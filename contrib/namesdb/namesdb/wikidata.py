import random
import logging
import requests
from functools import lru_cache
from typing import List, Optional, Set, Tuple
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from nomenklatura import settings
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.wikidata import WikidataClient

from namesdb.db import store_mapping, engine
from namesdb.util import clean_form

log = logging.getLogger(__name__)
settings.DB_STMT_TIMEOUT = 10000 * 100000
dataset = Dataset.make({"name": "synonames", "title": "Synonames"})
cache = Cache.make_default(dataset)
# cache.preload(f"{WikidataClient.WD_API}%")
session = requests.Session()
client = WikidataClient(cache, session=session, cache_days=90)


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
def clean_wikidata_name(name: Optional[str]) -> List[str]:
    if name is None:
        return []
    names: List[str] = []
    for part in name.split("/"):
        part = clean_form(part)
        if part is None:
            continue
        if "," in part or "(" in part or "/" in part or "=" in part:
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
        log.error(f"Error fetching item {qid}: {e}")
        # time.sleep(1)
        return None


def crawl_mappings():
    conn = engine.connect()
    conn.begin()
    # with ThreadPoolExecutor(max_workers=6) as executor:
    for cls, cls_name in CLASSES.items():
        print("Crawling: ", cls, cls_name)
        query = SPARQL % cls
        response = client.query(query)
        print("Results: ", len(response.results))
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
            if qid is None or qid.startswith("L"):
                continue
            if qid in IGNORE:
                continue
            item = process_item(qid)
            # result = future.result()
            if item is None:
                continue
            qid, uniques = item
            for form in uniques:
                log.info(f"Storing mapping: {qid} -> {form}")
                store_mapping(conn, form, qid)
            if idx > 0 and idx % 1000 == 0:
                print("Crawled: ", idx)
                # client.cache.flush()
                cache.flush()
                conn.commit()
                conn.begin()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    crawl_mappings()
