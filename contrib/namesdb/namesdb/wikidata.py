import json
import logging
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import requests
from followthemoney import Dataset
from nomenklatura import settings
from nomenklatura.cache import Cache
from nomenklatura.db import Session
from nomenklatura.wikidata import WikidataClient
from nomenklatura.wikidata.util import make_session

from namesdb.blocks import GROUPS as BLOCKED_GROUPS
from namesdb.db import (
    SOURCE_ALIAS,
    SOURCE_LABEL,
    SOURCE_NATIVE,
    SOURCE_TRANSLIT,
    ItemNames,
    engine,
    store_item,
    store_mapping,
)
from namesdb.util import clean_form
from rigour.urls import build_url

log = logging.getLogger("namesdb.wikidata")
settings.DB_STMT_TIMEOUT = 10000 * 100000
dataset = Dataset.make({"name": "synonames", "title": "Synonames"})
db = Session(engine)
cache = Cache(db, dataset, create=True)
session = make_session(
    user_agent="opensanctions-namesdb/1.0 (+https://opensanctions.org; tech@opensanctions.org)"
)
client = WikidataClient(cache, session=session, cache_days=200)


# Crawl wikidata for names
CLASSES = {
    "Q101352": "family",  # family name
    "Q4116295": "family",  # surname
    "Q120707496": "family",  # second family name
    "Q121493728": "family",  # first family name
    "Q66475447": "family",  # family name affix
    "Q12717622": "parentonymic",  # parentonymic name
    "Q110874": "patronymic",  # patronymic name
    "Q1076664": "matronymic",  # matronymic name
    "Q130444148": "patronymic",  # masculine patronymic name
    "Q130444179": "patronymic",  # feminine patronymic name
    "Q130443889": "matronymic",  # feminine matronymic name
    "Q130443873": "matronymic",  # masculine matronymic name
    "Q12308941": "given",  # male given name
    "Q11879590": "given",  # female given name
    "Q3409032": "given",  # unisex given name
    "Q202444": "given",  # given name
    "Q122067883": "given",  # given name component
    "Q245025": "given",  # middle name
    "Q200835": "honorific",  # religiour title of honor
}
# Same as relation: https://www.wikidata.org/wiki/Property:P460
SPARQL = """
SELECT DISTINCT ?item WHERE { ?item wdt:P31 wd:%s . }
"""

# P1705 (native label) is monolingual text and carries its own language.
# P2440 (transliteration or transcription) is a plain string: its language
# comes from the P424 qualifier when present, otherwise from labels on the
# same item that spell the form identically, otherwise it is undetermined.
NATIVE_LABEL = "P1705"
TRANSLITERATION = "P2440"
# Qualifier on P2440 naming the transliteration standard (determination method).
SCHEME_QUALIFIER = "P459"
# Qualifier on P2440 giving the Wikimedia language code of the transliteration.
LANG_QUALIFIER = "P424"
# Language code for a transliteration whose target language Wikidata leaves
# open. Distinct from `UNKNOWN_LANG`, which marks rows never tagged at all.
UNDETERMINED_LANG = "und"


@dataclass
class NameMeta:
    """Provenance of one (form, lang) on a Wikidata item."""

    source: int = 0
    scheme: str | None = None

    def merge(self, source: int, scheme: str | None) -> None:
        self.source |= source
        if self.scheme is None:
            self.scheme = scheme


@lru_cache(maxsize=1000)
def clean_wikidata_name(name: str | None) -> list[str]:
    if name is None:
        return []
    names: list[str] = []
    for raw in name.split("/"):
        part = clean_form(raw)
        if part is None:
            continue
        if "," in part or "(" in part or "/" in part or "=" in part or ":" in part:
            continue
        names.append(part)
    return names


def item_url(qid: str) -> str:
    """Build the wbgetentities URL under which the client caches an item."""
    params = {
        "format": "json",
        "ids": qid,
        "action": "wbgetentities",
        "props": "info|sitelinks/urls|aliases|labels|descriptions|claims|datatype",
    }
    return build_url(WikidataClient.WD_API, params=params)


def qualifier_values(claim: dict[str, Any], prop: str) -> list[Any]:
    values: list[Any] = []
    for qual in claim.get("qualifiers", {}).get(prop, []):
        if qual.get("snaktype") != "value":
            continue
        values.append(qual.get("datavalue", {}).get("value"))
    return values


def claim_value(claim: dict[str, Any]) -> Any:
    """Return the main value of a non-deprecated claim, or None."""
    if claim.get("rank") == "deprecated":
        return None
    snak = claim.get("mainsnak", {})
    if snak.get("snaktype") != "value":
        return None
    return snak.get("datavalue", {}).get("value")


