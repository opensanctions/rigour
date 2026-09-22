import csv
import logging
import unicodedata
from collections import defaultdict
from collections.abc import Generator, Iterable
from typing import IO

from normality import ascii_text
from normality.cleaning import remove_unsafe_chars

from namesdb.cleanup import block_forms, block_groups, block_phrases
from namesdb.db import (
    SOURCE_ALIAS,
    SOURCE_LABEL,
    SOURCE_NATIVE,
    SOURCE_TRANSLIT,
    all_mappings,
    engine,
    form_script,
    iter_items,
    skipped_pairs,
)
from rigour.text.scripts import can_latinize

log = logging.getLogger(__name__)


def can_translit_match(forms: Iterable[str]) -> bool:
    latinized: set[str] = set()
    for form in forms:
        if not can_latinize(form):
            return False
        ascii = ascii_text(form)
        if len(form) > 1 and len(ascii) == 0:
            return False
        latinized.add(ascii)
    return len(latinized) == 1


def normalize_form(text: str) -> str:
    text = text.strip().strip('"')
    text = unicodedata.normalize("NFC", text)
    text = remove_unsafe_chars(text)
    return text


def generate_export_lines() -> Generator[tuple[str, int], None, None]:
    block_groups()
    block_phrases()
    block_forms()
    with engine.begin() as conn:
        raw_mappings = dict(all_mappings(conn))
        log.info("Loaded %d name mappings", len(raw_mappings))
        mappings: dict[str, set[str]] = {}
        log.info("Normalizing name mappings...")
        for group, aliases in raw_mappings.items():
            normed = [normalize_form(a) for a in aliases]
            mappings[group] = {n for n in normed if len(n)}
        log.info("Deduplicating name groups...")
        by_names: dict[str, set[str]] = defaultdict(set)
        for group, aliases in mappings.items():
            for alias in aliases:
                by_names[alias].add(group)
        log.info("%d unique names, deduplicating...", len(by_names))
        for ngroup, naliases in sorted(mappings.items()):
            other_groups = set()
            for alias in naliases:
                other_groups.update(by_names[alias])
            other_groups.discard(ngroup)
            for ogroup in other_groups:
                oaliases = mappings.get(ogroup, set())
                if naliases.issubset(oaliases):
                    # print("Removing: ", nqid, "->", oqid, ": ", naliases)
                    mappings.pop(ngroup, None)

        written = 0
        forms_written = 0
        for group, forms in sorted(mappings.items()):
            if len(forms) < 2:
                continue
            if can_translit_match(forms):
                # log.info("Skipping mapping for: %r", forms)
                continue
            written += 1
            forms_written += len(forms)
            fstr = ", ".join(sorted(forms))
            yield f"{fstr} => {group}\n", len(forms)


CSV_COLUMNS = [
    "group",
    "classes",
    "native_langs",
    "form",
    "script",
    "langs",
    "source",
    "scheme",
]
SOURCE_LETTERS = [
    (SOURCE_LABEL, "L"),
    (SOURCE_ALIAS, "A"),
    (SOURCE_NATIVE, "N"),
    (SOURCE_TRANSLIT, "T"),
]


def source_letters(source: int) -> str:
    return "".join(letter for flag, letter in SOURCE_LETTERS if source & flag)


def write_csv(fh: IO[str]) -> tuple[int, int]:
    """Write the per-form training CSV; return (items, rows) written.

    One row per stored item and form, with the raw Wikidata language
    codes the form appears under as a space-joined list. Forms skipped in
    the mapping table and blocklisted groups and phrases are left out;
    no further deduplication happens here.
    """
    block_groups()
    block_phrases()
    items = 0
    rows = 0
    writer = csv.writer(fh)
    writer.writerow(CSV_COLUMNS)
    with engine.begin() as conn:
        skipped = skipped_pairs(conn)
        for group, classes, names, schemes in iter_items(conn):
            items += 1
            native_langs: set[str] = set()
            for langs in names.values():
                native_langs.update(
                    lang for lang, bits in langs.items() if bits & SOURCE_NATIVE
                )
            for form, langs in sorted(names.items()):
                if (form, group) in skipped:
                    continue
                source = 0
                for bits in langs.values():
                    source |= bits
                writer.writerow(
                    [
                        group,
                        " ".join(classes),
                        " ".join(sorted(native_langs)),
                        form,
                        form_script(form) or "",
                        " ".join(sorted(langs)),
                        source_letters(source),
                        schemes.get(form, ""),
                    ]
                )
                rows += 1
    return items, rows
