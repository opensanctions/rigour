from enum import Enum
from mystace import create_mustache_tree
from mystace.mustache_tree import MustacheTreeNode
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString
from genscripts.util import CODE_PATH, RESOURCES_PATH


OPENCAGE_YAML_PATH = RESOURCES_PATH / "addresses" / "opencage_worldwide.yaml"
FORMATS_DEST_PATH = CODE_PATH / "addresses" / "formats.yml"


# these don't exist in the rigour yaml -- by design?
DROP_VARS = {"hamlet", "place"}

SPACE_LITERAL = " "
PRIMARY_OR_MUSTACHE_LITERAL = "||"
OR_JINJA_LITERAL = " or "

class M2JType(Enum):
    ROOT = -1
    LITERAL = 0
    SECTION = 2
    INVERTED_SECTION = 3
    PARTIAL = 5
    VARIABLE = 6
    VARIABLE_RAW = 7
    OR = 8
    CONCAT = 9


class M2JNode:
    tag_type: M2JType
    data: str
    children: list['M2JNode']

    def __init__(self, tag_type: M2JType, data: str = "", children: list['M2JNode'] | None = None):
        self.tag_type = tag_type
        self.data = data
        self.children = children if children is not None else []

    def __repr__(self) -> str:
        if self.data:
            return f"<{self.__class__.__name__}: {self.tag_type}, {self.data!r}>"
        return f"<{self.__class__.__name__}: {self.tag_type}>"


def _convert_tree(t: MustacheTreeNode) -> M2JNode:
    j = M2JNode(tag_type=M2JType.ROOT, data=t.data)

    frontier = [(n, j) for n in t.children or []]
    while frontier:
        n, curr = frontier.pop(0)
        curr.children.append(M2JNode(tag_type=M2JType(n.tag_type.value), data=n.data))
        if n.children:
            for c in n.children:
                frontier.append((c, curr.children[-1]))

    return j


def split_space(t: M2JNode):
    """
    Find any literal nodes that contain spaces.
    Trim the spaces from the beginning and end of the literal when the literal is up against a boundary.
    """

    def _can_split(n: M2JNode):
        return n.tag_type == M2JType.LITERAL and n.data != '\n'

    def _is_boundary(n: M2JNode):
        return n.tag_type in {M2JType.OR} or n.tag_type == M2JType.LITERAL and n.data == '\n'

    if not t.children:
        return

    i = 0
    while i < len(t.children):
        n = t.children[i]

        if n.children:
            split_space(n)

        if not _can_split(n) or SPACE_LITERAL not in n.data:
            i += 1
            continue

        curr = n.data
        assert SPACE_LITERAL in curr, f"Expected {SPACE_LITERAL} in {curr}"

        if i == 0 or _is_boundary(t.children[i - 1]):
            curr = curr.lstrip(SPACE_LITERAL)

        if i == len(t.children) - 1 or _is_boundary(t.children[i + 1]):
            curr = curr.rstrip(SPACE_LITERAL)

        if curr:
            n.data = curr
            i += 1
        else:
            t.children.pop(i)


def split_or(t: M2JNode):
    """
    Split any literal nodes that contain the OR mustache literal into separate nodes.
    """

    def _is_boundary(n: M2JNode):
        """
        We stop backtracking or looking ahead when we hit a boundary.
        """
        return n.tag_type != M2JType.LITERAL or n.data == '\n'

    if not t.children:
        return

    i = 0
    while i < len(t.children):
        n = t.children[i]

        if n.children:
            split_or(n)

        if _is_boundary(n) or PRIMARY_OR_MUSTACHE_LITERAL not in n.data:
            i += 1
            continue

        assert n.data.count(PRIMARY_OR_MUSTACHE_LITERAL) == 1, f"Expected 1 {PRIMARY_OR_MUSTACHE_LITERAL} in {n.data}"

        t.children.pop(i)

        idx = n.data.index(PRIMARY_OR_MUSTACHE_LITERAL)
        left = n.data[:idx].rstrip(SPACE_LITERAL)
        right = n.data[idx + len(PRIMARY_OR_MUSTACHE_LITERAL) :].lstrip(SPACE_LITERAL)

        if left:
            t.children.insert(i, M2JNode(tag_type=M2JType.LITERAL, data=left))
            i += 1

        t.children.insert(i, M2JNode(tag_type=M2JType.OR, data=PRIMARY_OR_MUSTACHE_LITERAL))
        i += 1

        if right:
            t.children.insert(i, M2JNode(tag_type=M2JType.LITERAL, data=right))
            i += 1


