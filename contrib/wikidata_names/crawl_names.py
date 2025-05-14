import random
import logging
import requests
import unicodedata
from pathlib import Path
from functools import lru_cache
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from nomenklatura import settings
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.wikidata import WikidataClient
from rigour.names import is_name
from fingerprints import clean_brackets
from rigour.text.cleaning import remove_emoji
from rigour.text.scripts import is_modern_alphabet

log = logging.getLogger(__name__)
settings.DB_STMT_TIMEOUT = 10000 * 100000
dataset = Dataset.make({"name": "synonames", "title": "Synonames"})
cache = Cache.make_default(dataset)
# cache.preload(f"{WikidataClient.WD_API}%")
session = requests.Session()
client = WikidataClient(cache, session=session, cache_days=60)
out_path = Path(__file__).parent / "out"
out_path.mkdir(exist_ok=True, parents=True)


# Crawl wikidata for names
CLASSES = {
    "Q101352": "family",  # family name
    "Q4116295": "family",  # surname
    "Q120707496": "family",  # second family name
    "Q121493728": "family",  # first family name
    "Q110874": "patronymic",  # patronymic name
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
}
IGNORE = {"Q211024", "Q13198636"}
# Same as relation: https://www.wikidata.org/wiki/Property:P460
SPARQL = """
SELECT DISTINCT ?item WHERE { ?item wdt:P31 wd:%s . }
"""


@lru_cache(maxsize=1000)
def clean_name(name: Optional[str]) -> List[str]:
    if name is None:
        return []
    names: List[str] = []
    name = unicodedata.normalize("NFC", name)
    name = clean_brackets(name)
    name = remove_emoji(name)
    for part in name.split("/"):
        part = part.strip().lower()
        if not is_name(part):
            continue
        if len(part) > 30:
            continue
        if is_modern_alphabet(part) and len(part) < 2:
            print("Too short %r -> %r" % (name, part))
            continue
        if "," in part or "(" in part or "/" in part or "=" in part:
            # print("Skipping: ", part)
            continue
        names.append(part)
    return names


def process_item(qid: str) -> Tuple[str, Set[str]]:
    # Helper function to safely fetch an item
    try:
        item = client.fetch_item(qid)
        if item is None or item.id in CLASSES:
            return None
        unique = set()
        labels = list(item.labels)
        labels.extend(item.aliases)
        for claim in item.claims:
            # add P1705 native label
            # add P2440 transliteration or transcription
            if claim.property in ("P1705", "P2440"):
                labels.append(claim.text)

        for label in labels:
            name = label.text
            for name in clean_name(label.text):
                unique.add(name)
        if len(unique) < 1:
            return None
        return (qid, unique)
    except requests.RequestException as e:
        log.error(f"Error fetching item {qid}: {e}")
        # time.sleep(1)
        return None


def build_canonicalisations():
    inverted: Dict[str, Set[str]] = defaultdict(set)
    with ThreadPoolExecutor(max_workers=6) as executor:
        for cls, cls_name in CLASSES.items():
            print("Crawling: ", cls, cls_name)
            query = SPARQL % cls
            response = client.query(query)
            print("Results: ", len(response.results))
            futures: Future[Tuple[str, Set[str]]] = []
            random.shuffle(response.results)
            for result in response.results:
                qid = result.plain("item")
                if qid is None or qid.startswith("L"):
                    continue
                if qid in IGNORE:
                    continue
                futures.append(executor.submit(process_item, qid))
            for idx, future in enumerate(as_completed(futures)):
                result = future.result()
                if result is None:
                    continue
                qid, uniques = result
                inverted[qid].update(uniques)
                if idx > 0 and idx % 1000 == 0:
                    print("Crawled: ", idx)
                    # client.cache.flush()
                    cache.flush()

    print("Deduplicating name QIDs...")
    by_names: Dict[str, Set[str]] = defaultdict(set)
    for qid, aliases in inverted.items():
        for alias in aliases:
            by_names[alias].add(qid)
    for nqid, naliases in sorted(inverted.items()):
        other_qids = set()
        for alias in naliases:
            other_qids.update(by_names[alias])
        other_qids.discard(nqid)
        for oqid in other_qids:
            oaliases = inverted[oqid]
            if naliases.issubset(oaliases):
                print("Removing: ", nqid, "->", oqid, ": ", naliases)
                inverted.pop(nqid, None)

    print("Write out names file...")
    with open(out_path / "persons.txt", "w", encoding="utf-8") as fh:
        for qid, aliases in sorted(inverted.items()):
            if len(aliases) < 2:
                continue
            forms = ", ".join(sorted(aliases))
            out = f"{forms} => {qid}"
            fh.write(out + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # build_mappings()
    build_canonicalisations()
