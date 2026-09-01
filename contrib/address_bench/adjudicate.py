"""Label candidate address pairs with Claude Sonnet 5.

Stage two of the address_bench pipeline. Reads `candidates.csv`, asks
the model whether each pair denotes the same physical address, and
appends the verdicts to `cases.csv`.

The candidate stratum is only a prior — `generate.py` cannot tell a
transliteration from a different building on the same street, and
neither can a token overlap score. Two passes run: a direct one over
every pair, then an adversarial re-check over the pairs the first pass
called a match, because the failure mode this corpus most needs to
avoid is a labeller that waves through structurally distinct addresses.

Verdicts are cached in `.cache.jsonl` keyed by the pair and prompt
version, so a re-run costs nothing and a prompt edit invalidates
cleanly.
"""

import csv
import json
import os
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import blake2b
from pathlib import Path
from typing import Literal

import anthropic
import click
from anthropic.types import (
    JSONOutputFormatParam,
    MessageParam,
    OutputConfigParam,
    TextBlockParam,
    ThinkingConfigAdaptiveParam,
)
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.progress import Progress

HERE = Path(__file__).parent
CANDIDATES = HERE / "candidates.csv"
CASES = HERE / "cases.csv"
CACHE = HERE / ".cache.jsonl"

MODEL = "claude-sonnet-5"

#: Bumping this invalidates every cached verdict. Change it whenever a
#: prompt below changes in a way that could move a label.
PROMPT_VERSION = 1

CASE_FIELDS = [
    "case_group",
    "addr1",
    "addr2",
    "is_match",
    "quality",
    "category",
    "notes",
]

#: Strata that are over-generated and thinned after classification, as
#: {case_group: how many matches to keep}. Every non-match is kept.
#:
#: `block_neardupe` pairs have identical token sets, so ~99% of them are
#: the same address written two ways — cheap rows that teach little. The
#: ~1% that are *not* are the most valuable rows in the corpus:
#: `УЛ СОЛЯНКА Д. 1/2 СТР. 1` and `УЛ СОЛЯНКА Д. 1/2 СТР. 2` are
#: different buildings whose token sets collide exactly, so nothing
#: scoring token overlap can ever separate them. Finding them means
#: classifying the boring 99% and throwing most of it away.
HARVEST_MATCH_CAP = {"block_neardupe": 800}

console = Console(stderr=True)


class Verdict(BaseModel):
    """One model judgement about a pair of address strings."""

    label: Literal["same", "subset", "different"]
    confidence: Literal["high", "medium", "low"]
    category: str
    reason: str


THINKING: ThinkingConfigAdaptiveParam = {"type": "adaptive"}

SCHEMA: JSONOutputFormatParam = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["same", "subset", "different"]},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "category": {
                "type": "string",
                "description": "Lowercase slug naming the single most salient difference, e.g. translit_cyrillic, translation_cjk, abbreviation, punctuation_only, house_number_differs, unit_differs, different_street, different_city, city_only.",
            },
            "reason": {"type": "string", "description": "At most 15 words."},
        },
        "required": ["label", "confidence", "category", "reason"],
        "additionalProperties": False,
    },
}

DIRECT_SYSTEM = """\
You judge whether two address strings, drawn from corporate registries \
and sanctions lists, denote the same physical location. The strings are \
messy: different languages, scripts, transliterations, abbreviations, \
field orders, and levels of detail.

Assign exactly one label.

`same` — the same physical location. Assign it despite any of:
  - transliteration or translation between scripts. `УЛ. БОЛЬШАЯ \
ПЕРЕЯСЛАВСКАЯ Д. 46 СТР. 2, Г.МОСКВА, 129110` and `129110, м. Москва, \
вул. Велика Переяслівська, буд. 46 (будова 2)` are `same`. So are \
`新疆石河子市北泉镇北泉路西211栋-2号` and `West of Beiquan Road, Beiquan \
Town, Shihezi City, Xinjiang 211 Building -2`.
  - abbreviation or expansion: `St` / `Street`, `Ter.` / `Terrace`, \
`ул.` / `улица`, `NW` / `Northwest`.
  - reordered fields, differing punctuation, differing case.
  - one side naming the country or region and the other omitting it.

`subset` — one string is less specific than the other but consistent \
with it: every component present on both sides agrees, and one side \
simply stops earlier. `MARYVILLE, TN 37804` versus `2651 SEVIERVILLE \
ROAD, MARYVILLE, TN 37804` is `subset`. Use this only when the shorter \
string adds nothing that contradicts the longer one.

`different` — different physical locations. Assign it for:
  - a different street, city, or postcode.
  - the same street with a different house or building number. \
`Professor Brochs gate 12` and `Professor Brochs gate 14` are \
`different`.
  - the same building with a different apartment, unit, suite, floor or \
PO box number. `12 Bld 1 Rochdelskaya Street Apt 13` and `12 Bld 1 \
Rochdelskaya Street Apt 1` are `different`.
  - two sites of one organisation. A company's registered office and its \
factory are `different` addresses even under one record.

Judge the locations, not the entities. Two unrelated companies often \
share a registered-agent address; that pair is `same`. One company often \
lists two genuine sites; that pair is `different`.

Set `confidence` to `low` whenever the strings are too fragmentary, too \
garbled, or too ambiguous to rule on with real conviction. A `low` \
verdict is more useful than a confident guess."""

