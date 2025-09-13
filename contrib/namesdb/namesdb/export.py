import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, Iterable, Set
from normality import ascii_text
from rigour.text.scripts import can_latinize

from namesdb.cleanup import block_groups, block_phrases
from namesdb.db import all_mappings, engine

log = logging.getLogger(__name__)


def can_translit_match(forms: Iterable[str]) -> bool:
    latinized: Set[str] = set()
    for form in forms:
        if not can_latinize(form):
            return False
        ascii = ascii_text(form)
        if len(form) > 1 and len(ascii) == 0:
            return False
        latinized.add(ascii)
    return len(latinized) == 1


def dump_file_export(path: Path):
    log.info("Exporting namesdb mappings to %r", path.as_posix())
    block_groups()
    block_phrases()
    with engine.begin() as conn:
        mappings = dict(all_mappings(conn))
        log.info("Loaded %d name mappings", len(mappings))
        # print("Deduplicating name QIDs...")
        by_names: Dict[str, Set[str]] = defaultdict(set)
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
        with open(path, "w") as fh:
            for group, forms in sorted(mappings.items()):
                if len(forms) < 2:
                    continue
                if can_translit_match(forms):
                    # log.info("Skipping mapping for: %r", forms)
                    continue
                written += 1
                fstr = ", ".join(sorted(forms))
                fh.write(f"{fstr} => {group}\n")

        log.info("Wrote %d mappings to %r", written, path.as_posix())
