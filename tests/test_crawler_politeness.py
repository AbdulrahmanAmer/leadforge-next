"""U8.1: politeness invariants proved against a real local HTTP server (127.0.0.1 only).

v0.3 speed unit (2026-09-02): extended with the fail-fast-tail + workers=12 politeness proofs
(build items 1 and 3) — see the block near the bottom of this file.
"""
import http.server
import threading
import time

import pytest

from leadforge.config import load_config
from leadforge.enrich.crawler import SiteCrawler


class _Handler(http.server.BaseHTTPRequestHandler):
    requests: list[str] = []
    request_times: list[float] = []  # v0.3 speed unit: monotonic timestamp per request, for pacing proofs
    home_html = b"<html><body>hello</body></html>"
    robots = b""
    page_status = 200  # non-robots paths: set 403 to fake a WAF block
    delay_by_path: dict[str, float] = {}  # v0.3 speed unit: {"/about-0": 0.3} — simulate a slow page

    robots_status = 200

    def do_GET(self):  # noqa: N802 — http.server API
        type(self).requests.append(self.path)
        type(self).request_times.append(time.monotonic())
        delay = type(self).delay_by_path.get(self.path)
        if delay:
            time.sleep(delay)
        if self.path == "/robots.txt":
            if type(self).robots_status != 200:
                self.send_response(type(self).robots_status)
                self.end_headers()
                return
            body = self.robots
        elif self.path.endswith(".xml"):
            self.send_response(404)
            self.end_headers()
            return
        elif type(self).page_status != 200:
            self.send_response(type(self).page_status)
            self.end_headers()
            return
        else:
            body = self.home_html
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def server():
    class H(_Handler):
        requests = []
        request_times = []
        robots = b""
        home_html = _Handler.home_html
        page_status = 200
        robots_status = 200
        delay_by_path = {}

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", H
    srv.shutdown()


def _crawler(tmp_path, monkeypatch, delay=0.0):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.politeness.delay_s = delay
    return cfg, SiteCrawler(cfg)


def test_per_host_delay_is_honored(tmp_path, monkeypatch, server):
    base, handler = server
    cfg, crawler = _crawler(tmp_path, monkeypatch, delay=1.0)
    try:
        t0 = time.monotonic()
        assert crawler._get(f"{base}/") is not None
        assert crawler._get(f"{base}/again") is not None
        elapsed = time.monotonic() - t0
    finally:
        crawler.close()
    # robots fetch + 2 pages = at least 2 waits on one host; jitter is ±30%
    assert elapsed >= 0.7, f"two same-host fetches took only {elapsed:.2f}s with delay_s=1.0"


def test_robots_disallow_is_respected(tmp_path, monkeypatch, server):
    base, handler = server
    handler.robots = b"User-agent: *\nDisallow: /private\n"
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        assert crawler._get(f"{base}/private") is None
    finally:
        crawler.close()
    assert "/private" not in handler.requests  # never even requested


def test_crawl_of_robots_disallowed_home_never_flags_browser(tmp_path, monkeypatch, server):
    """The red line, proven at crawl() level against a real server (the runner-level test
    monkeypatches crawl() away, which is how a needs_browser mutation once went green)."""
    base, handler = server
    handler.robots = b"User-agent: *\nDisallow: /\n"
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is False and res.error == "robots-disallowed"
    assert res.needs_browser is False  # a site that said no must never be browser-rendered
    assert all(p == "/robots.txt" for p in handler.requests)  # homepage never even requested


def test_crawl_of_blocked_home_flags_browser(tmp_path, monkeypatch, server):
    base, handler = server
    handler.page_status = 403  # WAF-style block for the plain HTTP client; robots readable + permissive
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is False
    assert res.needs_browser is True


def test_crawl_of_dead_home_does_not_flag_browser(tmp_path, monkeypatch, server):
    """404/timeouts/PDFs gain nothing from Chromium — only block-shaped statuses escalate."""
    base, handler = server
    handler.page_status = 404
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is False
    assert res.needs_browser is False
    assert "404" in res.error


def test_unreachable_robots_is_treated_as_disallow(tmp_path, monkeypatch, server):
    """RFC 9309 §2.3.1.4: a 5xx robots.txt means assume complete disallow — and a site whose
    robots policy was never readable must not be browser-rendered either."""
    base, handler = server
    handler.robots_status = 503
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is False and res.error == "robots-disallowed"
    assert res.needs_browser is False
    assert all(p == "/robots.txt" for p in handler.requests)


