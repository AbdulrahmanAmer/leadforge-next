"""L6 item 2: the schema version is read before anything is written (ADOPT risk 11).

A workspace of an older schema is refused and stays byte for byte as it was: the SHA-256 of every file under
the workspace, and the list of files, are equal before and after. Every person and company here is invented.
"""
import hashlib
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from leadforge import db
from leadforge.cli import app
from leadforge.util import InputError


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def make_old_workspace(ws: Path, *, live_wal: bool):
    """A schema-4 workspace with rows. live_wal: a second connection is left open with its log not folded back,
    so a non-empty `-wal` sits beside the file (what a crashed run leaves)."""
    data = ws / "leadforge_data"
    data.mkdir(parents=True)
    path = data / "db.sqlite3"
    conn = db.connect(path)
    conn.execute("INSERT INTO businesses(id,name,name_norm,dedupe_key) VALUES('b1','Old Example Plumbing','old example plumbing','k1')")
    conn.execute("UPDATE meta SET value='4' WHERE key='schema_version'")
    conn.commit()
    if live_wal:
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("INSERT INTO businesses(id,name,name_norm,dedupe_key) VALUES('b2','Second Example Plumbing','second example plumbing','k2')")
        conn.commit()
        assert path.with_name(path.name + "-wal").stat().st_size > 0
        return path, conn
    conn.close()
    return path, None


@pytest.mark.parametrize("live_wal", [False, True])
def test_old_workspace_is_refused_and_unchanged(tmp_path, monkeypatch, live_wal):
    path, held = make_old_workspace(tmp_path, live_wal=live_wal)
    (tmp_path / "leadforge_data" / "progress.jsonl").write_text('{"stage":"enrich"}\n', encoding="utf-8")
    (tmp_path / "dm_batch.ndjson").write_text("{}\n", encoding="utf-8")
    before = snapshot(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(InputError, match="older LeadForge"):
        db.connect(path)
    assert snapshot(tmp_path) == before

    runner = CliRunner()
    for argv in (["status"], ["suppress", "list"]):
        res = runner.invoke(app, argv)
        assert res.exit_code != 0, (argv, res.output)
        assert "older LeadForge" in res.output or isinstance(res.exception, InputError), (argv, res.output)
        assert snapshot(tmp_path) == before, argv
    if held is not None:
        held.close()


def test_file_with_tables_but_no_version_row_is_refused(tmp_path):
    import sqlite3
    path = tmp_path / "db.sqlite3"
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE businesses (id TEXT)")
    c.commit()
    c.close()
    before = snapshot(tmp_path)
    with pytest.raises(InputError, match="no schema version"):
        db.connect(path)
    assert snapshot(tmp_path) == before


def test_new_and_current_workspaces_still_open(tmp_path):
    fresh = tmp_path / "new" / "db.sqlite3"
    fresh.parent.mkdir()
    db.connect(fresh).close()                      # does not exist yet: created and stamped
    empty = tmp_path / "empty.sqlite3"
    empty.write_bytes(b"")
    db.connect(empty).close()                      # zero bytes: new
    again = tmp_path / "again.sqlite3"
    shutil.copyfile(fresh, again)
    db.connect(again).close()                      # current version: opens
