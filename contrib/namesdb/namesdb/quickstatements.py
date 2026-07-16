"""Emit QuickStatements alias additions that sync name forms between
high-overlap Wikidata name items.

When two name items share most of their forms, each item is usually
missing a few transliterations that its sibling already carries. This
module diffs such pairs and proposes the missing strings as aliases,
so the next crawl sees more complete items (and the dump's subset
dedup can collapse more groups).

Candidate pairs come from the local mapping table; the actual alias
strings and their language codes are re-read from the raw item JSON in
the Wikidata response cache. The mapping table cannot serve that role:
stored forms are cleaned/lowercased and carry no language, while the
cache has the original strings under original Wikidata language codes.
Cache-only by design — this module never talks to the network.
"""

import json
import logging
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import Column, Connection, MetaData, Table, Unicode, select
from rigour.ids.wikidata import is_qid
from rigour.urls import build_url

from namesdb.db import all_mappings, engine
from namesdb.export import normalize_form
from namesdb.util import clean_wikidata_name

log = logging.getLogger(__name__)

WD_API = "https://www.wikidata.org/w/api.php"
# Must mirror nomenklatura's WikidataClient.fetch_item exactly, so the
# built URL matches the cache keys written during crawling.
WD_PROPS = "info|sitelinks/urls|aliases|labels|descriptions|claims|datatype"

# Forms held by this many groups or more are treated as too ambiguous
# to serve as pair evidence (e.g. very common romanizations).
MAX_FORM_GROUPS = 50

cache_table = Table(
    "cache",
    MetaData(),
    Column("key", Unicode(), primary_key=True),
    Column("text", Unicode(), nullable=True),
)

# Raw string -> set of Wikidata language codes carrying it on an item.
EntityStrings = Dict[str, Set[str]]


@dataclass
class SyncStats:
    pairs_considered: int = 0
    pairs_synced: int = 0
    cache_misses: Set[str] = field(default_factory=set)
    directions_capped: int = 0
    lines: int = 0
    redirects: Dict[str, str] = field(default_factory=dict)


def entity_url(qid: str) -> str:
    params = {
        "format": "json",
        "ids": qid,
        "action": "wbgetentities",
        "props": WD_PROPS,
    }
    return build_url(WD_API, params=params)


def get_cached_entity(conn: Connection, qid: str) -> Optional[Dict[str, Any]]:
    """Read the raw wbgetentities JSON for an item from the crawl cache."""
    stmt = select(cache_table.c.text)
    stmt = stmt.where(cache_table.c.key == entity_url(qid))
    row = conn.execute(stmt).first()
    if row is None or row.text is None:
        return None
    data = json.loads(row.text)
    entity: Optional[Dict[str, Any]] = data.get("entities", {}).get(qid)
    if entity is None or "missing" in entity:
        return None
    return entity


def entity_strings(entity: Dict[str, Any]) -> EntityStrings:
    """Collect all label and alias strings with their language codes."""
    strings: EntityStrings = defaultdict(set)
    labels = entity.get("labels") or {}
    if isinstance(labels, dict):
        for lang, obj in labels.items():
            value = obj.get("value")
            if value is not None:
                strings[value].add(obj.get("language", lang))
    aliases = entity.get("aliases") or {}
    if isinstance(aliases, dict):
        for lang, objs in aliases.items():
            for obj in objs:
                value = obj.get("value")
                if value is not None:
                    strings[value].add(obj.get("language", lang))
    return strings


def presence_key(text: str) -> str:
    """Fold a string for the "does the target already have this?" check.

    Deliberately aggressive: tone digits, diacritics, modifier letters
    and apostrophes are stripped, so a candidate that differs from an
    existing target string only by such marks is treated as already
    present and never emitted. Relax this to plain NFC casefolding to
    also sync diacritic/tone variants (e.g. "gaa1" vs "gaa¹") — more
    edits, but they read as pedantic clutter to human patrollers.
    """
    out: List[str] = []
    for ch in unicodedata.normalize("NFKD", text.casefold()):
        if unicodedata.category(ch) in ("Mn", "Sk", "Lm"):
            continue
        if ch.isdigit() or ch in "`´'’ʼʻ‘-·. ":
            continue
        out.append(ch)
    return "".join(out)


def contains_han(text: str) -> bool:
    # Han characters are identity-bearing: two items may share every
    # romanization yet denote different names written with different
    # characters (裕毅 vs 優樹, both "Yuki"). Never propagate them.
    # A more aggressive version could copy graphical variants of
    # characters the target already has, using Unihan kSemanticVariant/
    # kZVariant tables — but that needs per-edit review.
    for ch in text:
        cp = ord(ch)
        if 0x2E80 <= cp <= 0x2FDF or cp in (0x3005, 0x3007):
            return True
        if 0x3400 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
            return True
        if 0x20000 <= cp <= 0x3FFFF:
            return True
    return False


