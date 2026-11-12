"""L7 (C8 to C13), the collect side: guardrails proved against a loopback server (127.0.0.1 and `localhost` only).

The server answers as several sites at once: the Host header picks the site, so `127.0.0.1:<port>` and
`localhost:<port>` are two sites (two site keys) on one socket. Nothing here leaves this machine.
"""
import http.server
import threading

import pytest

from leadforge.config import load_config
from leadforge.enrich.crawler import ROBOTS_MAX_BYTES, ROBOTS_TTL_S, SiteCrawler

HTML = b"<html><body>hello</body></html>"


class _Site(http.server.BaseHTTPRequestHandler):
    sites: dict = {}  # host header -> {path: (status, {header: value}, body)}
    log: list = []  # (host header, path) of every request that reached the server

    def do_GET(self):  # noqa: N802 — http.server API
        host = (self.headers.get("Host") or "").lower()
        path = self.path
        type(self).log.append((host, path))
        status, headers, body = type(self).sites.get(host, {}).get(path, (404, {}, b""))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def loopback():
    """-> (port, sites, log). `sites[host][path] = (status, headers, body)`, filled in by the test."""

    class H(_Site):
        sites = {}
        log = []

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], H.sites, H.log
    srv.shutdown()


def _crawler(tmp_path, monkeypatch, **kw):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.politeness.delay_s = 0.0
    return cfg, SiteCrawler(cfg, **kw)


def _html(body=HTML):
    return (200, {"Content-Type": "text/html"}, body)


def _robots(text: bytes):
    return (200, {"Content-Type": "text/plain"}, text)


# ---------------------------------------------------------------------------------------- C8: robots in full
@pytest.mark.parametrize("status", [404, 401, 403, 410])
def test_c8_a_4xx_robots_answer_allows(tmp_path, monkeypatch, loopback, status):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (status, {}, b"User-agent: *\nDisallow: /\n"), "/page": _html()}
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        assert c._get(f"http://{host}/page") is not None
    finally:
        c.close()


@pytest.mark.parametrize("status", [500, 502, 503])
def test_c8_a_5xx_robots_answer_forbids(tmp_path, monkeypatch, loopback, status):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (status, {}, b""), "/page": _html()}
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        assert c._get(f"http://{host}/page") is None
        assert c.last_failure == "robots"
    finally:
        c.close()
    assert (host, "/page") not in log  # never even requested


