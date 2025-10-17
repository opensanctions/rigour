# pip install ruamel.yaml
from typing import Optional
from normality import slugify_text, latinize_text, squash_spaces
from rigour.text.scripts import is_latin, can_latinize
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString, DoubleQuotedScalarString
from pathlib import Path


# PATH = "/Users/pudo/Code/countrynames/countrynames/data.yaml"
TERR_DIR = Path(__file__).parent.parent / "resources/territories"

yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=2, offset=2)


def global_norm(text: str) -> Optional[str]:
    """Normalize text for global use."""
    # return normalize(text, lowercase=True)
    return squash_spaces(text.casefold())


def loc_norm(text: str) -> str:
    """Normalize text for local use."""
    if not text:
        return ""
    return squash_spaces(text.lower())


# def load_country_labels():
#     with open(PATH, "r", encoding="utf-8") as f:
#         data = yaml.load(f)
#     return data

global_names = {}

# cc_labels = load_country_labels()
for terr_file in sorted(TERR_DIR.glob("*.yml")):
    with open(terr_file, "r", encoding="utf-8") as f:
        cc = slugify_text(terr_file.stem).upper()
        terr = yaml.load(f)
        if "summary" in terr:
            terr["summary"] = FoldedScalarString(terr.get("summary"))
        if "parent" in terr and terr["parent"] == "no":
            terr["parent"] = DoubleQuotedScalarString(terr.get("parent"))

        # lower = {}
        # for name in cc_labels.get(cc, []):
        #     cname = squash_spaces(remove_unsafe_chars(name))
        #     lname = cname.lower()
        #     if lname not in lower:
        #         lower[lname] = []
        #     lower[lname].append(cname)

        labels = set()
        # for versions in lower.values():
        #     version = pick_case(versions)
        #     if len(versions) > 1:
        #         print("XXX", cc, versions, "->", version)
        #     labels.add(version)

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
            normed = global_norm(gname)
            if normed is None:
                continue
            if normed not in global_names:
                global_names[normed] = set()
            global_names[normed].add(cc)

    with open(terr_file, "w", encoding="utf-8") as f:
        yaml.dump(terr, f)

for normed, codes in global_names.items():
    if len(codes) < 2:
        continue
    codes = sorted(codes)
    print(f"{normed} => {', '.join(codes)}")