def high_overlap_pairs(
    mappings: Dict[str, Set[str]], min_shared: int, min_jaccard: float
) -> List[Tuple[str, str, int, float]]:
    """Score group pairs by form overlap, best first."""
    by_form: Dict[str, Set[str]] = defaultdict(set)
    for group, forms in mappings.items():
        for form in forms:
            by_form[form].add(group)
    shared: Dict[Tuple[str, str], int] = defaultdict(int)
    for form, groups in by_form.items():
        if len(groups) < 2 or len(groups) > MAX_FORM_GROUPS:
            continue
        for a, b in combinations(sorted(groups), 2):
            shared[(a, b)] += 1
    pairs: List[Tuple[str, str, int, float]] = []
    for (a, b), count in shared.items():
        if count < min_shared:
            continue
        jaccard = count / len(mappings[a] | mappings[b])
        # Lowering --min-jaccard admits subset-shaped pairs (a sparse
        # item inside a rich reading cluster) — larger, still mostly
        # sound sync candidates, but review the output more carefully.
        if jaccard < min_jaccard:
            continue
        pairs.append((a, b, count, jaccard))
    pairs.sort(key=lambda p: (-p[3], -p[2], p[0], p[1]))
    return pairs


def propose_aliases(
    source_strings: EntityStrings,
    source_forms: Set[str],
    target_present: Set[str],
) -> List[Tuple[str, str]]:
    """Propose (lang, text) aliases the target is missing.

    Ultra-conservative on purpose: every emitted string must already
    exist verbatim on the source item, survive our ingest cleaning into
    a form we actually hold for the source group (so manual `ndb skip`
    curation and the junk filters apply to uploads too), and be absent
    from the target even under aggressive folding.
    """
    proposals: List[Tuple[str, str]] = []
    for text, langs in source_strings.items():
        if "|" in text or '"' in text or "\n" in text or "\t" in text:
            continue
        if contains_han(text):
            continue
        cleaned = clean_wikidata_name(text)
        if len(cleaned) != 1:
            continue
        form = normalize_form(cleaned[0])
        if form not in source_forms:
            continue
        if presence_key(text) in target_present:
            continue
        # Reuse the source's own language codes — no inference. When the
        # source carries the string as language-neutral ("mul"), one such
        # alias suffices. A more aggressive option is to emit "mul" for
        # every romanization regardless of source codes, per the Wikidata
        # convention for name items — but that reshapes items rather than
        # mirroring existing usage, so it needs community buy-in first.
        if "mul" in langs:
            proposals.append(("mul", text))
        else:
            for lang in sorted(langs):
                proposals.append((lang, text))
    proposals.sort()
    return proposals


def load_mappings(conn: Connection) -> Dict[str, Set[str]]:
    mappings: Dict[str, Set[str]] = {}
    for group, aliases in all_mappings(conn):
        if not is_qid(group):
            continue
        normed = set(normalize_form(a) for a in aliases)
        normed.discard("")
        if len(normed) > 1:
            mappings[group] = normed
    return mappings


def generate_statements(
    min_shared: int,
    min_jaccard: float,
    max_per_pair: int,
    limit: int,
) -> Tuple[List[str], SyncStats]:
    """Build QuickStatements v1 lines (including comment lines)."""
    stats = SyncStats()
    lines: List[str] = []
    emitted: Set[Tuple[str, str, str]] = set()
    with engine.connect() as conn:
        mappings = load_mappings(conn)
        log.info("Loaded %d groups, scoring overlap...", len(mappings))
        pairs = high_overlap_pairs(mappings, min_shared, min_jaccard)
        log.info("Found %d candidate pairs", len(pairs))
        entities: Dict[str, Optional[Dict[str, Any]]] = {}
        for a, b, count, jaccard in pairs:
            if stats.lines >= limit:
                break
            stats.pairs_considered += 1
            for qid in (a, b):
                if qid not in entities:
                    entities[qid] = get_cached_entity(conn, qid)
                    if entities[qid] is None:
                        stats.cache_misses.add(qid)
            ent_a, ent_b = entities[a], entities[b]
            if ent_a is None or ent_b is None:
                continue
            redirected = False
            for qid, ent in ((a, ent_a), (b, ent_b)):
                target = ent.get("id")
                if target is not None and target != qid:
                    # The item was merged/redirected on Wikidata since we
                    # crawled it: nothing to sync, the pair resolves itself
                    # on the next crawl. Reported at the end of the file.
                    stats.redirects[qid] = target
                    redirected = True
            if redirected:
                continue
            strings_a = entity_strings(ent_a)
            strings_b = entity_strings(ent_b)
            present_a = set(presence_key(t) for t in strings_a)
            present_b = set(presence_key(t) for t in strings_b)
            block: List[str] = []
            directions = [
                (a, strings_a, present_b, b),
                (b, strings_b, present_a, a),
            ]
            for source, strings, present, target in directions:
                proposals = propose_aliases(strings, mappings[source], present)
                proposals = [
                    (lang, text)
                    for lang, text in proposals
                    if (target, lang, text) not in emitted
                ]
                if len(proposals) > max_per_pair:
                    # A direction proposing this much usually means the
                    # pair is not the near-duplicate it looked like.
                    stats.directions_capped += 1
                    continue
                for lang, text in proposals:
                    emitted.add((target, lang, text))
                    block.append(f'{target}|A{lang}|"{text}"')
            if len(block) == 0:
                continue
            stats.pairs_synced += 1
            stats.lines += len(block)
            lines.append(
                f"/* {a} <-> {b}: {count} shared forms, jaccard {jaccard:.2f} */"
            )
            lines.extend(block)
    if len(stats.redirects) > 0:
        lines.append("/* Items merged on Wikidata since last crawl: */")
        for qid, target in sorted(stats.redirects.items()):
            lines.append(f"/*   {qid} -> {target} */")
    return lines, stats
