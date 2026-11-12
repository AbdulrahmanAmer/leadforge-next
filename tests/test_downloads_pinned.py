"""C3 (slice L2b): nothing downloaded unchecked.

The NER model is pinned by revision (the helper binary's own pin moved to the Maps add-on, slice L8); `run` with an old doctor stamp opens no socket. All offline: the
"download" is served by a fake and every socket call is blocked and recorded."""
import importlib.machinery
import json
import os
import queue
import socket
import sys
import time
import types

import pytest
from typer.testing import CliRunner

from leadforge import doctor
from leadforge.cli import app
from leadforge.config import load_config


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

    assert fake_gliner == [(ner_worker.MODEL_NAME, {"revision": pin, "local_files_only": True})] * 2


def test_unpinned_model_is_refused():
    from leadforge.enrich import ner_worker

    with pytest.raises(ValueError, match="no pinned revision"):
        ner_worker.pinned_revision("someone/other-model")


# ------------------------------------------------------------------ the model and its tokenizer inside `run`
MODEL_LIBS = ("gliner", "transformers", "huggingface_hub", "torch")


def _report_env_target(req_q, resp_q, ready_q, device, model_name, batch_size, batch_wait_ms):
    """Spawned in a real child process: reports the offline switches and which model libraries were
    already imported when the loader would start."""
    import os as _os
    import sys as _sys
    ready_q.put(("ok", json.dumps({
        "HF_HUB_OFFLINE": _os.environ.get("HF_HUB_OFFLINE"),
        "TRANSFORMERS_OFFLINE": _os.environ.get("TRANSFORMERS_OFFLINE"),
        "imported": [m for m in MODEL_LIBS if m in _sys.modules]})))
    req_q.get(timeout=30)


def test_loader_process_is_offline_before_model_libraries_load(monkeypatch):
    from leadforge.enrich.ner_worker import NerWorker

    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    w = NerWorker(device="cpu", target=_report_env_target, start_timeout_s=60.0)
    try:
        assert w.start_error is None, w.start_error
        seen = json.loads(w.started_device)
    finally:
        w.shutdown()
    assert seen == {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "imported": []}
    assert "HF_HUB_OFFLINE" not in os.environ, "the switches belong to the loading process, not the caller"


def _hub_like_gliner(monkeypatch, calls: list):
    """A made-up gliner whose loader behaves like the Hub client: unless it is offline or asked for local
    files only, a model it does not have is fetched over the network."""
    class GLiNER:
        @classmethod
        def from_pretrained(cls, name, **kw):
            calls.append((name, kw))
            if not kw.get("local_files_only") and os.environ.get("HF_HUB_OFFLINE") != "1":
                socket.create_connection(("huggingface.co", 443))
            raise OSError("not in the local cache")

    mod = types.ModuleType("gliner")
    mod.__spec__ = importlib.machinery.ModuleSpec("gliner", None)
    mod.GLiNER = GLiNER
    monkeypatch.setitem(sys.modules, "gliner", mod)


