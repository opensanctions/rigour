import click
import logging
from pathlib import Path
from typing import List
from namesdb.export import dump_file_export
from rich.table import Table
from rich.console import Console
from normality import latinize_text

from namesdb.db import engine, regex_groups, store_mapping, skip_mapping
from namesdb.db import get_groups, get_forms

log = logging.getLogger(__name__)


@click.group()
def cli():
    """NamesDB CLI for managing name mappings."""
    logging.basicConfig(level=logging.INFO)


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


@cli.command("skipgroup")
@click.argument("groups", type=str, nargs=-1)
def skip_group(groups: List[str]) -> None:
    with engine.begin() as conn:
        for group in groups:
            for mapping_id, form, skip in sorted(get_forms(conn, group)):
                if skip:
                    continue
                log.info("Skip %r (%d) for group '%s'", form, mapping_id, group)
                skip_mapping(conn, mapping_id)


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


@cli.command("grep")
@click.option("--mark-skip", "-k", is_flag=True, help="Mark all matches as skipped.")
@click.argument("pattern", type=str)
def grep_forms(pattern: str, mark_skip: bool = False) -> None:
    with engine.begin() as conn:
        table = Table()
        table.add_column("Group", style="magenta")
        table.add_column("ID", style="blue")
        table.add_column("Form", style="green")
        table.add_column("Latinized", style="yellow")
        table.add_column("Skip", style="red")
        for group, mapping_id, form, skip in regex_groups(conn, pattern):
            status = "skip" if skip else ""
            table.add_row(group, str(mapping_id), form, latinize_text(form), status)
            if mark_skip and not skip:
                skip_mapping(conn, mapping_id)
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
    dump_file_export(Path(path))


if __name__ == "__main__":
    cli()