def drop_vars_and_simplify(t: M2JNode):
    def _is_boundary(n: M2JNode):
        return n.tag_type in {M2JType.OR} or n.tag_type == M2JType.LITERAL and n.data == '\n'

    def _is_simple_section(n: M2JNode):
        return n.tag_type in {M2JType.SECTION, M2JType.INVERTED_SECTION} and all(
            c.tag_type in {M2JType.VARIABLE, M2JType.VARIABLE_RAW, M2JType.LITERAL} for c in n.children
        )

    if not t.children:
        return

    i = 0
    while i < len(t.children):
        c = t.children[i]
        drop_vars_and_simplify(c)

        is_against_boundary = (
            (i > 0 and _is_boundary(t.children[i - 1]))
            or (i + 1 < len(t.children) and _is_boundary(t.children[i + 1]))
            or i == 0
            or i == len(t.children) - 1
        )

        # remove empty sections
        if c.tag_type == M2JType.SECTION and not c.children:
            t.children.pop(i)
            continue

        is_whitespace = c.tag_type == M2JType.LITERAL and c.data.strip(SPACE_LITERAL) == ""
        if is_whitespace and is_against_boundary:
            # remove empty literals
            t.children.pop(i)
            continue

        if c.tag_type == M2JType.OR and is_against_boundary:
            # remove dangling OR
            t.children.pop(i)
            continue

        if c.tag_type in {M2JType.VARIABLE, M2JType.VARIABLE_RAW} and c.data in DROP_VARS:
            # remove dropped variables
            t.children.pop(i)
            if i > 0:
                i -= 1
            continue

        # inline sections that contain only variables and literals
        if _is_simple_section(c):
            t.children.pop(i)

            j = i
            for section_child in c.children:
                t.children.insert(j, section_child)
                j += 1

            # merge literals at the beginning of the section
            if (
                i > 0
                and t.children[i - 1].tag_type == M2JType.LITERAL
                and t.children[i].tag_type == M2JType.LITERAL
                and not _is_boundary(t.children[i - 1])
            ):
                t.children[i - 1].data += t.children[i].data
                t.children.pop(i)
                i -= 1

            # merge literals at the end of the section
            if (
                j > 0
                and t.children[j - 1].tag_type == M2JType.LITERAL
                and t.children[j].tag_type == M2JType.LITERAL
                and not _is_boundary(t.children[j])
            ):
                t.children[j - 1].data += t.children[j].data
                t.children.pop(j)

        i += 1


def split_string_concat(t: M2JNode):
    if not t.children:
        return

    for c in t.children:
        split_string_concat(c)

    # outside of sections, we don't need to handle concats around ORs
    if t.tag_type not in {M2JType.SECTION, M2JType.INVERTED_SECTION}:
        return

    args: list[list[M2JNode]] = [[]]
    for c in t.children:
        if c.tag_type == M2JType.OR:
            args.append([])
        else:
            args[-1].append(c)

    # if we have only one argument, we can just return
    if len(args) == 1:
        return

    t.children = []
    for i, arg in enumerate(args):
        if len(arg) == 1:
            t.children.append(arg[0])
        else:
            new_node = M2JNode(tag_type=M2JType.CONCAT, children=arg)
            t.children.append(new_node)
        if i < len(args) - 1:
            t.children.append(M2JNode(tag_type=M2JType.OR))

    return t


def jinja_tree_to_template(t: M2JNode, depth: int = 0) -> str:
    if t.tag_type == M2JType.ROOT:
        template = ""
        for c in t.children:
            template += jinja_tree_to_template(c, depth + 1)
        return template
    elif t.tag_type in {M2JType.SECTION, M2JType.INVERTED_SECTION}:
        assert depth < 2, f'Too many nested sections: {depth}'
        template = "{{"
        for c in t.children:
            template += jinja_tree_to_template(c, depth + 1)
        template += "}}"
        return template
    elif t.tag_type == M2JType.CONCAT:
        formatted_val = ' ~ '.join([jinja_tree_to_template(c, depth + 1) for c in t.children])
        vars = [c for c in t.children if c.tag_type in {M2JType.VARIABLE, M2JType.VARIABLE_RAW}]
        return f'format_if({formatted_val}, {", ".join([c.data for c in vars])})'
    elif t.tag_type == M2JType.LITERAL:
        if depth < 2:
            return t.data
        else:
            return f"'{t.data}'"
    elif t.tag_type in {M2JType.VARIABLE, M2JType.VARIABLE_RAW}:
        if depth < 2:
            return '{{' + t.data + '}}'
        else:
            return t.data
    elif t.tag_type == M2JType.OR:
        return OR_JINJA_LITERAL
    else:
        raise ValueError(f"Got unexpected tag type {t.tag_type}")