ADVERSARIAL_SYSTEM = """\
An automated labeller has claimed that the two address strings below \
denote the SAME physical location. Your job is to check that claim \
sceptically.

First look for every reason they might be distinct locations: a \
different house or building number, a different apartment, unit, suite, \
floor or PO box, a different street with a similar name, a different \
settlement sharing a name, a postcode that does not fit the city, two \
sites of the same organisation. Small numeric differences are the most \
common way a labeller is wrong — check every number on both sides.

Then rule.

`same` — the claim holds. Every difference is a matter of \
transliteration, translation, abbreviation, field order, punctuation, \
or one side omitting a component the other states.

`subset` — the strings are consistent, but one is strictly less \
specific than the other rather than an equivalent rendering of it.

`different` — the claim is wrong; these are distinct locations.

Do not endorse the claim to be agreeable. If the strings differ in any \
component that identifies a distinct deliverable location, the answer is \
`different`."""


def pair_prompt(addr1: str, addr2: str) -> str:
    """Render the volatile half of the request.

    Kept minimal and last so the cached system prefix does the work.
    """
    return f"A: {addr1}\nB: {addr2}"


def cache_key(addr1: str, addr2: str, phase: str) -> str:
    """Key a verdict by pair, phase, and prompt version."""
    raw = f"{PROMPT_VERSION}|{phase}|{addr1}|{addr2}"
    return blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()


def case_id(case_group: str, addr1: str, addr2: str) -> str:
    """Derive the stable identity of a corpus row.

    Not stored in `cases.csv` — deriving it keeps the file hand-editable
    and lets rows be inserted anywhere.
    """
    raw = f"{case_group}|{addr1}|{addr2}"
    return blake2b(raw.encode("utf-8"), digest_size=4).hexdigest()


class Cache:
    """Append-only JSONL store of model verdicts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.entries: dict[str, Verdict] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if not len(line.strip()):
                        continue
                    row = json.loads(line)
                    self.entries[row["key"]] = Verdict(**row["verdict"])

    def get(self, key: str) -> Verdict | None:
        return self.entries.get(key)

    def put(self, key: str, verdict: Verdict) -> None:
        with self.lock:
            self.entries[key] = verdict
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps({"key": key, "verdict": verdict.model_dump()}) + "\n"
                )
                fh.flush()


def judge(
    client: anthropic.Anthropic,
    cache: Cache,
    addr1: str,
    addr2: str,
    phase: str,
) -> Verdict | None:
    """Return the model's verdict on one pair, hitting the cache first."""
    key = cache_key(addr1, addr2, phase)
    cached = cache.get(key)
    if cached is not None:
        return cached
    prompt = DIRECT_SYSTEM if phase == "direct" else ADVERSARIAL_SYSTEM
    system: list[TextBlockParam] = [
        {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
    ]
    messages: list[MessageParam] = [
        {"role": "user", "content": pair_prompt(addr1, addr2)}
    ]
    output_config: OutputConfigParam = {"effort": "medium", "format": SCHEMA}
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            thinking=THINKING,
            output_config=output_config,
            system=system,
            messages=messages,
        )
    except anthropic.APIStatusError as exc:
        console.print(f"[red]API error {exc.status_code}: {exc.message}")
        return None
    except anthropic.APIConnectionError:
        console.print("[red]Connection error")
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return None
    try:
        verdict = Verdict(**json.loads(text))
    except (ValidationError, json.JSONDecodeError) as exc:
        console.print(f"[red]Unparseable verdict: {exc}")
        return None
    cache.put(key, verdict)
    return verdict


#: (label, confidence, passes agreed) -> (is_match, quality). A first
#: pass the adversarial re-check contradicts is never silently flipped;
#: it is kept as the direct verdict and demoted to WEAK, which is what
#: the tier means: defensible either way, and worth a human eye.
def resolve(direct: Verdict, recheck: Verdict | None) -> tuple[bool, str, str]:
    """Fold one or two verdicts into a corpus label, tier, and category."""
    if direct.label == "subset":
        return True, "WEAK", "subset"
    if direct.label == "different":
        quality = {"high": "STRONG", "medium": "MEDIUM", "low": "WEAK"}[
            direct.confidence
        ]
        return False, quality, direct.category
    if recheck is not None and recheck.label == "different":
        return True, "WEAK", direct.category
    if recheck is not None and recheck.label == "subset":
        return True, "WEAK", "subset"
    if direct.confidence == "low" or (
        recheck is not None and recheck.confidence == "low"
    ):
        return True, "WEAK", direct.category
    if (
        direct.confidence == "high"
        and recheck is not None
        and recheck.confidence == "high"
    ):
        return True, "STRONG", direct.category
    return True, "MEDIUM", direct.category


