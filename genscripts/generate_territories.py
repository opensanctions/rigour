import os
from pathlib import Path
from yaml import safe_load as yaml_load
import logging
from typing import Any, Dict, Generator, Set
from normality import latinize_text, squash_spaces
from rigour.text.scripts import is_latin, can_latinize
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString, DoubleQuotedScalarString

from rigour.ids.wikidata import is_qid
from rigour.langs import iso_639_alpha3
from rigour.territories.territory import Territory
from rigour.territories.util import clean_code, clean_codes
from genscripts.util import write_jsonl, norm_string, RESOURCES_PATH, RUST_DATA_PATH

log = logging.getLogger(__name__)
yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=2, offset=2)


TERRITORIES_DIR = RESOURCES_PATH / "territories"
TEMPLATE = """from typing import Dict, Any

TERRITORIES: Dict[str, Any] = %r
"""


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


def rewrite_territory(global_names: Dict[str, Set[str]], file_path: Path) -> None:
    cc = clean_code(file_path.stem).upper()
    with open(file_path, "r", encoding="utf-8") as f:
        terr = yaml.load(f)
    if "summary" in terr:
        terr["summary"] = FoldedScalarString(terr.get("summary"))
    if "parent" in terr and terr["parent"] == "no":
        terr["parent"] = DoubleQuotedScalarString(terr.get("parent"))

    labels = set()

    # Process the territory data as needed
    used_names = set([loc_norm(cc)])
    name = terr.get("name")
    if name in labels:
        labels.remove(name)
    if name is not None:
        used_names.add(loc_norm(name))
    full_name = terr.get("full_name")
    if full_name in labels:
        labels.remove(full_name)
    if full_name is not None:
        used_names.add(loc_norm(full_name))
    iso3 = terr.get("alpha3")
    if iso3 is not None:
        used_names.add(loc_norm(iso3))
    if "names_strong" in terr:
        strong = terr["names_strong"]
        for name in strong:
            name = str(name)
            if name in labels:
                labels.remove(name)
    else:
        terr["names_strong"] = CommentedSeq()
        terr["names_strong"].append(name)
    for name in terr["names_strong"]:
        name_norm = loc_norm(name)
        if name_norm in used_names:
            terr["names_strong"].remove(name)
        used_names.add(name_norm)
    for i, name in enumerate(terr["names_strong"]):
        if is_latin(name):
            continue
        if can_latinize(name):
            latin = latinize_text(name)
            terr["names_weak"].yaml_add_eol_comment(latin, i)

    if "names_weak" in terr:
        weak = terr["names_weak"]
        for name in weak:
            name = str(name)
            if name in labels:
                labels.remove(name)
    else:
        terr["names_weak"] = CommentedSeq()
    for label in labels:
        terr["names_weak"].append(label)
    for name in terr["names_weak"]:
        norm_name = loc_norm(name)
        if norm_name in used_names:
            print("Remove", name)
            terr["names_weak"].remove(name)
        used_names.add(norm_name)
    for i, name in enumerate(terr["names_weak"]):
        if is_latin(name):
            continue
        if can_latinize(name):
            latin = latinize_text(name)
            terr["names_weak"].yaml_add_eol_comment(latin, i)

    all_labels = set()
    all_labels.add(terr.get("name"))
    all_labels.add(terr.get("full_name"))
    all_labels.update([str(n) for n in terr["names_strong"]])
    all_labels.update([str(n) for n in terr["names_weak"]])
    for gname in all_labels:
        if gname is None:
            continue
        normed = squash_spaces(gname.casefold())
        if normed is None:
            continue
        if normed not in global_names:
            global_names[normed] = set()
        global_names[normed].add(cc)

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(terr, f)


def rewrite_territories():
    global_names: Dict[str, Set[str]] = {}
    for file_path in territory_files():
        rewrite_territory(global_names, file_path)
    for normed, codes in global_names.items():
        if len(codes) < 2:
            continue
        codes = sorted(codes)
        print(f"{normed} => {', '.join(codes)}")


def update_data() -> None:
    raw_territories: Dict[str, Any] = {}
    territories: Dict[str, Territory] = {}
    seen_codes: Set[str] = set()
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
                names = set(norm_string(name) for name in data["names_strong"])
                data["names_strong"] = sorted(names)
            if "names_weak" in data:
                names = set(norm_string(name) for name in data["names_weak"])
                data["names_weak"] = sorted(names)
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
