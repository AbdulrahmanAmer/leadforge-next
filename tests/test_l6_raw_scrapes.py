"""L6 item 5 (C6): the raw output of the Maps scraper is not kept once parsed. Reviewers and places are invented."""
import json
from pathlib import Path

import pytest

from leadforge import db
from leadforge.grid import PlannedQuery
from leadforge.normalize import to_business
from leadforge.providers.gosom import GosomProvider
from leadforge.util import ProviderDegraded

REVIEWER = "Hesper Dunmore-Vale"      # a reviewer's own name: in the raw file, never a business fact
REVIEW_TEXT = "Hesper's long review of the shop, quoted word for word"


def raw_row() -> dict:
    return {"title": "Lantern Row Garage", "category": "Auto repair shop", "address": "3 Lantern Row, Leeds LS1 1AA, UK",
            "phone": "0113 496 0000", "web_site": "https://lantern-row.example", "review_rating": 4.5, "review_count": 3,
            "place_id": "PID_LANTERN", "cid": "111",
            "user_reviews_extended": [
                {"Name": REVIEWER, "Description": REVIEW_TEXT, "Rating": 5,
                 "reply_text_original": "Thanks for coming in, Rowan"}]}


@pytest.fixture
def provider(cfg):
    return GosomProvider(cfg)


def fake_run(content: str, *, timed_out=False, returncode=0, stderr=""):
    def run(args, out_path, hard_timeout_s, stall_s=180.0, poll_s=5.0):
        out_path.write_text(content, encoding="utf-8")
        return {"returncode": returncode, "stderr": stderr}, timed_out
    return staticmethod(run)


def cache_files(cfg) -> list[str]:
    return sorted(p.name for p in cfg.cache_dir.iterdir())


def workspace_holds(cfg, text: str) -> list[str]:
    return [str(p) for p in Path(cfg.workspace).rglob("*") if p.is_file() and text.encode() in p.read_bytes()]


def test_raw_file_is_gone_once_parsed_and_the_reviewer_is_in_no_file(cfg, provider, monkeypatch):
    monkeypatch.setattr(GosomProvider, "_run_with_watchdog", fake_run(json.dumps([raw_row()])))
    listings = provider.fetch(PlannedQuery(text="garage Leeds", category="garage", area="Leeds"))
    assert len(listings) == 1 and listings[0].data["user_reviews_extended"][0]["Name"] == REVIEWER   # parsed in memory
    assert cache_files(cfg) == []
    conn = db.connect(cfg.db_path)
    biz = to_business(listings[0], "run_1", None, "GB")
    conn.execute("INSERT INTO runs(id,stage) VALUES('run_1','discovering')")
    db.upsert_business(conn, biz)
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    assert workspace_holds(cfg, REVIEWER) == [] and workspace_holds(cfg, "word for word") == []   # a scan of every file


def test_raw_file_is_gone_when_the_run_stalled_and_part_was_salvaged(cfg, provider, monkeypatch):
    monkeypatch.setattr(GosomProvider, "_run_with_watchdog", fake_run(json.dumps(raw_row()), timed_out=True))
    assert len(provider.fetch(PlannedQuery(text="garage Leeds", category="garage", area="Leeds"))) == 1
    assert cache_files(cfg) == []


def test_a_failed_fetch_that_wrote_no_file_still_reports_its_own_error(cfg, provider, monkeypatch):
    def run(args, out_path, hard_timeout_s, stall_s=180.0, poll_s=5.0):
        return {"returncode": 1, "stderr": "boom"}, False       # the scraper died before writing anything
    monkeypatch.setattr(GosomProvider, "_run_with_watchdog", staticmethod(run))
    with pytest.raises(ProviderDegraded, match="exit 1"):       # not a FileNotFoundError from the clean-up
        provider.fetch(PlannedQuery(text="garage Leeds", category="garage", area="Leeds"))


def test_raw_file_is_gone_when_nothing_could_be_parsed(cfg, provider, monkeypatch):
    monkeypatch.setattr(GosomProvider, "_run_with_watchdog",
                        fake_run(f'{{"user_reviews": [{{"Name": "{REVIEWER}"', timed_out=True))
    with pytest.raises(ProviderDegraded):
        provider.fetch(PlannedQuery(text="garage Leeds", category="garage", area="Leeds"))
    assert cache_files(cfg) == [] and workspace_holds(cfg, REVIEWER) == []
