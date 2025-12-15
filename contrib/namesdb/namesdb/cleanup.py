import string
import logging
from sqlalchemy import select, update, func
from namesdb.db import engine, mapping_table
from namesdb.blocks import GROUPS, CONTAINS, STARTS, SUFFIXES

from rigour.text.scripts import is_latin

log = logging.getLogger(__name__)


def block_groups():
    with engine.begin() as conn:
        for group in GROUPS:
            stmt = update(mapping_table)
            stmt = stmt.where(mapping_table.c.group == group)
            stmt = stmt.values(skip=True)
            conn.execute(stmt)


def block_phrases():
    with engine.begin() as conn:
        for phrase in CONTAINS:
            stmt = update(mapping_table)
            stmt = stmt.where(mapping_table.c.form.ilike(f"%{phrase}%"))
            stmt = stmt.values(skip=True)
            conn.execute(stmt)
        for phrase in STARTS:
            stmt = update(mapping_table)
            stmt = stmt.where(mapping_table.c.form.ilike(f"{phrase}%"))
            stmt = stmt.values(skip=True)
            conn.execute(stmt)
        for phrase in SUFFIXES:
            stmt = update(mapping_table)
            stmt = stmt.where(mapping_table.c.form.ilike(f"%{phrase}"))
            stmt = stmt.values(skip=True)
            conn.execute(stmt)


def block_forms():
    with engine.begin() as conn:
        q = select(mapping_table.c.id, mapping_table.c.form)
        q = q.where(mapping_table.c.skip.is_(False))
        result = conn.execute(q)
        for row in result:
            form = row._mapping["form"]

            # Remove single-character forms
            alnums = [c for c in form if c.isalnum()]
            if len(alnums) < 2:
                latins = [c for c in alnums if is_latin(c) or c in string.digits]
                if len(latins) == len(alnums):
                    log.info("Blocking form: %r", form)
                    # stmt = update(mapping_table)
                    # stmt = stmt.where(mapping_table.c.id == row._mapping["id"])
                    # stmt = stmt.values(skip=True)
                    # conn.execute(stmt)


def bad_candidates():
    stmt = select(mapping_table)
    stmt = stmt.where(mapping_table.c.skip.is_(False))
    stmt = stmt.order_by(func.length(mapping_table.c.form).desc())
    # stmt = stmt.where(mapping_table.c.form.like("% not %"))
    stmt = stmt.limit(1000)
    with engine.connect() as conn:
        result = conn.execute(stmt)
        for row in result:
            form = row._mapping["form"]
            print(row._mapping["id"], row._mapping["group"], repr(form))


if __name__ == "__main__":
    block_groups()
    block_phrases()
    bad_candidates()
