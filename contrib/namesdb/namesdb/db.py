from pathlib import Path
from datetime import datetime, timezone
from typing import Generator, List, Optional, Set, Tuple
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
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from namesdb.util import clean_form

RUN_TIME = datetime.now(timezone.utc)
DATA_PATH = Path(__file__).parent.parent / "data"
DATA_PATH.mkdir(exist_ok=True)
DB_FILE = DATA_PATH / "names.db"
DB_URL = f"sqlite:///{DB_FILE.resolve().as_posix()}"
engine = create_engine(DB_URL)

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
metadata.create_all(bind=engine)


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
        set_=dict(
            last_seen=ilstmt.excluded.last_seen,
        ),
    )
    conn.execute(lstmt)


def skip_mapping(conn: Connection, mapping_id: int) -> None:
    """Mark a mapping as skipped in the database."""
    data = {
        "skip": True,
        "last_seen": RUN_TIME,
    }
    stmt = update(mapping_table).values(data)
    stmt = stmt.where(mapping_table.c.id == mapping_id)
    conn.execute(stmt)


def get_groups(conn: Connection, form: str) -> List[str]:
    cleaned = clean_form(form)
    if cleaned is None:
        return []
    stmt = select(mapping_table.c.group)
    stmt = stmt.where(mapping_table.c.form == cleaned)
    groups: List[str] = []
    for row in conn.execute(stmt):
        groups.append(row._mapping["group"])
    return groups


def regex_groups(conn: Connection, pattern: str) -> Set[Tuple[str, int, str, bool]]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.form.regexp_match(pattern))
    forms: Set[Tuple[str, int, str, bool]] = set()
    for row in conn.execute(stmt):
        data = (
            row._mapping["group"],
            row._mapping["id"],
            row._mapping["form"],
            row._mapping["skip"],
        )
        forms.add(data)
    return forms


def get_forms(conn: Connection, group: str) -> Set[Tuple[int, str, bool]]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.group == group)
    forms: Set[Tuple[int, str, bool]] = set()
    for row in conn.execute(stmt):
        forms.add((row._mapping["id"], row._mapping["form"], row._mapping["skip"]))
    return forms


def all_mappings(conn: Connection) -> Generator[Tuple[str, Set[str]], None, None]:
    stmt = select(mapping_table)
    stmt = stmt.filter(mapping_table.c.skip.is_(False))
    stmt = stmt.order_by(mapping_table.c.group.asc())
    group: Optional[str] = None
    forms: Set[str] = set()
    for row in conn.execute(stmt):
        if group != row._mapping["group"]:
            if group is not None and len(forms):
                yield (group, forms)
            group = row._mapping["group"]
            forms = set()
        forms.add(row._mapping["form"])
    if group is not None and len(forms):
        yield (group, forms)
