import logging
import requests
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, Generator, Set
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.wikidata import WikidataClient, Item

log = logging.getLogger(__name__)
dataset = Dataset.make({"name": "synonames", "title": "Synonames"})
cache = Cache.make_default(dataset)
cache.preload(f"{WikidataClient.WD_API}%")
session = requests.Session()
client = WikidataClient(cache, session=session, cache_days=90)
out_path = Path(__file__).parent / "out"
out_path.mkdir(exist_ok=True, parents=True)


# Crawl wikidata for names
CLASSES = {
    "Q12308941": "given",  # male given name
    "Q11879590": "given",  # female given name
    "Q202444": "given",  # given name
    "Q122067883": "given",  # given name component
    "Q245025": "given",  # middle name
    "Q101352": "family",  # family name
    "Q4116295": "family",  # surname
    "Q120707496": "family",  # second family name
    "Q121493728": "family",  # first family name
    "Q110874": "patronymic",  # patronymic name
    "Q130444148": "patronymic",  # masculine patronymic name
    "Q130444179": "patronymic",  # feminine patronymic name
    "Q130443889": "matronymic",  # feminine matronymic name
    "Q130443873": "matronymic",  # masculine matronymic name
}
# Same as relation: https://www.wikidata.org/wiki/Property:P460
SPARQL = """
SELECT DISTINCT ?item WHERE { ?item wdt:P31 wd:%s . }
"""


def iterate_name_items() -> Generator[Item, None, None]:
    def fetch_item_safe(qid: str) -> Item:
        # Helper function to safely fetch an item
        while True:
            try:
                return client.fetch_item(qid)
            except requests.RequestException as e:
                log.error(f"Error fetching item {qid}: {e}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        for cls, cls_name in CLASSES.items():
            print("Crawling: ", cls, cls_name)
            query = SPARQL % cls
            response = client.query(query)
            print("Results: ", len(response.results))
            futures: Future[Item] = []
            for result in response.results:
                qid = result.plain("item")
                if qid is None or qid.startswith("L"):
                    continue
                futures.append(executor.submit(fetch_item_safe, qid))
            for idx, future in enumerate(as_completed(futures)):
                item = future.result()
                if item is None:
                    continue
                yield item
                if idx % 100 == 0:
                    print("Crawled: ", idx)
                    client.cache.flush()


def build_mappings():
    inverted: Dict[str, Set[str]] = defaultdict(set)
    for item in iterate_name_items():
        counter = Counter()
        unique = set()
        main_name = None
        for label in item.labels:
            name = label.text
            if name is None:
                continue
            if " " in name or "," in name or "-" in name or "(" in name or "/" in name:
                # print("Skipping: ", name)
                continue
            if len(name) > 30:
                continue
            if label.lang == "eng":
                main_name = name
            unique.add(name)
            counter[name] += 1
        if len(unique) < 1:
            continue
        if main_name is None:
            main_name = counter.most_common(1)[0][0]
        inverted[main_name].update(unique)
        # forms = ", ".join(unique)
        # out = f"{forms} => {main_name}"
        # print(out)

    with open(out_path / "wd_names_strict.txt", "w", encoding="utf-8") as fh:
        for main_name, aliases in inverted.items():
            aliases.remove(main_name)
            if len(aliases) < 2:
                continue
            forms = ", ".join(sorted(aliases))
            out = f"{forms} => {main_name}"
            fh.write(out + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_mappings()