def test_c8_a_robots_file_of_600_kib_is_read_to_at_least_500_kib(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    filler = b"# padding line to make the file long\n"
    early = b"User-agent: *\nDisallow: /deep-rule\n"  # ~400 KiB in
    late = b"Disallow: /late-rule\n"  # beyond the bound (560 KiB in)
    body = (filler * (400 * 1024 // len(filler))) + early + (filler * (160 * 1024 // len(filler))) + late
    body += filler * ((600 * 1024 - len(body)) // len(filler) + 1)
    assert len(body) >= 600 * 1024 and ROBOTS_MAX_BYTES >= 500 * 1024
    assert body.index(b"/deep-rule") > 400 * 1024 and body.index(b"/late-rule") > ROBOTS_MAX_BYTES
    sites[host] = {"/robots.txt": _robots(body), "/deep-rule": _html(), "/late-rule": _html()}
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        assert c._get(f"http://{host}/deep-rule") is None and c.last_failure == "robots"
        # the bound is documented: RFC 9309 asks for 500 KiB, a rule past the bound is not read
        assert c._get(f"http://{host}/late-rule") is not None
    finally:
        c.close()


def test_c8_a_robots_answer_lives_24_hours(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": _robots(b"User-agent: *\nDisallow: /private\n"), "/page": _html()}
    now = [1000.0]
    _, c = _crawler(tmp_path, monkeypatch, clock=lambda: now[0])
    robots_calls = lambda: sum(1 for h, p in log if p == "/robots.txt")  # noqa: E731
    try:
        assert c._get(f"http://{host}/page") is not None
        assert robots_calls() == 1
        now[0] += ROBOTS_TTL_S - 1  # just under 24 hours: the answer is still used
        assert c._get(f"http://{host}/page") is not None
        assert robots_calls() == 1
        # the site changes its mind; at 24 hours the new answer is read
        sites[host]["/robots.txt"] = _robots(b"User-agent: *\nDisallow: /page\n")
        now[0] += 1
        assert c._get(f"http://{host}/page") is None and c.last_failure == "robots"
        assert robots_calls() == 2
    finally:
        c.close()
    assert ROBOTS_TTL_S == 86400


def test_c8_robots_found_through_a_redirect_is_read(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {
        "/robots.txt": (301, {"Location": "/rules.txt"}, b""),
        "/rules.txt": _robots(b"User-agent: *\nDisallow: /secret\n"),
        "/secret": _html(), "/open": _html(),
    }
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        assert c._get(f"http://{host}/secret") is None and c.last_failure == "robots"
        assert c._get(f"http://{host}/open") is not None
    finally:
        c.close()


def test_c8_a_robots_redirect_without_end_forbids(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (302, {"Location": "/robots.txt"}, b""), "/page": _html()}
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        assert c._get(f"http://{host}/page") is None and c.last_failure == "robots"
    finally:
        c.close()
    assert (host, "/page") not in log


# ------------------------------------------- C8 addition: the robots check on a CROSS-SITE redirect hop
def test_c8_cross_site_redirect_hop_is_checked_against_the_other_sites_robots(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    here, there = f"127.0.0.1:{port}", f"localhost:{port}"  # two sites: two site keys
    sites[here] = {
        "/robots.txt": (404, {}, b""),  # the first site allows everything
        "/go-private": (302, {"Location": f"http://{there}/private/x"}, b""),
        "/go-public": (302, {"Location": f"http://{there}/public/x"}, b""),
    }
    sites[there] = {
        "/robots.txt": _robots(b"User-agent: *\nDisallow: /private\n"),  # the other site forbids /private
        "/private/x": _html(b"<html><body>private</body></html>"),
        "/public/x": _html(b"<html><body>public</body></html>"),
    }
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        # control: the same hop to a path the other site allows IS fetched, so the refusal below is the check
        ok = c._get(f"http://{here}/go-public")
        assert ok is not None and str(ok.url) == f"http://{there}/public/x"
        assert (there, "/public/x") in log
        assert c._get(f"http://{here}/go-private") is None
        assert c.last_failure == "robots"
    finally:
        c.close()
    assert (there, "/private/x") not in log  # the forbidden path was never requested
    assert (there, "/robots.txt") in log  # the other site's own robots.txt was read at the hop


# ------------------------------------------------------------------------- C9: a refusal is final (zero starts)
class _FakeStarter:
    """Stands in for the one function that opens a browser. Counts starts; checks the profile folder it is given."""

    def __init__(self):
        self.starts: list[str] = []
        self.state_seen_at_start: list[bool] = []

    def __call__(self, url, cfg, profile_dir):
        from leadforge.browser_profile import LOCAL_STATE

        self.starts.append(url)
        self.state_seen_at_start.append((profile_dir / LOCAL_STATE).is_file())
        return "<html><body>rendered by the fake: <a href='mailto:hi@rendered.example'>hi</a></body></html>"


@pytest.fixture
def fake_browser(monkeypatch):
    from leadforge.enrich import browser

    starter = _FakeStarter()
    monkeypatch.setattr(browser, "is_available", lambda: True)
    monkeypatch.setattr(browser, "_render_with_crawl4ai", starter)
    return starter


def _business(website):
    return {"id": 1, "website": website, "domain": "garage.example", "category": "car garage", "address_country": "GB"}


def _process(tmp_path, monkeypatch, website):
    from leadforge.enrich import runner
    from leadforge.util import HostThrottle

    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    return runner._process_one(cfg, HostThrottle(0), _business(website))


@pytest.mark.parametrize("status", [403, 429])
def test_c9_a_refusal_starts_zero_browsers(tmp_path, monkeypatch, loopback, fake_browser, status):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (404, {}, b""), "/": (status, {}, b"no")}
    out = _process(tmp_path, monkeypatch, f"http://{host}/")
    assert fake_browser.starts == []  # ZERO browser starts
    assert out["ok"] is False and out["needs_browser"] is False
    assert f"status:{status}" in out["error"]


@pytest.mark.parametrize("status", [406, 503])
def test_c9_other_block_shaped_statuses_still_get_the_browser(tmp_path, monkeypatch, loopback, fake_browser, status):
    """'Other cases unchanged' - and the control that makes the zero above mean something: the fake starter works."""
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (404, {}, b""), "/": (status, {}, b"no")}
    out = _process(tmp_path, monkeypatch, f"http://{host}/")
    assert len(fake_browser.starts) == 1
    assert fake_browser.state_seen_at_start == [True]  # the profile folder held its seeded file at the first start
    assert out["ok"] is True and "hi@rendered.example" in out["emails"]


@pytest.mark.parametrize("status,starts", [(403, 0), (429, 0), (200, 1)])
def test_c9_render_check_force_does_not_go_round_a_refusal(tmp_path, monkeypatch, loopback, fake_browser, status, starts):
    from typer.testing import CliRunner

    from leadforge.cli import app

    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (404, {}, b""), "/": (status, {"Content-Type": "text/html"}, HTML)}
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(app, ["render-check", f"http://{host}/", "--force"])
    assert len(fake_browser.starts) == starts


# -------------------------------------------------------------- C10: no crawl that skips the robots check
@pytest.mark.parametrize("value", ["true", "false"])
def test_c10_the_email_crawl_key_is_refused_with_a_message(tmp_path, monkeypatch, value):
    from pydantic import ValidationError

    (tmp_path / "leadforge.yaml").write_text(f"discovery:\n  email_crawl: {value}\n", encoding="utf-8")
    with pytest.raises(ValidationError, match=r"discovery\.email_crawl was removed.*robots\.txt"):
        load_config(tmp_path)


def test_c10_the_environment_cannot_set_it_either(tmp_path, monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("LEADFORGE_DISCOVERY__EMAIL_CRAWL", "true")
    with pytest.raises(ValidationError, match="email_crawl was removed"):
        load_config(tmp_path)


def test_c10_the_helper_never_gets_the_email_argument(tmp_path, monkeypatch):
    from leadforge.grid import PlannedQuery
    from leadforge.providers import gosom as gosom_mod
    from leadforge.providers.gosom import GosomProvider

    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    captured: dict = {}

    def fake_run(args, out, t, **kw):
        captured["args"] = args
        out.write_text("", encoding="utf-8")
        return {"returncode": 0, "stderr": ""}, False

    monkeypatch.setattr(gosom_mod, "gosom_path", lambda cfg: "gosom-fake")
    monkeypatch.setattr(GosomProvider, "_run_with_watchdog", staticmethod(fake_run))
    GosomProvider(cfg).fetch(PlannedQuery(text="x in y", category="", area="", tile=None))
    assert captured["args"] and "-email" not in captured["args"]


# --------------------------------------------------------------- C11: protected e-mail addresses
def _cfemail(addr, key=0x42):
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in addr)


def test_c11_a_protected_address_is_not_stored_by_default(tmp_path, monkeypatch, loopback):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    page = f'<html><body><p>Contact us</p><span class="__cf_email__" data-cfemail="{_cfemail("owner@garage.example")}">[email&#160;protected]</span></body></html>'
    sites[host] = {"/robots.txt": (404, {}, b""), "/": _html(page.encode())}
    out = _process(tmp_path, monkeypatch, f"http://{host}/")
    assert out["ok"] is True and out["emails"] == {}  # the address is not stored


def test_c11_decoding_is_on_request_only(tmp_path, monkeypatch, loopback):
    from leadforge.enrich import runner
    from leadforge.util import HostThrottle

    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    page = f'<html><body><span data-cfemail="{_cfemail("owner@garage.example")}">[email&#160;protected]</span></body></html>'
    sites[host] = {"/robots.txt": (404, {}, b""), "/": _html(page.encode())}
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.crawl.decode_protected_emails = True
    out = runner._process_one(cfg, HostThrottle(0), _business(f"http://{host}/"))
    assert "owner@garage.example" in out["emails"]


@pytest.mark.parametrize("status,eligible,refused", [(403, False, True), (429, False, True), (406, True, False), (401, True, False)])
def test_c9_the_crawler_marks_a_refusal_and_does_not_offer_the_browser(tmp_path, monkeypatch, loopback, status, eligible, refused):
    port, sites, log = loopback
    host = f"127.0.0.1:{port}"
    sites[host] = {"/robots.txt": (404, {}, b""), "/": (status, {}, b"no")}
    _, c = _crawler(tmp_path, monkeypatch)
    try:
        res = c.crawl(f"http://{host}/")
    finally:
        c.close()
    assert (res.needs_browser, res.refused) == (eligible, refused)


def test_c11_the_extractor_does_not_decode_unless_told_to():
    from leadforge.enrich.extract import extract_emails

    html = f'<span data-cfemail="{_cfemail("owner@garage.example")}">[email&#160;protected]</span>'
    assert extract_emails(html, "") == {}
    assert "owner@garage.example" in extract_emails(html, "", decode_protected=True)