def mustache_to_jinja(template: str) -> str:
    jinja_template = ""

    tree = _convert_tree(create_mustache_tree(template))
    split_or(tree)
    split_space(tree)
    drop_vars_and_simplify(tree)
    split_string_concat(tree)

    jinja_template = jinja_tree_to_template(tree)
    return collapse_newlines(jinja_template)


def collapse_newlines(text: str) -> str:
    prev = ""
    while prev != text:
        prev = text
        text = text.replace("\n\n", "\n").replace("\n ", "\n").strip()
    return text


def update_mustache_field(yaml_obj: dict, field: str) -> LiteralScalarString:
    current_anchor = yaml_obj[field].yaml_anchor()
    txt = mustache_to_jinja(str(yaml_obj[field]))
    if not txt.endswith("\n"):
        txt += "\n"
    yaml_obj[field] = LiteralScalarString(txt)
    if current_anchor is not None:
        yaml_obj[field].yaml_set_anchor(current_anchor.value, always_dump=current_anchor.always_dump)
    return yaml_obj[field]


def normalize_add_component(country: CommentedMap) -> str | None:
    trailing_comment: str | None = None

    # grab and detach the trailing comment (if any)
    if len(country.ca.items) > 0:
        last_key = list(country.keys())[-1]
        last_comment = country.ca.items[last_key][2]
        if last_comment is not None:
            trailing_comment = country.ca.items[last_key][2].value
        del country.ca.items[last_key]

        if trailing_comment:
            if trailing_comment.startswith("\n\n"):
                trailing_comment = f"\n{trailing_comment[2:]}"
            trailing_comment = "\n".join([c.lstrip("# ") for c in trailing_comment.split("\n")])
            trailing_comment.rstrip("\n")

    # build the nested mapping
    if "add_component" in country:
        add_component_val = country["add_component"]
        assert isinstance(
            add_component_val, str
        ), f"Invalid add_component type: {type(add_component_val)} for {country}"
        fields = add_component_val.split("=")

        assert len(fields) == 2, f"Invalid add_component format: {add_component_val} for {country}"
        k, v = fields
        ac_map = CommentedMap({k: v})
    else:
        ac_map = CommentedMap()

    if "change_country" in country:
        ac_map["country"] = country.pop("change_country")

    country["add_component"] = ac_map

    return trailing_comment

 
def load_address_formats_from_opencage() -> None:
    """
    Load address formats from OpenCageData's address-formatting repo.
    Converts the mustache templates to jinja2 format.
    Uses the following conventions for mustache to jinja2 conversion:
    - literals between variables in a `first` block explicitly concatenated with ~
    - relies on a macro "format_if" to handle concatenated strings in `first` blocks that contain only delimiters.
        - e.g. if we have {{#first}} {{{house_number}}}, {{{road}}} || {{{suburb}}} {{/first}}
        - we only want to use {{{house_number}}}, {{{road}}} if both `house_number` and `road` are non-empty.
    """
    if not OPENCAGE_YAML_PATH.exists():
        raise FileNotFoundError(f"OpenCage YAML file not found ({OPENCAGE_YAML_PATH}). Please run make fetch-opencage-addresses to download.")

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    yaml_obj = yaml.load(OPENCAGE_YAML_PATH.read_text())

    orig_fields_by_value = {}
    new_fields = {}
    attach_trailing = None

    for k, v in yaml_obj.items():
        if attach_trailing:
            yaml_obj.yaml_set_comment_before_after_key(k, before=attach_trailing, after=None)
            attach_trailing = None

        if k.startswith("generic") or k.startswith("fallback"):
            orig_fields_by_value[v] = k
            new_fields[k] = update_mustache_field(yaml_obj, k)
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                # update references to the original mustache fields for countries that reference them.
                if isinstance(v2, LiteralScalarString) and v2 in orig_fields_by_value:
                    v[k2] = new_fields[orig_fields_by_value[v2]]

                # one-off templates need to be converted to jinja.
                elif k2 in {"address_template", "fallback_template"}:
                    update_mustache_field(v, k2)

            if "change_country" in v or "add_component" in v:
                attach_trailing = normalize_add_component(v)


    with open(FORMATS_DEST_PATH, "w") as outfile:
        outfile.write("# Derived from: https://github.com/OpenCageData/address-formatting\n")
        yaml.dump(yaml_obj, outfile)

 
if __name__ == "__main__":
    load_address_formats_from_opencage()

