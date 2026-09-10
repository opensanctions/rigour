import logging
import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

from normality import latinize_text, squash_spaces
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, FoldedScalarString
from yaml import safe_load as yaml_load

from genscripts.util import RESOURCES_PATH, RUST_DATA_PATH, norm_string, write_jsonl
from rigour.ids.wikidata import is_qid
from rigour.langs import iso_639_alpha3
from rigour.territories.territory import Territory
from rigour.territories.util import clean_code, clean_codes, normalize_territory_name
from rigour.text.scripts import can_latinize, is_latin

log = logging.getLogger(__name__)
yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=2, offset=2)


TERRITORIES_DIR = RESOURCES_PATH / "territories"


def territory_files() -> Generator[Path, None, None]:
    # Sort the listdir result: os.listdir returns filenames in
    # filesystem-dependent order (alphabetical on macOS APFS, inode
    # order on Linux ext4), which leaks into rust/data/territories/
    # data.jsonl and breaks CI's no-diff check.
    for filename in sorted(os.listdir(TERRITORIES_DIR)):
        if filename.endswith(".yml"):
            yield Path(TERRITORIES_DIR / filename).resolve()


def loc_norm(text: str) -> str:
    """Normalize text for local use."""
    if not text:
        return ""
    return squash_spaces(text.lower())


NAME_KEYS = ("names_strong", "names_weak", "places")


def _clean_names(terr: Any, key: str, used_names: set[str], create: bool) -> None:
    """Dedupe one name list in place against names already used by the territory.

    Entries whose local normalisation is already in `used_names` are dropped;
    surviving non-Latin entries get a latinised end-of-line comment.
    """
    if key not in terr:
        if not create:
            return
        terr[key] = CommentedSeq()
    names = terr[key]
    for name in list(names):
        name_norm = loc_norm(str(name))
        if name_norm in used_names:
            print("Remove", key, name)
            names.remove(name)
            continue
        used_names.add(name_norm)
    for i, name in enumerate(names):
        if is_latin(name):
            continue
        if can_latinize(name):
            latin = latinize_text(name)
            names.yaml_add_eol_comment(latin, i)


def rewrite_territory(file_path: Path) -> None:
    cc = clean_code(file_path.stem).upper()
    with open(file_path, "r", encoding="utf-8") as f:
        terr = yaml.load(f)
    if "summary" in terr:
        terr["summary"] = FoldedScalarString(terr.get("summary"))
    if "parent" in terr and terr["parent"] == "no":
        terr["parent"] = DoubleQuotedScalarString(terr.get("parent"))

    used_names = {loc_norm(cc)}
    name = terr.get("name")
    if name is not None:
        used_names.add(loc_norm(name))
    full_name = terr.get("full_name")
    if full_name is not None:
        used_names.add(loc_norm(full_name))
    iso3 = terr.get("alpha3")
    if iso3 is not None:
        used_names.add(loc_norm(iso3))
    if "names_strong" not in terr:
        terr["names_strong"] = CommentedSeq()
        terr["names_strong"].append(name)
    _clean_names(terr, "names_strong", used_names, create=True)
    _clean_names(terr, "names_weak", used_names, create=True)
    _clean_names(terr, "places", used_names, create=False)

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(terr, f)


def rewrite_territories() -> None:
    for file_path in territory_files():
        rewrite_territory(file_path)


def check_name_collisions(claims: dict[str, set[tuple[str, str]]]) -> None:
    """Fail when a normalised name is claimed by more than one territory.

    The lookup in `rigour.territories.lookup` resolves a name to exactly one
    territory, so a shared name would silently pick a winner.

    Args:
        claims: Normalised name mapped to the `(code, kind)` pairs claiming it,
            where `kind` is the YAML key the name came from.

    Raises:
        RuntimeError: If any name is claimed by two or more territory codes.
    """
    conflicts = 0
    for normed, owners in sorted(claims.items()):
        codes = {code for code, _ in owners}
        if len(codes) < 2:
            continue
        conflicts += 1
        detail = ", ".join(f"{code} ({kind})" for code, kind in sorted(owners))
        print(f"Name collision: {normed!r} => {detail}")
    if conflicts > 0:
        raise RuntimeError(f"{conflicts} territory name collisions found")


