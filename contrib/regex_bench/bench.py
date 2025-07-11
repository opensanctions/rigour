import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import click

from rigour.names.name import Name
from rigour.names.person import load_person_names_mapping
from rigour.names.symbol import Symbol
from rigour.names.tagging import (
    TaggerType,
    _common_symbols,
    tag_org_name,
    tag_person_name,
)
from rigour.names.tokenize import tokenize_name
from rigour.text.dictionary import Normalizer
from rigour.names.tagging import RETagger, AhoCorTagger, Tagger
from rigour.names import prenormalize_name

log = logging.getLogger(__name__)
InPath = click.Path(dir_okay=False, readable=True, path_type=Path, allow_dash=True)


def get_tagger_type(library: str) -> TaggerType:
    """Get the tagger type based on the library name."""
    if library == "re":
        return TaggerType.RE
    elif library == "ahocorasick":
        return TaggerType.AHO_COR
    else:
        raise ValueError(f"Unknown tagger type: {library}")


def normalizer(text: Optional[str]) -> Optional[str]:
    """Normalize a name by removing extra spaces and converting to lowercase."""
    if text is None:
        return None
    text = prenormalize_name(text)
    if not text:
        return None
    return " ".join(tokenize_name(text))


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


def fmt_tag_result(tag_result: List[Tuple[str, Symbol]]) -> str:
    return str(sorted(tag_result, key=lambda x: str(x.id)))


@cli.command("tag-person")
@click.argument("library", type=str)
@click.argument("names_path", type=InPath)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print out each line and its results - useful for comparison",
)
def tag_person(library: str, names_path: Path, verbose: bool) -> None:
    with open(names_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx > 0 and idx % 1000 == 0:
                print(f"Processed {idx} lines")
            tagger_type = get_tagger_type(library)
            tag_result = tag_person_name(
                Name(line.strip()), normalizer, tagger_type=tagger_type
            )
            if verbose:
                print(f"{line.strip()} -> {fmt_tag_result(tag_result.symbols)}")


@cli.command("tag-org")
@click.argument("library", type=str)
@click.argument("names_path", type=InPath)
@click.option(
    "--verbose",
    is_flag=True,
    help="Print out each line and its results - useful for comparison",
)
def tag_org(library: str, names_path: Path, verbose: bool) -> None:
    with open(names_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx > 0 and idx % 1000 == 0:
                print(f"Processed {idx} lines")
            tagger_type = get_tagger_type(library)
            tag_result = tag_org_name(
                Name(line.strip()), normalizer, tagger_type=tagger_type
            )
            if verbose:
                print(f"{line.strip()} -> {fmt_tag_result(tag_result.symbols)}")


@cli.command("demo-tag-person")
@click.argument("library", type=str)
@click.argument("demo_string", type=str)
def demo_tag_person(library: str, demo_string: str) -> None:
    print("Tagging demo string")
    normalized_string = normalizer(demo_string)
    name = Name(normalized_string)
    tagger_type = get_tagger_type(library)
    tag_result = tag_person_name(name, normalizer, tagger_type=tagger_type)
    print(f"'{normalized_string}' -> {fmt_tag_result(tag_result.symbols)}")


@cli.command("demo-tag-org")
@click.argument("library", type=str)
@click.argument("demo_string", type=str)
def demo_tag_org(library: str, demo_string: str) -> None:
    print("Tagging demo string")
    normalized_string = normalizer(demo_string)
    name = Name(normalized_string)
    tagger_type = get_tagger_type(library)
    tag_result = tag_person_name(name, normalizer, tagger_type=tagger_type)
    print(f"'{normalized_string}' -> {fmt_tag_result(tag_result.symbols)}")


if __name__ == "__main__":
    cli()
