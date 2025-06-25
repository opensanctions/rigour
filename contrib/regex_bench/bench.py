import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import click

from rigour.names.person import load_person_names_mapping
from rigour.names.symbol import Symbol
from rigour.names.tagging import _common_symbols
from rigour.text.dictionary import Normalizer, Scanner as REScanner
from rigour.names.tagging import Tagger as RETagger
from rigour.names import prenormalize_name

log = logging.getLogger(__name__)
InPath = click.Path(dir_okay=False, readable=True, path_type=Path, allow_dash=True)


def load_tagger_class(name: str) -> Type[RETagger]:
    """Load a scanner class by name."""
    if name == "re2":
        from impl.dictionary_re2 import Tagger
    elif name == "re":
        Tagger = RETagger
    elif name == "hyperscan":
        from impl.dictionary_hyperscan import Tagger
    else:
        raise ValueError(f"Unknown scanner type: {name}")
    return Tagger


def _get_person_name_mapping(normalizer: Normalizer) -> Dict[str, List[Symbol]]:
    from rigour.data.names.data import PERSON_SYMBOLS

    mapping = _common_symbols(normalizer)
    for key, values in PERSON_SYMBOLS.items():
        sym = Symbol(Symbol.Category.SYMBOL, key.upper())
        nkey = normalizer(key)
        if nkey is not None:
            mapping[nkey].append(Symbol(Symbol.Category.SYMBOL, key))
        for value in values:
            nvalue = normalizer(value)
            if nvalue is None:
                continue
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    name_mapping = load_person_names_mapping(normalizer=normalizer)
    for name, qids in name_mapping.items():
        for qid in qids:
            sym = Symbol(Symbol.Category.NAME, int(qid[1:]))
            mapping[name].append(sym)

    print("Loaded person tagger (%s terms).", len(mapping))
    return mapping


def normalizer(text: Optional[str]) -> Optional[str]:
    """Normalize a name by removing extra spaces and converting to lowercase."""
    if text is None:
        return None
    text = prenormalize_name(text)
    if not text:
        return None
    return " ".join(text.split())


@click.group()
def cli() -> None:
    pass


@cli.command("normalize")
@click.argument("names_path", type=InPath)
def normalize(names_path: Path) -> None:
    """Normalize names from a file."""
    with open(names_path, "r", encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if not name:
                continue
            normalized_name = normalizer(name)
            if normalized_name:
                print(normalized_name)


@cli.command("bench")
@click.argument("library", type=str)
@click.argument("names_path", type=InPath)
@click.option("--verbose", is_flag=True, help="Print out each line and its results")
def bench(library: str, names_path: Path, verbose: bool) -> None:
    Tagger = load_tagger_class(library)
    tag = Tagger(_get_person_name_mapping(normalizer))
    if library == "hyperscan":
        tag.load()
    with open(names_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx > 0 and idx % 1000 == 0:
                print(f"Processed {idx} lines")
            tag_result = tag(line.strip())
            if verbose:
                print(f"{line.strip()} -> {tag_result}")



@cli.command("demo")
@click.argument("library", type=str)
@click.argument("demo_string", type=str)
def demo(library: str, demo_string: str) -> None:
    print("Loading tagger")
    Tagger = load_tagger_class(library)
    print("Instantiating tagger")
    tag = Tagger(_get_person_name_mapping(normalizer))
    if library == "hyperscan":
        tag.load()
    print("Tagging demo string")
    print(tag(normalizer(demo_string)))


@cli.command("compile-hyperscan")
def compile_hyperscan() -> None:
    """Compile the hyperscan database."""
    from impl.dictionary_hyperscan import Tagger

    tagger = Tagger(_get_person_name_mapping(normalizer))
    tagger.compile()

if __name__ == "__main__":
    cli()
