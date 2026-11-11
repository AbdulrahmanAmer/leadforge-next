"""C3 (slice L2b): nothing downloaded unchecked.

The helper binary is pinned by version and SHA-256 and a file that does not match is refused and deleted;
the NER model is pinned by revision; `run` with an old doctor stamp opens no socket. All offline: the
"download" is served by httpx.MockTransport and every socket call is blocked and recorded."""
import hashlib
import json
import queue
import socket
import sys
import time
import types

import httpx
import pytest
from typer.testing import CliRunner

from leadforge import doctor
from leadforge.cli import app
from leadforge.config import load_config
from leadforge.util import EnvError

FAKE_BINARY = b"MZ this is a made-up file, not the pinned gosom release\n"


@pytest.fixture
def no_sockets(monkeypatch):
    """Every way out to the network records the attempt and fails."""
    attempts: list[str] = []

    def _blocked(name):
        def _raise(*a, **k):
            attempts.append(f"{name}{a[1:2] or a[:1]}")
            raise OSError(f"network blocked by test ({name})")
        return _raise

    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, _blocked(f"socket.{name}"))
    monkeypatch.setattr(socket, "create_connection", _blocked("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", _blocked("getaddrinfo"))
    return attempts


def _never_run(*a, **k):
    raise AssertionError(f"a binary was executed: {a[:1]}")


# ------------------------------------------------------------------ the pinned helper binary
def test_every_pinned_asset_has_a_sha256():
    assert doctor.gosom_asset_name() in doctor.GOSOM_SHA256
    for name, digest in doctor.GOSOM_SHA256.items():
        assert doctor.GOSOM_VERSION in name
        assert len(digest) == 64 and int(digest, 16) >= 0


def test_doctored_binary_is_refused_deleted_and_never_run(cfg, monkeypatch):
    path = doctor.gosom_path(cfg)
    path.write_bytes(FAKE_BINARY)  # right name, wrong bytes
    monkeypatch.setattr(doctor.subprocess, "run", _never_run)

    assert doctor.gosom_runs(path) is False
    assert not path.exists(), "a binary with the wrong SHA-256 must be deleted"

    path.write_bytes(FAKE_BINARY)
    rep = doctor.run_doctor(cfg, network=False)
    gosom = next(r for r in rep.results if r.name == "gosom-binary")
    assert gosom.ok is False and "refused and deleted" in gosom.msg
    assert not path.exists()


def _serve(monkeypatch, body: bytes, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=body)

    real_client = httpx.Client
    monkeypatch.setattr(doctor.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


def test_download_with_wrong_hash_is_refused_and_deleted(cfg, monkeypatch):
    seen: list[str] = []
    _serve(monkeypatch, FAKE_BINARY, seen)
    dest = doctor.gosom_path(cfg)

    with pytest.raises(EnvError, match="refused and deleted"):
        doctor.download_gosom(cfg)
    assert seen == [f"https://github.com/{doctor.GOSOM_REPO}/releases/download/v{doctor.GOSOM_VERSION}/"
                    f"{doctor.gosom_asset_name()}"], "only the pinned release URL, no API lookup"
    assert not dest.exists()
    assert list(dest.parent.iterdir()) == [], "no partial file left behind"


def test_download_with_the_pinned_hash_is_kept(cfg, monkeypatch):
    seen: list[str] = []
    _serve(monkeypatch, FAKE_BINARY, seen)
    monkeypatch.setitem(doctor.GOSOM_SHA256, doctor.gosom_asset_name(), hashlib.sha256(FAKE_BINARY).hexdigest())

    assert doctor.download_gosom(cfg).read_bytes() == FAKE_BINARY
    assert len(seen) == 1


# ------------------------------------------------------------------ the model file
@pytest.fixture
def fake_gliner(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class GLiNER:
        @classmethod
        def from_pretrained(cls, name, **kw):
            calls.append((name, kw))
            return cls()

        def to(self, device):
            return self

    monkeypatch.setitem(sys.modules, "gliner", types.SimpleNamespace(GLiNER=GLiNER))
    return calls


def test_model_is_loaded_by_pinned_revision(fake_gliner, monkeypatch):
    from leadforge.enrich import extract, ner_worker

    pin = ner_worker.MODEL_REVISIONS[ner_worker.MODEL_NAME]
    assert len(pin) == 40 and int(pin, 16) >= 0  # a commit id, not a branch name like "main"

    monkeypatch.setattr(extract, "_GLINER_MODEL", None)
    monkeypatch.setattr(extract, "_apply_torch_threads", lambda: None)
    extract._gliner_model()

    req_q, resp_q, ready_q = queue.Queue(), queue.Queue(), queue.Queue()
    req_q.put(None)  # shutdown sentinel: load, report ready, stop
    ner_worker._worker_main(req_q, resp_q, ready_q, "cpu", ner_worker.MODEL_NAME, 1, 0)

    assert fake_gliner == [(ner_worker.MODEL_NAME, {"revision": pin})] * 2


def test_unpinned_model_is_refused():
    from leadforge.enrich import ner_worker

    with pytest.raises(ValueError, match="no pinned revision"):
        ner_worker.pinned_revision("someone/other-model")


# ------------------------------------------------------------------ nothing downloads inside `run`
def _old_stamp(cfg):
    (cfg.data_path / doctor.STAMP_NAME).write_text(json.dumps(
        {"at": "2026-01-01T00:00:00Z", "t": time.time() - 48 * 3600, "gosom": doctor.GOSOM_VERSION}),
        encoding="utf-8")


def test_run_with_old_stamp_makes_no_network_call(tmp_path, monkeypatch, no_sockets):
    """The real `run` command, its real ensure_ready, an old stamp and no helper binary: it stops with
    the doctor's fix and never reaches for the network."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "answers.yaml").write_text(
        "campaign: t\noffer:\n  what: Web redesign\n"
        "target:\n  categories: [auto repair shop]\n"
        "  geography:\n    country: US\n    areas: ['Houston, TX']\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["--json", "intake", "--answers", "answers.yaml"]).exit_code == 0
    _old_stamp(load_config(tmp_path))

    res = runner.invoke(app, ["--json", "run", "--icp", "icp.yaml"])

    assert no_sockets == [], f"run opened the network: {no_sockets}"
    assert res.exit_code != 0
    digest = json.loads(next(ln for ln in res.output.splitlines() if ln.startswith("LF_DIGEST "))[10:])
    assert digest["ok"] is False
    assert "gosom-binary (leadforge doctor --fix)" in json.dumps(digest)


def test_old_stamp_with_a_good_install_passes_offline_and_refreshes(cfg, monkeypatch, no_sockets):
    monkeypatch.setattr(doctor, "gosom_runs", lambda path: True)
    _old_stamp(cfg)

    doctor.ensure_ready(cfg)

    assert no_sockets == []
    stamp = json.loads((cfg.data_path / doctor.STAMP_NAME).read_text(encoding="utf-8"))
    assert time.time() - stamp["t"] < 60
