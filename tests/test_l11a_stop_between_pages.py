"""L11a Build 3, decision 11: a stop the window asks for (`window run_stop`) is seen between two page fetches of one site, not
only between two businesses, so a slow site cannot hold the stop for its whole crawl.

A real local HTTP server (127.0.0.1 only, fully offline), the same pattern as test_crawler_link_selection.py: the home page links
five further pages, each of which answers after SLOW_S seconds. The stop flag is written when the first further page is asked for.
"""

import http.server
import json
import threading
import time

import pytest

from leadforge import db, util
from leadforge.config import load_config
from leadforge.enrich import runner
from leadforge.util import RunStopped

SLOW_S = 2.0
LINKS = ["/about", "/contact", "/team", "/staff", "/careers"]


class _SlowSite(http.server.BaseHTTPRequestHandler):
    stop_file = None
    stopped_at: float | None = None

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = ("<html><body>" + "".join(f'<a href="{link}">{link[1:]}</a>' for link in LINKS) + "</body></html>").encode()
        elif path in LINKS:
            cls = type(self)
            if cls.stop_file is not None and cls.stopped_at is None:
                cls.stop_file.write_text("stop", encoding="utf-8")   # what `window run_stop` writes
                cls.stopped_at = time.monotonic()
            time.sleep(SLOW_S)
            body = b"<html><body>Opening hours</body></html>"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def slow_site():
    class H(_SlowSite):
        stop_file = None
        stopped_at = None

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", H
    srv.shutdown()


@pytest.mark.parametrize("stage", ["all", "site"])   # the overlapped path a run takes, and the serial one
def test_a_stop_during_a_slow_site_ends_the_enrich_within_seconds(tmp_path, monkeypatch, slow_site, stage):
    base, site = slow_site
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.politeness.delay_s = 0.0
    monkeypatch.setattr(runner.browser, "is_available", lambda: False)
    stop = tmp_path / "window-run.stop"
    site.stop_file = stop
    monkeypatch.setattr(util, "_STOP_FILE", str(stop))   # as run_start sets it; the command line never does
    conn = db.connect(cfg.db_path)
    conn.execute("INSERT INTO businesses(id,place_id,name,name_norm,website,domain,address_country,last_seen_at,dedupe_key) "
                 "VALUES('b1','place-b1','Slow Lane Motors','slow lane motors',?,'127.0.0.1','GB','2026-11-01T09:10:00Z','key-b1')",
                 (base + "/",))
    conn.commit()
    with pytest.raises(RunStopped):
        runner.run_enrich(conn, cfg, 10, stage=stage)
    ended = time.monotonic()
    assert site.stopped_at is not None, "the crawl never asked for a further page"
    took = ended - site.stopped_at
    print(f"stage {stage}: the stop to the end of enrich: {took:.2f} s (one further page takes {SLOW_S} s, the site {len(LINKS)} of them)")
    assert took < 4.0
    enrich = json.loads(conn.execute("SELECT enrich_json FROM businesses WHERE id='b1'").fetchone()[0] or "{}")
    assert "error" not in enrich   # a stopped site is not recorded as a failed one: `run --resume` crawls it again
    conn.close()