def test_run_ner_path_with_empty_cache_opens_no_socket_and_warns_once(cfg, tmp_path, monkeypatch,
                                                                        no_sockets, caplog):
    from leadforge.enrich import extract, ner_worker, runner

    calls: list = []
    _hub_like_gliner(monkeypatch, calls)
    monkeypatch.delenv("LEADFORGE_NO_NER_MODEL", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-hub-cache"))
    cfg.enrich.ner = True

    class InProcessWorker:  # the real loader, run in this process so the socket guard sees it
        def __init__(self, **kw):
            self.start_error = None
            req_q, ready_q = queue.Queue(), queue.Queue()
            req_q.put(None)
            ner_worker._worker_main(req_q, queue.Queue(), ready_q, "cpu", ner_worker.MODEL_NAME, 1, 0)
            status, info = ready_q.get_nowait()
            self.start_error = None if status == "ok" else info
            self.available = status == "ok"

        def shutdown(self):
            pass

    monkeypatch.setattr(ner_worker, "NerWorker", InProcessWorker)
    caplog.set_level("WARNING")
    try:
        runner._start_ner_worker(cfg)
        people = runner._people_fn(cfg)("Jane Smith, Owner of the shop", "https://shop.example/")
    finally:
        runner._stop_ner_worker()

    assert no_sockets == [], f"the NER path opened the network: {no_sockets}"
    assert calls == [], "no model load is attempted when the cache is empty"
    assert isinstance(people, list)  # the heuristic extractor carried on
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING" and "ner" in r.getMessage().lower()]
    assert len(warned) == 1, warned
    assert "leadforge doctor --fix --full" in warned[0]

    extract_calls: list = []
    _hub_like_gliner(monkeypatch, extract_calls)
    monkeypatch.setattr(extract, "_GLINER_MODEL", None)
    with pytest.raises(OSError, match="not in the local cache"):
        extract._gliner_model()
    assert no_sockets == [], f"the in-thread loader opened the network: {no_sockets}"
    assert extract_calls[0][1].get("local_files_only") is True


def test_in_thread_loader_refuses_when_the_hub_client_was_imported_online(monkeypatch, no_sockets):
    from leadforge.enrich import extract

    calls: list = []
    _hub_like_gliner(monkeypatch, calls)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.ModuleType("huggingface_hub"))
    monkeypatch.setattr(extract, "_GLINER_MODEL", None)
    with pytest.raises(RuntimeError, match="imported before the offline switches"):
        extract._gliner_model()
    assert calls == [] and no_sockets == []


def test_doctor_fetch_pins_the_model_and_the_tokenizer(tmp_path, monkeypatch):
    from leadforge.enrich import ner_worker

    hub = tmp_path / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    files = {ner_worker.MODEL_NAME: ["gliner_config.json", "pytorch_model.bin"],
             ner_worker.BACKBONE_NAME: ["config.json", "spm.model", "tokenizer_config.json"]}
    calls: list = []

    def snapshot_download(repo_id, **kw):
        if not kw.get("revision"):
            raise AssertionError(f"{repo_id} fetched by name with no revision")
        calls.append((repo_id, kw["revision"]))
        snap = hub / ("models--" + repo_id.replace("/", "--")) / "snapshots" / kw["revision"]
        snap.mkdir(parents=True)
        for name in files[repo_id]:
            (snap / name).write_bytes(b"made up")
        return str(snap)

    mod = types.ModuleType("huggingface_hub")
    mod.snapshot_download = snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", mod)
    assert ner_worker.ner_cache_ready() is False

    doctor.fetch_ner_model()

    tok_pin = ner_worker.MODEL_REVISIONS[ner_worker.BACKBONE_NAME]
    assert len(tok_pin) == 40 and int(tok_pin, 16) >= 0
    assert calls == [(ner_worker.MODEL_NAME, ner_worker.MODEL_REVISIONS[ner_worker.MODEL_NAME]),
                     (ner_worker.BACKBONE_NAME, tok_pin)]
    assert ner_worker.ner_cache_ready() is True


# ------------------------------------------------------------------ nothing downloads inside `run`
def _old_stamp(cfg):
    (cfg.data_path / doctor.STAMP_NAME).write_text(json.dumps(
        {"at": "2026-01-01T00:00:00Z", "t": time.time() - 48 * 3600}),
        encoding="utf-8")


def test_run_with_old_stamp_makes_no_network_call(tmp_path, monkeypatch, no_sockets):
    """The real `run` command, its real ensure_ready, an old stamp and a missing dependency: it stops with
    the doctor's fix and never reaches for the network."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "CORE_IMPORTS", [*doctor.CORE_IMPORTS, "leadforge_made_up_missing_module"])
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
    assert "core-imports (pip install -e <repo-root>)" in json.dumps(digest)


def test_old_stamp_with_a_good_install_passes_offline_and_refreshes(cfg, monkeypatch, no_sockets):
    _old_stamp(cfg)

    doctor.ensure_ready(cfg)

    assert no_sockets == []
    stamp = json.loads((cfg.data_path / doctor.STAMP_NAME).read_text(encoding="utf-8"))
    assert time.time() - stamp["t"] < 60