def test_final_host_http_status_and_offsite_redirect(tmp_path, monkeypatch, server):
    """v0.3 unit C1: crawl()'s new signals against a real server (not a mock) — final_host and
    http_status are always set from the actual response; offsite_redirect compares final_host to the
    caller-supplied business_domain, www-insensitive, and stays False with no business_domain given."""
    base, handler = server
    host = base.split("//", 1)[1]  # "127.0.0.1:PORT" — no www to strip either side
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        same = crawler.crawl(base, business_domain=host)
        diff = crawler.crawl(base, business_domain="totally-different.example")
        no_domain = crawler.crawl(base)
    finally:
        crawler.close()
    assert same.signals["http_status"] == 200
    assert same.signals["final_host"] == host.casefold()
    assert same.signals["offsite_redirect"] is False
    assert diff.signals["offsite_redirect"] is True
    assert no_domain.signals["offsite_redirect"] is False  # nothing to compare against -> never flagged


def test_pages_per_site_cap(tmp_path, monkeypatch, server):
    base, handler = server
    links = "".join(f'<a href="/about-{i}">about {i}</a>' for i in range(20))
    handler.home_html = f"<html><body>{links}</body></html>".encode()
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok
    page_hits = [p for p in handler.requests if p.startswith("/about") or p == "/"]
    assert len(res.pages) <= cfg.crawl.pages_per_site
    assert len(page_hits) <= cfg.crawl.pages_per_site


# ==================================================================== v0.3 speed unit (2026-09-02)
# build item 1: fail-fast on the slow tail (site budget, per-page timeouts, dead-host cache).

def test_site_budget_stops_further_pages(tmp_path, monkeypatch, server):
    """1a: once cfg.crawl.site_budget_s is exceeded, crawl() stops fetching further pages and
    returns what it already collected — still ok=True (the home page loaded), with
    signals['budget_exhausted']=True. A budget of 0 is exceeded immediately after the home fetch,
    so NONE of the 5 candidate links are ever requested — the sharpest, most deterministic proof."""
    base, handler = server
    links = "".join(f'<a href="/about-{i}">about {i}</a>' for i in range(5))
    handler.home_html = f"<html><body>{links}</body></html>".encode()
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    cfg.crawl.site_budget_s = 0.0
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is True  # partial success: the home page loaded
    assert res.signals.get("budget_exhausted") is True
    assert len(res.pages) == 1  # home only
    assert not any(p.startswith("/about") for p in handler.requests)


def test_site_budget_not_exhausted_when_ample(tmp_path, monkeypatch, server):
    """Watched-fail control for the test above: a generous budget must NOT set budget_exhausted or
    block the candidate-page fetches — proves the flag isn't hardcoded True."""
    base, handler = server
    handler.home_html = b'<html><body><a href="/about-0">about</a></body></html>'
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    cfg.crawl.site_budget_s = 60.0
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert "budget_exhausted" not in res.signals
    assert any(p.startswith("/about") for p in handler.requests)


def test_secondary_page_uses_page_timeout_not_home_timeout(tmp_path, monkeypatch, server):
    """1b: the home fetch uses the client's default (cfg.crawl.timeout_s); a secondary/candidate page
    fetch is called with an explicit timeout override equal to cfg.crawl.page_timeout_s, which is
    shorter by default (6s vs 10s)."""
    base, handler = server
    handler.home_html = b'<html><body><a href="/about-0">about</a></body></html>'
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    assert cfg.crawl.page_timeout_s < cfg.crawl.timeout_s  # the config invariant itself
    calls: list[tuple[str, object]] = []
    orig_get = crawler.client.get

    def spy_get(url, **kwargs):
        calls.append((url, kwargs.get("timeout")))
        return orig_get(url, **kwargs)

    monkeypatch.setattr(crawler.client, "get", spy_get)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok
    about_calls = [t for u, t in calls if u.endswith("/about-0")]
    home_calls = [t for u, t in calls if "robots.txt" not in u and not u.endswith("/about-0")]
    assert home_calls, f"no home-page call recorded among {calls!r}"
    assert home_calls[0] is None  # no override -> client default (home timeout)
    assert about_calls and about_calls[0] == cfg.crawl.page_timeout_s


