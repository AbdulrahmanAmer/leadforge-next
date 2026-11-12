"""L6 build 2, item 1: C5 for files. A business and everything attached to it expires, also its sheets and cached pages.

Every person here is invented. Files under the workspace's own `exports` and `cache` folders that hold an expired business are
deleted whole, under the same protections as the records; files the user wrote elsewhere (`--out`) are not touched.
"""
import json
import re
import zipfile
from pathlib import Path

from openpyxl import Workbook
from typer.testing import CliRunner

from leadforge import db
from leadforge.cli import app
from leadforge.config import load_config
from leadforge.retention import purge
from tests.test_l6_purge import ALL, NOW, digest_of, ids, make_workspace


def sheet(path: Path, *cells: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.active.append(["Business", "Contact"])
    for c in cells:
        wb.active.append(["x", c])
    wb.save(path)
    return path


def text(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def make_files(ws: Path) -> dict[str, Path]:
    """Old run: a sheet, a csv and a cached page that name A, C and D. 11-month run: files of B and E. New run: N0 and N1.
    One file of the user's own, outside the data folder."""
    ex, ca = ws / "leadforge_data" / "exports", ws / "leadforge_data" / "cache"
    return {
        "old_sheet": sheet(ex / "run_old" / "leads.xlsx", "Person A", "a@works-a.example"),
        "old_csv": text(ex / "run_old" / "leads.csv", "Invented C Works,c@works-c.example\n"),
        "old_cache": text(ca / "page_old.json", json.dumps({"owner": "Person D", "biz": "Invented D Works"})),
        "mid_sheet": sheet(ex / "run_mid" / "leads.xlsx", "Person B", "b@works-b.example"),
        "soon_csv": text(ex / "run_soon" / "leads.csv", "Invented E Works,e@works-e.example\n"),
        "new_cache": text(ca / "page_new.json", json.dumps({"owner": "Person N0"})),
        "report": text(ex / "run_new" / "report.json", json.dumps({"biz": "Invented N1 Works"})),
        "out_file": text(ws / "my_own_copy" / "leads.csv", "Invented A Works,a@works-a.example\n"),
    }


def scan(root: Path, needles: list[str]) -> list[str]:
    """Every file under root (also inside a sheet's zip members) that holds one of the strings."""
    pat = re.compile("|".join(re.escape(n) for n in needles).encode(), re.IGNORECASE)
    hits = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith("db.sqlite3"):
            continue
        raw = p.read_bytes()
        inside = zipfile.is_zipfile(p) and any(pat.search(zipfile.ZipFile(p).read(n)) for n in zipfile.ZipFile(p).namelist())
        if pat.search(raw) or inside:
            hits.append(str(p.relative_to(root)))
    return hits


EXPIRED = ["Person A", "Person C", "Person D", "Invented A Works", "Invented C Works", "Invented D Works"]


def rel(p: Path, ws: Path) -> str:
    return str(p.relative_to(ws / "leadforge_data")).replace("\\", "/")


def block_unlink(monkeypatch, victim: Path) -> None:
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.resolve() == victim.resolve():
            raise PermissionError("held open by another program")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)


def test_expired_businesses_files_go_with_them_and_the_rest_stays(tmp_path):
    make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    first = purge(cfg, NOW, "auto")
    assert first["state"] == "armed" and first["files_expired"] == 3        # reported, not deleted
    assert all(p.exists() for p in f.values())                              # the first pass after the upgrade deletes no file
    second = purge(cfg, NOW, "auto")
    assert second["state"] == "purged" and second["files_deleted"] == 3
    for k in ("old_sheet", "old_csv", "old_cache"):
        assert not f[k].exists(), k
    for k in ("mid_sheet", "soon_csv", "new_cache", "report", "out_file"):   # 11 months, newer, and the user's own copy stay
        assert f[k].exists(), k
    assert scan(tmp_path / "leadforge_data", EXPIRED) == []
    assert scan(tmp_path / "leadforge_data", ["Person B", "Person N0"]) != []     # and the others' data is still there
    assert ids(tmp_path / "leadforge_data" / "db.sqlite3") == ALL - {"A", "C", "D"}


def test_the_explicit_report_names_the_files_and_deletes_nothing(tmp_path):
    make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    rep = purge(cfg, NOW, "report")
    assert rep["files_expired"] == 3
    assert sorted(rep["file_paths"]) == sorted(rel(f[k], tmp_path) for k in ("old_sheet", "old_csv", "old_cache"))
    assert all(p.exists() for p in f.values())


def test_files_count_in_the_30_day_line(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)
    make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    assert purge(cfg, NOW, "report")["files_expiring_30d"] == 1              # E's csv; B's sheet is due in 33 days
    from leadforge import cli
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    monkeypatch.chdir(tmp_path)
    counts = cli._start_of_run_purge(cfg)
    assert counts["expiring_30d"] == 1 and counts["files_expiring_30d"] == 1
    assert "1 files" in capsys.readouterr().err


def test_files_count_in_the_more_than_half_stop(tmp_path):
    """3 of 10 businesses are expired (under half), but 3 of the 4 files hold one of them: the automatic purge stops."""
    make_workspace(tmp_path)
    ex = tmp_path / "leadforge_data" / "exports"
    old = [sheet(ex / "r1" / "a.xlsx", "Person A"), text(ex / "r1" / "c.csv", "c@works-c.example\n"), text(ex / "r1" / "d.json", "Person D")]
    keep = text(ex / "r2" / "n.csv", "Person N3\n")
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    res = purge(cfg, NOW, "auto")
    assert res["state"] == "stopped_over_half" and res["expired"] == 3 and res["files_expired"] == 3
    assert all(p.exists() for p in old + [keep]) and ids(tmp_path / "leadforge_data" / "db.sqlite3") == ALL
    again = purge(cfg, NOW, "apply")                                         # the explicit command has no half limit
    assert again["state"] == "purged" and not any(p.exists() for p in old) and keep.exists()


def test_a_name_that_a_surviving_business_also_carries_condemns_no_file(tmp_path):
    path = make_workspace(tmp_path)
    c = db.connect(path)
    c.execute("INSERT INTO people(business_id,name) VALUES('A','Shared Sam')")
    c.execute("INSERT INTO people(business_id,name) VALUES('N2','Shared Sam')")
    c.commit()
    c.close()
    only_shared = text(tmp_path / "leadforge_data" / "exports" / "r" / "who.csv", "Shared Sam\n")
    text(tmp_path / "leadforge_data" / "exports" / "r" / "other.csv", "Person N4\n")   # keeps the half rule out of the way
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    assert purge(cfg, NOW, "auto")["state"] == "purged"
    assert only_shared.exists()


def test_a_file_that_cannot_be_deleted_keeps_the_records_and_is_named(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    with monkeypatch.context() as m:
        block_unlink(m, f["old_csv"])
        res = purge(cfg, NOW, "apply")
    assert res["state"] == "files_locked" and res["files_failed"] == ["exports/run_old/leads.csv"] and res["deleted"] == 0
    assert ids(path) == ALL                                                  # records stay: they are what finds the file again
    again = purge(cfg, NOW, "apply")
    assert again["state"] == "purged" and not f["old_csv"].exists() and ids(path) == ALL - {"A", "C", "D"}


def test_the_purge_command_exits_4_naming_a_locked_file(tmp_path, monkeypatch):
    make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    block_unlink(monkeypatch, f["old_cache"])
    res = CliRunner().invoke(app, ["purge", "--apply"])
    assert res.exit_code == 4, res.output
    d = digest_of(res.output)
    assert d["ok"] is False and "cache/page_old.json" in " ".join(d["warnings"]) and "Person D" not in res.output


def test_a_run_goes_on_when_a_file_is_locked_and_says_which(tmp_path, monkeypatch, capsys):
    make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    from leadforge import cli
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("leadforge.util.utcnow", lambda: NOW)
    block_unlink(monkeypatch, f["old_sheet"])
    counts = cli._start_of_run_purge(cfg)
    assert counts["purged"] == 0
    assert "leads.xlsx" in capsys.readouterr().err


def test_no_files_under_the_folders_changes_nothing_in_the_numbers(tmp_path):
    make_workspace(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    res = purge(cfg, NOW, "auto")
    assert res["state"] == "purged" and res["deleted"] == 3 and res["files_deleted"] == 0 and res["files_expired"] == 0


def test_a_file_that_cannot_be_read_is_not_guessed_about(tmp_path, monkeypatch):
    path = make_workspace(tmp_path)
    f = make_files(tmp_path)
    cfg = load_config(tmp_path)
    purge(cfg, NOW, "auto")
    real_read = Path.read_bytes

    def unreadable(self):
        if self.resolve() == f["mid_sheet"].resolve():
            raise PermissionError("held open by another program")
        return real_read(self)

    with monkeypatch.context() as m:
        m.setattr(Path, "read_bytes", unreadable)
        res = purge(cfg, NOW, "apply")
    assert res["state"] == "files_locked" and res["files_failed"] == ["exports/run_mid/leads.xlsx"]
    assert ids(path) == ALL and f["mid_sheet"].exists()                      # nothing was deleted from the database