def load_candidates(limit: int | None) -> list[dict[str, str]]:
    """Read candidates.csv, skipping pairs already present in cases.csv.

    Under `--limit` the rows are drawn round-robin across strata rather
    than off the top of the file, so a sample run exercises every prompt
    case instead of just the first stratum.
    """
    with open(CANDIDATES, "r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    known = existing_ids()
    fresh: list[dict[str, str]] = []
    seen = set(known)
    for r in rows:
        cid = case_id(r["stratum"], r["addr1"], r["addr2"])
        # candidates.csv can carry one pair twice under different dataset
        # provenance; the corpus must hold it once.
        if cid in seen:
            continue
        seen.add(cid)
        fresh.append(r)
    if limit is None:
        return fresh
    by_stratum: dict[str, list[dict[str, str]]] = {}
    for row in fresh:
        by_stratum.setdefault(row["stratum"], []).append(row)
    picked: list[dict[str, str]] = []
    index = 0
    while len(picked) < limit and any(len(v) > index for v in by_stratum.values()):
        for rows_in in by_stratum.values():
            if index < len(rows_in) and len(picked) < limit:
                picked.append(rows_in[index])
        index += 1
    return picked


def existing_ids() -> set[str]:
    """Derive the case_id of every row already in the corpus."""
    return {case_id(r["case_group"], r["addr1"], r["addr2"]) for r in existing_rows()}


def existing_rows() -> list[dict[str, str]]:
    """Read the corpus as it stands, or nothing if it does not exist."""
    if not CASES.exists():
        return []
    with open(CASES, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def banked_matches() -> Counter[str]:
    """Count matches already in the corpus per harvested stratum.

    Seeding the cap from the corpus is what stops a resumed or repeated
    run from admitting a second full quota of matches on top of the ones
    already banked.
    """
    counts: Counter[str] = Counter()
    for row in existing_rows():
        if row["case_group"] in HARVEST_MATCH_CAP and row["is_match"] == "true":
            counts[row["case_group"]] += 1
    return counts


def keep(case: dict[str, str], banked: Counter[str]) -> bool:
    """Decide whether an adjudicated row belongs in the corpus.

    Only harvested strata discard anything, and only their matches. The
    verdict is cached either way, so a discarded row costs nothing to
    re-derive on the next run. Call under the writer lock — this mutates
    `banked`.
    """
    group = case["case_group"]
    cap = HARVEST_MATCH_CAP.get(group)
    if cap is None or case["is_match"] == "false":
        return True
    if banked[group] >= cap:
        return False
    banked[group] += 1
    return True


def adjudicate(
    client: anthropic.Anthropic, cache: Cache, row: dict[str, str]
) -> dict[str, str] | None:
    """Run both passes over one candidate and shape the corpus row."""
    addr1, addr2 = row["addr1"], row["addr2"]
    direct = judge(client, cache, addr1, addr2, "direct")
    if direct is None:
        return None
    recheck = None
    if direct.label == "same":
        recheck = judge(client, cache, addr1, addr2, "adversarial")
    is_match, quality, category = resolve(direct, recheck)
    datasets = f"{row['dataset1']}/{row['dataset2']}"
    return {
        "case_group": row["stratum"],
        "addr1": addr1,
        "addr2": addr2,
        "is_match": "true" if is_match else "false",
        "quality": quality,
        "category": category,
        "notes": f"{direct.reason} [{datasets}]",
    }


@click.command()
@click.option(
    "--limit", type=int, default=None, help="Only adjudicate the first N candidates."
)
@click.option("--workers", default=12, help="Concurrent API requests.")
def main(limit: int | None, workers: int) -> None:
    """Append adjudicated rows to cases.csv."""
    if os.environ.get("ANTHROPIC_API_KEY") is None:
        console.print("[red]ANTHROPIC_API_KEY is not set — see README.")
        sys.exit(1)
    if not CANDIDATES.exists():
        console.print(f"[red]{CANDIDATES} missing — run generate.py first.")
        sys.exit(1)

    client = anthropic.Anthropic(max_retries=5)
    cache = Cache(CACHE)
    rows = load_candidates(limit)
    if not len(rows):
        console.print("Nothing new to adjudicate.")
        return
    console.print(
        f"Adjudicating {len(rows)} candidates ({len(cache.entries)} cached verdicts)"
    )

    is_new = not CASES.exists()
    with open(CASES, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CASE_FIELDS)
        if is_new:
            writer.writeheader()
        write_lock = threading.Lock()
        banked = banked_matches()
        with Progress(console=console) as progress:
            task = progress.add_task("adjudicating", total=len(rows))

            def work(row: dict[str, str]) -> None:
                case = adjudicate(client, cache, row)
                if case is not None:
                    with write_lock:
                        if keep(case, banked):
                            writer.writerow(case)
                            fh.flush()
                progress.advance(task)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(work, rows))
    console.print(f"Wrote {CASES}")


if __name__ == "__main__":
    main()
