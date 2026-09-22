import json
import os
from collections.abc import Generator
from datetime import datetime, timezone
from itertools import count
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    DateTime,
    Integer,
    MetaData,
    Table,
    Unicode,
    UniqueConstraint,
    create_engine,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from namesdb.util import clean_form
from rigour.text.scripts import text_scripts

RUN_TIME = datetime.now(timezone.utc)
DATA_PATH = Path(__file__).parent.parent / "data"
DATA_PATH.mkdir(exist_ok=True)
DB_FILE = Path(os.environ.get("NAMESDB_PATH", DATA_PATH / "names.db"))
DB_URL = f"sqlite:///{DB_FILE.resolve().as_posix()}"
engine = create_engine(DB_URL)

# Bit flags recording where a form was seen on a Wikidata item; OR-ed
# together when the same (form, lang) arrives via several routes.
SOURCE_LABEL = 1
SOURCE_ALIAS = 2
SOURCE_NATIVE = 4  # P1705 native label
SOURCE_TRANSLIT = 8  # P2440 transliteration or transcription

# JSON shape of `item.names`: form -> raw Wikidata language code -> source bits.
ItemNames = dict[str, dict[str, int]]

metadata = MetaData()
mapping_table = Table(
    "mapping",
    metadata,
    Column("id", Integer, primary_key=True, unique=True),
    Column("form", Unicode(500), index=True, nullable=False),
    Column("group", Unicode(255), index=True, nullable=False),
    Column("skip", Boolean, default=False),
    Column("first_seen", DateTime, nullable=True),
    Column("last_seen", DateTime, nullable=True),
    UniqueConstraint("form", "group", name="uq_mapping_form_group"),
)
item_table = Table(
    "item",
    metadata,
    Column("group", Unicode(255), primary_key=True),
    Column("classes", Unicode(500), nullable=False),
    Column("names", Unicode, nullable=False),
    Column("schemes", Unicode, nullable=False),
    Column("first_seen", DateTime, nullable=False),
    Column("last_seen", DateTime, nullable=False),
)
metadata.create_all(bind=engine)


def form_script(form: str) -> str | None:
    """Return the script of a form when it is written in exactly one script."""
    scripts = text_scripts(form)
    if len(scripts) != 1:
        return None
    return scripts.pop()


def store_mapping(conn: Connection, form: str, group: str) -> None:
    """Store a mapping between a form and a group in the database."""
    cleaned = clean_form(form)
    if cleaned is None:
        return
    data = {
        "form": cleaned,
        "group": group,
        "skip": False,
        "first_seen": RUN_TIME,
        "last_seen": RUN_TIME,
    }
    ilstmt = sqlite_insert(mapping_table).values(data)
    lstmt = ilstmt.on_conflict_do_update(
        index_elements=["form", "group"],
        set_={"last_seen": ilstmt.excluded.last_seen},
    )
    conn.execute(lstmt)


def store_item(
    conn: Connection,
    group: str,
    classes: list[str],
    names: ItemNames,
    schemes: dict[str, str],
    seen_at: datetime = RUN_TIME,
) -> None:
    """Store the name extraction of one Wikidata item, replacing any older one.

    An existing row is only overwritten by a newer observation, so a
    backfill stamped with cache timestamps never clobbers a fresh crawl.
    """
    data = {
        "group": group,
        "classes": " ".join(sorted(classes)),
        "names": json.dumps(names, ensure_ascii=False, sort_keys=True),
        "schemes": json.dumps(schemes, ensure_ascii=False, sort_keys=True),
        "first_seen": seen_at,
        "last_seen": seen_at,
    }
    istmt = sqlite_insert(item_table).values(data)
    stmt = istmt.on_conflict_do_update(
        index_elements=["group"],
        set_={
            "classes": istmt.excluded.classes,
            "names": istmt.excluded.names,
            "schemes": istmt.excluded.schemes,
            "last_seen": istmt.excluded.last_seen,
        },
        where=istmt.excluded.last_seen >= item_table.c.last_seen,
    )
    conn.execute(stmt)


def iter_items(
    conn: Connection,
) -> Generator[tuple[str, list[str], ItemNames, dict[str, str]], None, None]:
    """Yield (group, classes, names, schemes) for every stored item."""
    stmt = select(item_table).order_by(item_table.c.group.asc())
    for row in conn.execute(stmt).yield_per(10000):
        m = row._mapping
        classes = m["classes"].split() if len(m["classes"]) else []
        yield (m["group"], classes, json.loads(m["names"]), json.loads(m["schemes"]))


def skipped_pairs(conn: Connection) -> set[tuple[str, str]]:
    """Return the (form, group) pairs marked as skipped in the mapping table."""
    stmt = select(mapping_table.c.form, mapping_table.c.group)
    stmt = stmt.where(mapping_table.c.skip.is_(True))
    return {(row._mapping["form"], row._mapping["group"]) for row in conn.execute(stmt)}


def skip_mapping(conn: Connection, mapping_id: int) -> None:
    """Mark a mapping as skipped in the database."""
    data = {
        "skip": True,
        "last_seen": RUN_TIME,
    }
    stmt = update(mapping_table).values(data)
    stmt = stmt.where(mapping_table.c.id == mapping_id)
    conn.execute(stmt)


def get_groups(conn: Connection, form: str) -> list[str]:
    cleaned = clean_form(form)
    if cleaned is None:
        return []
    stmt = select(mapping_table.c.group)
    stmt = stmt.where(mapping_table.c.form == cleaned)
    groups: list[str] = []
    for row in conn.execute(stmt):
        groups.append(row._mapping["group"])
    return groups


def regex_groups(conn: Connection, pattern: str) -> set[tuple[str, int, str, bool]]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.form.regexp_match(pattern))
    forms: set[tuple[str, int, str, bool]] = set()
    for row in conn.execute(stmt):
        data = (
            row._mapping["group"],
            row._mapping["id"],
            row._mapping["form"],
            row._mapping["skip"],
        )
        forms.add(data)
    return forms


def get_forms(conn: Connection, group: str) -> set[tuple[int, str, bool]]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.group == group)
    forms: set[tuple[int, str, bool]] = set()
    for row in conn.execute(stmt):
        forms.add((row._mapping["id"], row._mapping["form"], row._mapping["skip"]))
    return forms


def all_mappings(conn: Connection) -> Generator[tuple[str, set[str]], None, None]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.skip.is_(False))
    stmt = stmt.order_by(mapping_table.c.group.asc())
    group: str | None = None
    forms: set[str] = set()
    for row in conn.execute(stmt):
        if group != row._mapping["group"]:
            if group is not None and len(forms):
                yield (group, forms)
            group = row._mapping["group"]
            forms = set()
        forms.add(row._mapping["form"])
    if group is not None and len(forms):
        yield (group, forms)


def make_group_id(conn: Connection) -> str:
    """Generate a fake group ID for testing purposes."""
    for i in count(1):
        wiki_id = f"Q{i}"
        group_id = f"X{i}"
        stmt = select(mapping_table)
        stmt = stmt.filter(
            or_(
                mapping_table.c.group == group_id,
                mapping_table.c.group == wiki_id,
            )
        )
        result = conn.execute(stmt).first()
        if result is None:
            return group_id
    raise RuntimeError("Unable to generate unique group ID")