def test_home_block_status_never_fetches_secondary_pages(tmp_path, monkeypatch, server):
    """1c, made explicit + tested (was already true structurally: a None from _get(website) returns
    before the candidate-links loop is ever reached). A 403 home page with real links present must
    produce ZERO secondary-page requests."""
    base, handler = server
    links = "".join(f'<a href="/about-{i}">about {i}</a>' for i in range(5))
    handler.home_html = f"<html><body>{links}</body></html>".encode()
    handler.page_status = 403
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(base)
    finally:
        crawler.close()
    assert res.ok is False
    assert res.needs_browser is True  # block-shaped status -> browser-eligible
    assert not any(p.startswith("/about") for p in handler.requests)


def test_dead_host_cached_after_connection_failure(monkeypatch):
    """1d: a DNS/connection failure marks the host dead PROCESS-WIDE (class-level cache) — a second,
    completely fresh SiteCrawler instance (as _process_one creates per business) hitting the SAME host
    must short-circuit without making any network call at all, proving a chain of N businesses on one
    dead host costs one connection failure, not N."""
    import httpx as _httpx

    from leadforge.enrich.crawler import SiteCrawler

    SiteCrawler.reset_dead_hosts()
    try:
        cfg = load_config(".")
        host = "dead-host-cache-test.invalid:1"
        url = f"http://{host}/"

        crawler1 = SiteCrawler(cfg)

        def boom(*a, **k):
            raise _httpx.ConnectError("simulated dead host")

        monkeypatch.setattr(crawler1.client, "get", boom)
        res1 = crawler1.crawl(url)
        crawler1.close()
        assert res1.ok is False
        assert SiteCrawler._host_dead_reason(host) is not None

        crawler2 = SiteCrawler(cfg)  # fresh instance — its own _robots cache starts empty
        calls: list = []

        def never_call(*a, **k):
            calls.append((a, k))
            raise AssertionError("crawler2 must never touch the network for a known-dead host")

        monkeypatch.setattr(crawler2.client, "get", never_call)
        res2 = crawler2.crawl(url)
        crawler2.close()
        assert calls == []
        assert res2.ok is False
    finally:
        SiteCrawler.reset_dead_hosts()  # the cache is process-wide — never leak it into other tests


def test_read_timeout_does_not_mark_host_dead(monkeypatch):
    """Watched-fail control: a slow-but-alive server (ReadTimeout, not a connection failure) must NOT
    be cached as dead — only DNS/connect failures qualify. Distinguishes _is_connection_failure from
    'any httpx exception', which would over-cache and wrongly disallow every future request to a host
    that is merely slow once."""
    import httpx as _httpx

    from leadforge.enrich.crawler import SiteCrawler

    SiteCrawler.reset_dead_hosts()
    try:
        cfg = load_config(".")
        host = "read-timeout-test.invalid:1"
        url = f"http://{host}/"
        crawler = SiteCrawler(cfg)

        def slow(*a, **k):
            raise _httpx.ReadTimeout("simulated slow server")

        monkeypatch.setattr(crawler.client, "get", slow)
        crawler.crawl(url)
        crawler.close()
        assert SiteCrawler._host_dead_reason(host) is None
    finally:
        SiteCrawler.reset_dead_hosts()


# build item 3: workers 4 -> 12 — per-host pacing must stay unchanged; only cross-host concurrency grows.

