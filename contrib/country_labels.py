# pip install ruamel.yaml
from normality import slugify_text, latinize_text, squash_spaces
from normality.cleaning import remove_unsafe_chars
from rigour.names.pick import pick_case
from rigour.text.scripts import is_latin, can_latinize
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString
from pathlib import Path


# PATH = "/Users/pudo/Code/countrynames/countrynames/data.yaml"
TERR_DIR = Path(__file__).parent.parent / "resources/territories"

yaml = YAML()
yaml.default_flow_style = False
yaml.indent(mapping=2, sequence=2, offset=2)


# def load_country_labels():
#     with open(PATH, "r", encoding="utf-8") as f:
#         data = yaml.load(f)
#     return data


# cc_labels = load_country_labels()
for terr_file in sorted(TERR_DIR.glob("*.yml")):
    with open(terr_file, "r", encoding="utf-8") as f:
        cc = slugify_text(terr_file.stem).upper()
        terr = yaml.load(f)
        if "summary" in terr:
            terr["summary"] = FoldedScalarString(terr.get("summary"))

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
        name = terr.get("name")
        if name in labels:
            labels.remove(name)
        full_name = terr.get("full_name")
        if full_name in labels:
            labels.remove(full_name)
        if "names_strong" in terr:
            strong = terr["names_strong"]
            for name in strong:
                name = str(name)
                if name in labels:
                    labels.remove(name)
        else:
            terr["names_strong"] = CommentedSeq()
            terr["names_strong"].append(name)
        for i, name in enumerate(terr["names_strong"]):
            if is_latin(name):
                continue
            if can_latinize(name):
                latin = latinize_text(name)
                terr["names_weak"].yaml_add_eol_comment(latin, i)

        strong_names = list(terr["names_strong"])
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
            if name in strong_names:
                terr["names_weak"].remove(name)
        for i, name in enumerate(terr["names_weak"]):
            if is_latin(name):
                continue
            if can_latinize(name):
                latin = latinize_text(name)
                terr["names_weak"].yaml_add_eol_comment(latin, i)

    with open(terr_file, "w", encoding="utf-8") as f:
        yaml.dump(terr, f)
