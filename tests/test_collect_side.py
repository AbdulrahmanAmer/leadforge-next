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