def test_workers_12_still_serializes_per_host_but_overlaps_across_hosts(tmp_path, monkeypatch):
    """Two real local servers stand in for two different hosts. A 'chain' of 3 businesses shares
    host A's domain; one business is on host B. Run all 4 through the SAME concurrency shape
    _crawl_stage uses (ThreadPoolExecutor(workers) + a shared HostThrottle) with workers=12:
    consecutive host-A request start times must stay >= delay_s minus the 30% jitter apart; a host-B
    request must land inside host A's own span, proving the two hosts actually ran concurrently rather
    than one waiting for the other to finish entirely.

    Start times are the throttle's own grant times, read from the clock the throttle uses. Arrival
    times at the server also carry each request's connect and thread-scheduling time, which on a busy
    Windows runner varied by up to 0.1 s and made the arrival gap shorter than the start gap (L2
    finding). The server still counts arrivals: every request host A saw must have passed the throttle."""
    import threading as _threading
    import types
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from leadforge import util
    from leadforge.enrich.crawler import SiteCrawler
    from leadforge.enrich.runner import _process_one
    from leadforge.util import HostThrottle

    # The throttle's last clock reading on a thread is its grant time when wait() returns.
    last_read = _threading.local()

    def _perf_counter() -> float:
        last_read.value = time.perf_counter()
        return last_read.value

    monkeypatch.setattr(util, "time", types.SimpleNamespace(
        perf_counter=_perf_counter, monotonic=time.monotonic, sleep=time.sleep, time=time.time))
    grants: dict[str, list[float]] = {}
    grants_lock = _threading.Lock()

    class _RecordingThrottle(HostThrottle):
        def wait(self, host: str) -> None:
            super().wait(host)
            with grants_lock:
                grants.setdefault(host, []).append(last_read.value)

    class _SlowHandler(http.server.BaseHTTPRequestHandler):
        times: list[float] = []
        lock = _threading.Lock()

        def do_GET(self):  # noqa: N802
            with type(self).lock:
                type(self).times.append(time.monotonic())
            if self.path == "/robots.txt":
                self.send_response(404)
                self.end_headers()
                return
            body = b"<html><body>hi</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    class HA(_SlowHandler):
        times = []
        lock = _threading.Lock()

    class HB(_SlowHandler):
        times = []
        lock = _threading.Lock()

    srv_a = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HA)
    srv_b = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HB)
    ta = _threading.Thread(target=srv_a.serve_forever, daemon=True)
    tb = _threading.Thread(target=srv_b.serve_forever, daemon=True)
    ta.start()
    tb.start()
    SiteCrawler.reset_dead_hosts()
    try:
        monkeypatch.chdir(tmp_path)
        cfg = load_config(tmp_path)
        cfg.politeness.workers = 12
        cfg.politeness.delay_s = 0.4
        throttle = _RecordingThrottle(cfg.politeness.delay_s)
        host_a = f"127.0.0.1:{srv_a.server_address[1]}"
        host_b = f"127.0.0.1:{srv_b.server_address[1]}"
        businesses = (
            [{"id": f"a{i}", "website": f"http://{host_a}/loc-{i}", "domain": host_a,
              "address_country": None, "category": None} for i in range(3)]
            + [{"id": "b0", "website": f"http://{host_b}/", "domain": host_b,
                "address_country": None, "category": None}]
        )
        with ThreadPoolExecutor(max_workers=12) as pool:
            futs = [pool.submit(_process_one, cfg, throttle, b) for b in businesses]
            for f in as_completed(futs):
                f.result()
    finally:
        srv_a.shutdown()
        srv_b.shutdown()
        SiteCrawler.reset_dead_hosts()

    a_times = sorted(HA.times)
    b_times = sorted(HB.times)
    a_starts = sorted(grants.get(host_a, []))
    assert len(a_times) >= 2, "expected >=2 requests to host A (robots.txt + home, at least once)"
    assert len(a_starts) == len(a_times), (
        f"host A saw {len(a_times)} requests but the throttle released {len(a_starts)}")
    floor = cfg.politeness.delay_s * (1 - throttle.jitter) - 1e-9
    gaps = [round(t2 - t1, 4) for t1, t2 in zip(a_starts, a_starts[1:], strict=False)]
    assert all(g >= floor for g in gaps), f"host A start gaps under {floor:.3f} s: {gaps}"
    assert b_times, "expected host B to be reached at all"
    assert b_times[0] <= a_times[-1], (
        "host B's first request should land within host A's own span if the two hosts ran "
        f"concurrently (host A span ends {a_times[-1]!r}, host B started {b_times[0]!r})"
    )

