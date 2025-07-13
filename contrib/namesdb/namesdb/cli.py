from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set
import click
from rich.table import Table
from rich.console import Console
from normality import latinize_text

from namesdb.db import engine, store_mapping, skip_mapping
from namesdb.db import get_groups, get_forms, all_mappings
from namesdb.cleanup import block_groups, block_phrases


@click.group()
def cli():
    """NamesDB CLI for managing name mappings."""
    pass


@cli.command("map")
@click.argument("group", type=str)
@click.argument("form", type=str)
def map_forms(group: str, form: str) -> None:
    with engine.begin() as conn:
        store_mapping(conn, form, group)


@cli.command("skip")
@click.argument("ids", type=int, nargs=-1)
def skip_form(ids: List[int]) -> None:
    with engine.begin() as conn:
        for id in ids:
            skip_mapping(conn, id)


@cli.command("lookup")
@click.argument("form", type=str)
def lookup_form(form: str) -> None:
    with engine.begin() as conn:
        table = Table()
        table.add_column("Group", style="magenta")
        table.add_column("ID", style="blue")
        table.add_column("Form", style="green")
        table.add_column("Latinized", style="yellow")
        table.add_column("Skip", style="red")
        for group in sorted(get_groups(conn, form)):
            for mapping_id, form, skip in sorted(get_forms(conn, group)):
                status = "skip" if skip else ""
                table.add_row(group, str(mapping_id), form, latinize_text(form), status)
        Console().print(table)


@cli.command("load")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, readable=True))
def load_file(path: Path) -> None:
    with engine.begin() as conn:
        with open(path, "r") as fh:
            while line := fh.readline():
                line = line.strip()
                forms_, group = line.split(" => ")
                for form in forms_.split(", "):
                    form = form.strip()
                    store_mapping(conn, form, group)
        conn.commit()


@cli.command("dump")
@click.argument("path", type=click.Path(dir_okay=False, writable=True))
def dump_file(path: Path) -> None:
    block_groups()
    block_phrases()
    with engine.begin() as conn:
        mappings = dict(all_mappings(conn))
        # print("Deduplicating name QIDs...")
        by_names: Dict[str, Set[str]] = defaultdict(set)
        for group, aliases in mappings.items():
            for alias in aliases:
                by_names[alias].add(group)
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

        with open(path, "w") as fh:
            for group, forms in sorted(mappings.items()):
                if len(forms) < 2:
                    continue
                fstr = ", ".join(sorted(forms))
                fh.write(f"{fstr} => {group}\n")


if __name__ == "__main__":
    cli()