def update_data() -> None:
    raw_territories: dict[str, Any] = {}
    territories: dict[str, Territory] = {}
    claims: dict[str, set[tuple[str, str]]] = {}
    seen_codes: set[str] = set()
    for source_file in territory_files():
        filename = os.path.basename(source_file)
        code = clean_code(filename.replace(".yml", ""))
        if code in seen_codes:
            print(f"Duplicate code: {code}")
            continue
        seen_codes.add(code)
        with open(source_file, "r", encoding="utf-8") as ufh:
            data = yaml_load(ufh.read())
            data["code"] = norm_string(code)
            data["name"] = norm_string(data["name"])
            if "full_name" in data:
                data["full_name"] = norm_string(data["full_name"])
            if "region" in data:
                data["region"] = norm_string(data["region"])
            if "subregion" in data:
                data["subregion"] = norm_string(data["subregion"])
            if "in_sentence" in data:
                data["in_sentence"] = norm_string(data["in_sentence"])
            if "names_strong" in data:
                names = {norm_string(name) for name in data["names_strong"]}
                data["names_strong"] = sorted(names)
            for key in NAME_KEYS:
                if key in data:
                    names = {norm_string(name) for name in data[key]}
                    data[key] = sorted(names)
            data["other_codes"] = clean_codes(data.get("other_codes", []))
            for other in data["other_codes"]:
                if other in territories:
                    log.warning("Duplicate code: %s", other)
            if len(data["other_codes"]) == 0:
                data.pop("other_codes")
            data["claims"] = clean_codes(data.get("claims", []))
            if len(data["claims"]) == 0:
                data.pop("claims")
            data["see"] = clean_codes(data.get("see", []))
            if len(data["see"]) == 0:
                data.pop("see")

            if "langs" in data:
                langs = set()
                for lang in data["langs"]:
                    lang_code = iso_639_alpha3(lang)
                    if lang_code is None or lang_code != lang:
                        log.warning(
                            "Invalid language code [%r]: %s (%s)",
                            source_file.as_posix(),
                            lang,
                            lang_code,
                        )
                        continue
                    langs.add(lang_code)
                data["langs"] = sorted(langs)
            raw_territories[code] = data
            territories[code] = Territory(territories, code, data)
            labelled = [("name", data["name"]), ("full_name", data.get("full_name"))]
            for key in NAME_KEYS:
                labelled.extend((key, name) for name in data.get(key, []))
            for kind, label in labelled:
                if label is None:
                    continue
                normed = normalize_territory_name(label)
                if len(normed) == 0:
                    continue
                claims.setdefault(normed, set()).add((code, kind))

    check_name_collisions(claims)

    for terr in territories.values():
        assert terr.name is not None, f"Must have a name: {terr.code}"
        assert terr.code is not None, f"Missing code: {terr.name}"
        assert terr.qid is not None, f"Missing QID: {terr.code}"
        assert is_qid(terr.qid), f"Invalid QID: {terr.code}"
        for other_qid in terr.other_qids:
            assert is_qid(other_qid), f"Invalid QID: {other_qid}"
        if terr._parent is not None:
            assert terr._parent != terr.code, f"Cannot be its own parent: {terr.code}"
            if terr._parent not in territories:
                msg = "Invalid parent: %s (country: %r)" % (terr._parent, terr.code)
                raise RuntimeError(msg)

        for successor in terr._successors:
            if successor not in territories:
                msg = "Invalid successor: %s (country: %r)" % (successor, terr.code)
                raise RuntimeError(msg)

        for claim in terr._claims:
            if claim not in territories:
                msg = "Invalid claim: %s (country: %r)" % (claim, terr.code)
                raise RuntimeError(msg)

        for see in terr._see:
            if see not in territories:
                msg = "Invalid see: %s (country: %r)" % (see, terr.code)
                raise RuntimeError(msg)

        if terr.is_country and not terr.is_jurisdiction:
            msg = "Country is not a jurisdiction: %r" % terr.code
            raise RuntimeError(msg)

    out_path = RUST_DATA_PATH / "territories" / "data.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_path, raw_territories.values())


if __name__ == "__main__":
    rewrite_territories()
    update_data()
