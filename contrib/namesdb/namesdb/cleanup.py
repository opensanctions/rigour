from sqlalchemy import select, update, func
from namesdb.db import engine, mapping_table
from namesdb.blocks import GROUPS, CONTAINS


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