def test_throttle_never_releases_a_request_before_its_delay(monkeypatch):
    """L2 finding: on Windows with Python <= 3.12 `time.monotonic()` advances in 15.625 ms ticks. A
    throttle that reads it can release the next request to a host up to one tick BEFORE the delay it
    computed (CI saw a 0.25 s gap against a 0.28 s floor). A virtual clock replays that: `monotonic`
    ticks like Windows, the exact time is what the site sees. The gap must be the full delay."""
    import types

    from leadforge import util

    tick = 0.015625
    now = [0.015]  # 15 ms into a tick: the coarse clock still reads 0.0

    def _sleep(s: float) -> None:
        now[0] += s

    fake = types.SimpleNamespace(
        monotonic=lambda: (now[0] // tick) * tick,  # what GetTickCount64 returns
        perf_counter=lambda: now[0],                 # exact
        sleep=_sleep,
    )
    monkeypatch.setattr(util, "time", fake)
    throttle = util.HostThrottle(0.2, jitter=0.0)
    throttle.wait("site.example")
    first = now[0]
    now[0] = 0.2032  # the next caller arrives just after the tick that follows 0.2 on the coarse clock
    throttle.wait("site.example")
    gap = round(now[0] - first, 4)
    assert gap >= 0.2, f"the second request left {gap} s after the first, before the 0.2 s delay"


def test_every_redirect_hop_waits_its_turn(tmp_path, monkeypatch, server):
    """A redirect is one more request to a site. Each hop the client follows must pass the per-site
    pause like any page: the site may see no request the throttle did not release."""
    from leadforge.util import HostThrottle

    base, handler = server

    def do_get(self):  # noqa: N802 — http.server API
        if self.path.startswith("/old"):
            type(self).requests.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/old2" if self.path == "/old" else "/new")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        _Handler.do_GET(self)

    monkeypatch.setattr(handler, "do_GET", do_get)
    released: list[str] = []

    class _Counting(HostThrottle):
        def wait(self, host: str) -> None:
            super().wait(host)
            released.append(host)

    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    crawler = SiteCrawler(cfg, throttle=_Counting(0.0))
    try:
        resp = crawler._get(f"{base}/old")
    finally:
        crawler.close()
    assert resp is not None and resp.url.path == "/new"
    assert handler.requests == ["/robots.txt", "/old", "/old2", "/new"]
    assert len(released) == len(handler.requests), (
        f"the site saw {len(handler.requests)} requests but the throttle released {len(released)}")


def test_a_redirect_into_a_disallowed_path_is_not_followed(tmp_path, monkeypatch, server):
    """robots.txt is asked about every address the crawler fetches, also one a redirect leads to."""
    base, handler = server
    handler.robots = b"User-agent: *\nDisallow: /private\n"

    def do_get(self):  # noqa: N802 — http.server API
        if self.path == "/old":
            type(self).requests.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/private/page")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        _Handler.do_GET(self)

    monkeypatch.setattr(handler, "do_GET", do_get)
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        resp = crawler._get(f"{base}/old")
        failure = crawler.last_failure
    finally:
        crawler.close()
    assert handler.requests == ["/robots.txt", "/old"], handler.requests
    assert resp is None and failure == "robots"


def test_throttle_treats_a_site_name_in_any_case_as_one_site(monkeypatch):
    """Site names are case-blind: the address as written and the one the HTTP client sends share a pause."""
    import types

    from leadforge import util

    now = [0.0]
    monkeypatch.setattr(util, "time", types.SimpleNamespace(
        perf_counter=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s)))
    throttle = util.HostThrottle(0.2, jitter=0.0)
    throttle.wait("Shop.Example")
    throttle.wait("shop.example")
    assert now[0] >= 0.2, f"the second request left {now[0]} s after the first"


def test_every_path_names_a_site_the_same_way(monkeypatch):
    """The plain fetch, its redirect hops and the browser pass share one pause per site: an address with a
    non-ASCII name, an explicit default port or capitals is the same site as its plain spelling."""
    from leadforge.enrich import browser
    from leadforge.util import site_key

    spellings = ["https://bücher-shop.de/", "https://XN--BCHER-SHOP-9DB.de:443/a", "https://xn--bcher-shop-9db.de/b"]
    assert len({site_key(u) for u in spellings}) == 1, [site_key(u) for u in spellings]

    class _Stop(Exception):
        pass

    class _Recorder:
        def wait(self, host):
            self.host = host
            raise _Stop  # stop before any browser could start

    rec = _Recorder()
    monkeypatch.setattr(browser, "is_available", lambda: True)
    with pytest.raises(_Stop):
        browser.fetch_rendered(spellings[0], None, rec)
    assert rec.host == site_key(spellings[2])


def test_a_home_redirect_refused_by_robots_is_reported_as_robots(tmp_path, monkeypatch, server):
    """A home page that redirects into a disallowed path is a site that said no, not a dead site."""
    base, handler = server
    handler.robots = b"User-agent: *\nDisallow: /private\n"

    def do_get(self):  # noqa: N802 — http.server API
        if self.path == "/":
            type(self).requests.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/private/home")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        _Handler.do_GET(self)

    monkeypatch.setattr(handler, "do_GET", do_get)
    cfg, crawler = _crawler(tmp_path, monkeypatch)
    try:
        res = crawler.crawl(f"{base}/")
    finally:
        crawler.close()
    assert res.error == "robots-disallowed", res.error
