"""Writes tests/golden/workspace_current.sqlite3: a workspace made by this version with one made-up business.

Run only together with a schema change the slice lists:  python tests/fixtures/make_workspace_golden.py
"""
from pathlib import Path

from leadforge import db
from leadforge.models import Business

OUT = Path(__file__).resolve().parents[1] / "golden" / "workspace_current.sqlite3"


def main() -> None:
    for p in (OUT, OUT.with_name(OUT.name + "-wal"), OUT.with_name(OUT.name + "-shm")):
        p.unlink(missing_ok=True)
    conn = db.connect(OUT)
    db.upsert_business(conn, Business(id="biz_golden", name="Golden Example Plumbing",
                                      name_norm="golden example plumbing", dedupe_key="dk:golden",
                                      website="https://plumbing.example", source="fakelist"))
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode=DELETE")  # one self-contained file
    conn.close()
    print(OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