def extract_names(entity: dict[str, Any]) -> dict[tuple[str, str], NameMeta]:
    """Collect name forms with their raw Wikidata language tags from an entity.

    Reads the raw entity JSON rather than the client's `Item` so that
    language codes are kept as Wikidata gives them (`sr-el`, `zh-hans`,
    `mul`), which the FtM language registry would otherwise collapse or
    drop.
    """
    names: dict[tuple[str, str], NameMeta] = {}

    def add(form: str, lang: str, source: int, scheme: str | None = None) -> None:
        names.setdefault((form, lang), NameMeta()).merge(source, scheme)

    for label in entity.get("labels", {}).values():
        for form in clean_wikidata_name(label.get("value")):
            add(form, label["language"], SOURCE_LABEL)
    for aliases in entity.get("aliases", {}).values():
        for alias in aliases:
            for form in clean_wikidata_name(alias.get("value")):
                add(form, alias["language"], SOURCE_ALIAS)

    claims: dict[str, list[dict[str, Any]]] = entity.get("claims", {})
    for claim in claims.get(NATIVE_LABEL, []):
        value = claim_value(claim)
        if not isinstance(value, dict) or not isinstance(value.get("text"), str):
            continue
        for form in clean_wikidata_name(value["text"]):
            add(form, value["language"], SOURCE_NATIVE)

    for claim in claims.get(TRANSLITERATION, []):
        value = claim_value(claim)
        if not isinstance(value, str):
            continue
        scheme: str | None = None
        for qvalue in qualifier_values(claim, SCHEME_QUALIFIER):
            if isinstance(qvalue, dict) and isinstance(qvalue.get("id"), str):
                scheme = qvalue["id"]
                break
        langs = [
            v for v in qualifier_values(claim, LANG_QUALIFIER) if isinstance(v, str)
        ]
        for form in clean_wikidata_name(value):
            form_langs = langs or [lang for (f, lang) in names if f == form]
            for lang in form_langs or [UNDETERMINED_LANG]:
                add(form, lang, SOURCE_TRANSLIT, scheme)
    return names


def extract_classes(entity: dict[str, Any]) -> list[str]:
    """Return the item's P31 classes that are among the crawled name classes."""
    classes: set[str] = set()
    for claim in entity.get("claims", {}).get("P31", []):
        value = claim_value(claim)
        if isinstance(value, dict) and value.get("id") in CLASSES:
            classes.add(value["id"])
    return sorted(classes)


def pack_names(
    names: dict[tuple[str, str], NameMeta],
) -> tuple[ItemNames, dict[str, str]]:
    """Regroup extracted names by form for storage as `item.names` / `item.schemes`."""
    packed: ItemNames = {}
    schemes: dict[str, str] = {}
    for (form, lang), meta in names.items():
        packed.setdefault(form, {})[lang] = meta.source
        if meta.scheme is not None and form not in schemes:
            schemes[form] = meta.scheme
    return packed, schemes


def process_item(
    qid: str,
) -> tuple[str, list[str], dict[tuple[str, str], NameMeta]] | None:
    try:
        item = client.fetch_item(qid)
        if item is None or item.id in CLASSES:
            return None
        # fetch_item has followed redirects and filled the cache, so the raw
        # body for the resolved id is available without another request.
        raw = cache.get(item_url(item.id))
        if raw is None:
            return None
        entity = json.loads(raw).get("entities", {}).get(item.id)
        if entity is None:
            return None
        names = extract_names(entity)
        if len(names) < 1:
            return None
        return (item.id, extract_classes(entity), names)
    except requests.RequestException as e:
        # The session retries on server errors and honours Retry-After on
        # 429/503, so anything surfacing here is a genuine failure to skip.
        log.error(f"Error fetching item {qid}: {e}")
        return None


def crawl_mappings() -> None:
    classes = list(CLASSES.items())
    random.shuffle(classes)
    for cls, cls_name in classes:
        log.info("Crawling: %s (%s)", cls, cls_name)
        query = SPARQL % cls
        response = client.query(query)
        log.info("Results: %d", len(response.results))
        random.shuffle(response.results)
        for idx, result in enumerate(response.results):
            qid = result.plain("item")
            if qid is None or qid.startswith("L") or qid in BLOCKED_GROUPS:
                continue
            item = process_item(qid)
            if item is None:
                continue
            qid, item_classes, names = item
            packed, schemes = pack_names(names)
            for form in packed:
                log.info(f"Storing mapping: {qid} -> {form}")
                store_mapping(db.connection, form, qid)
            store_item(db.connection, qid, item_classes, packed, schemes)
            if idx > 0 and idx % 1000 == 0:
                log.info("Crawled: %d", idx)
                db.checkpoint()
        db.checkpoint()
    db.commit()


def backfill_from_cache() -> None:
    """Store item extractions from every cached item response.

    Fills the item table for items crawled before language metadata was
    recorded, without any new Wikidata traffic. Rows are stamped with the
    cache entry's timestamp, so a fresher crawl is never overwritten.
    """
    like = f"{WikidataClient.WD_API}%wbgetentities%"
    items = 0
    for value in cache.all(like=like):
        if value.text is None:
            continue
        entities = json.loads(value.text).get("entities")
        if entities is None:
            continue
        for qid, entity in entities.items():
            if "missing" in entity or "redirects" in entity:
                continue
            if qid in CLASSES or qid in BLOCKED_GROUPS:
                continue
            names = extract_names(entity)
            if len(names) < 1:
                continue
            packed, schemes = pack_names(names)
            store_item(
                db.connection,
                qid,
                extract_classes(entity),
                packed,
                schemes,
                seen_at=value.timestamp,
            )
            items += 1
            if items % 1000 == 0:
                log.info("Backfilled: %d items", items)
                db.checkpoint()
    log.info("Backfilled: %d items", items)
    db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawl_mappings()
