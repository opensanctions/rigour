import random
import logging
import requests
from functools import lru_cache
from typing import List, Optional, Set, Tuple
# from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from followthemoney import Dataset
from nomenklatura import settings
from nomenklatura.cache import Cache
from nomenklatura.db import Session
from nomenklatura.wikidata import WikidataClient
from nomenklatura.wikidata.util import make_session

from namesdb.db import store_mapping, engine
from namesdb.blocks import GROUPS as BLOCKED_GROUPS
from namesdb.util import clean_form

log = logging.getLogger("namesdb.wikidata")
settings.DB_STMT_TIMEOUT = 10000 * 100000
dataset = Dataset.make({"name": "synonames", "title": "Synonames"})
db = Session(engine)
cache = Cache(db, dataset, create=True)
# cache.preload(f"{WikidataClient.WD_API}%")
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


@lru_cache(maxsize=1000)
def clean_wikidata_name(name: Optional[str]) -> List[str]:
    if name is None:
        return []
    names: List[str] = []
    for part in name.split("/"):
        part = clean_form(part)
        if part is None:
            continue
        if "," in part or "(" in part or "/" in part or "=" in part or ":" in part:
            # print("Skipping: ", part)
            continue
        names.append(part)
    return names


def process_item(qid: str) -> Optional[Tuple[str, Set[str]]]:
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
            for name in clean_wikidata_name(label.text):
                unique.add(name)
        if len(unique) < 1:
            return None
        return (qid, unique)
    except requests.RequestException as e:
        # The session retries on server errors and honours Retry-After on
        # 429/503, so anything surfacing here is a genuine failure to skip.
        log.error(f"Error fetching item {qid}: {e}")
        return None


def crawl_mappings():
    # with ThreadPoolExecutor(max_workers=6) as executor:
    classes = list(CLASSES.items())
    random.shuffle(classes)
    for cls, cls_name in classes:
        log.info("Crawling: %s (%s)", cls, cls_name)
        query = SPARQL % cls
        response = client.query(query)
        log.info("Results: %d", len(response.results))
        # futures: Future[Optional[Tuple[str, Set[str]]]] = []
        random.shuffle(response.results)
        # for result in response.results:
        #     qid = result.plain("item")
        #     if qid is None or qid.startswith("L"):
        #         continue
        #     if qid in IGNORE:
        #         continue
        #     futures.append(executor.submit(process_item, qid))
        # for idx, future in enumerate(as_completed(futures)):
        for idx, result in enumerate(response.results):
            qid = result.plain("item")
            if qid is None or qid.startswith("L") or qid in BLOCKED_GROUPS:
                continue
            item = process_item(qid)
            # result = future.result()
            if item is None:
                continue
            qid, uniques = item
            for form in uniques:
                log.info(f"Storing mapping: {qid} -> {form}")
                store_mapping(db.connection, form, qid)
            if idx > 0 and idx % 1000 == 0:
                log.info("Crawled: %d", idx)
                db.checkpoint()
        db.checkpoint()
    db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawl_mappings()
