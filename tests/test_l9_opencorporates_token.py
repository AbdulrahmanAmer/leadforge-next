"""L9 item 1 (C2): OpenCorporates takes its token only in the web address (its documentation, quoted in
docs/slices/L9-keys-and-the-agent-call.md), so the provider is off by default, and switched on the token is never
written to a log or an error. A loopback endpoint plays OpenCorporates and records every address it sees."""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from leadforge.config import load_config
from leadforge.providers import registry as regmod

# built at run time from pieces: clearly fake, and no scanner mistakes it for a real token
TOKEN = "-".join(["FAKE", "oc", "token", "0123456789", "not", "real"])
BIZ = {"id": "b1", "name": "Acme Widgets Ltd", "name_norm": "acme widgets", "address_city": "Leeds",
       "address_postal": "LS1 4AB", "address_country": "GB", "address_region": None}


@pytest.fixture
def endpoint(monkeypatch):
    seen: list[str] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):  # noqa: N802
            seen.append(self.path)
            self.send_response(500)
            self.send_header("Content-Length", "0")
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(regmod, "OC_BASE", f"http://127.0.0.1:{srv.server_address[1]}/v0.4")
    yield seen
    srv.shutdown()
    srv.server_close()


def _lookup_all(cfg) -> None:
    for reg in regmod.get_registries(cfg):  # what every enrich path does
        reg.lookup(BIZ)


def test_default_sends_no_token_to_the_endpoint(tmp_path, monkeypatch, endpoint, caplog, capsys):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.registry.opencorporates_token = TOKEN
    caplog.set_level(logging.DEBUG)
    _lookup_all(cfg)
    assert not any(TOKEN in path for path in endpoint), endpoint
    assert endpoint == []  # off by default: not one request
    assert "opencorporates is off" in caplog.text
    out = capsys.readouterr()
    assert TOKEN not in caplog.text + out.out + out.err


def test_switched_on_the_token_is_in_no_log_and_no_error(tmp_path, monkeypatch, endpoint, caplog, capsys):
    monkeypatch.chdir(tmp_path)
    cfg = load_config(tmp_path)
    cfg.registry.opencorporates_token = TOKEN
    cfg.registry.opencorporates_enabled = True
    caplog.set_level(logging.DEBUG)
    _lookup_all(cfg)
    assert len(endpoint) == 1 and TOKEN in endpoint[0]  # the request was made, the address carries the token
    out = capsys.readouterr()
    assert TOKEN not in caplog.text + out.out + out.err
    assert "opencorporates lookup failed" in caplog.text  # the failure is reported ...
    assert "api_token=<hidden>" in caplog.text            # ... and so is the request line, with the token cut
    for rec in caplog.records:
        assert TOKEN not in rec.getMessage()
        assert TOKEN not in str(rec.exc_info or "")
