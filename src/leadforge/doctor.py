"""Environment doctor & self-bootstrap (U0.5).

Checks the machine BEFORE any pipeline work and (with --fix) installs what is missing:
- Python >= 3.11, core imports, writable data dirs, disk space
- network + DNS reachability
- optional extras present (reported, never required)

A 24h ok-stamp keeps repeat checks cheap; pipeline commands call ensure_ready(), which never downloads (C3).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from leadforge.config import Config
from leadforge.util import EnvError, now_iso

STAMP_NAME = ".doctor_ok.json"
CORE_IMPORTS = [
    "typer", "pydantic", "yaml", "httpx", "selectolax", "trafilatura",
    "phonenumbers", "email_validator", "dns", "pyap", "tenacity", "openpyxl",
]
OPTIONAL_EXTRAS = {"crawl4ai": "browser", "gliner": "ner", "usaddress": "addressing"}
# extras --fix --full installs, with the concrete packages to fall back on when there is no
# source checkout to `pip install -e .[extra]` from (non-editable installs live in site-packages)
QUALITY_EXTRAS: list[tuple[str, str, str | None, list[str]]] = [
    ("ner", "gliner", None, ["gliner"]),
    ("browser", "crawl4ai", "crawl4ai-setup", ["crawl4ai"]),
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    fixed: bool = False
    msg: str = ""
    hint: str = ""


@dataclass
class DoctorReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def counts(self) -> dict:
        return {
            "checks": len(self.results),
            "fixed": sum(r.fixed for r in self.results),
            "failed": sum(not r.ok for r in self.results),
        }

    def lines(self) -> list[str]:
        out = []
        for r in self.results:
            tag = "fixed" if r.fixed else ("ok" if r.ok else "FAIL")
            line = f"[{tag}] {r.name}" + (f" — {r.msg}" if r.msg else "")
            if not r.ok and r.hint:
                line += f" | fix: {r.hint}"
            out.append(line)
        return out


# ------------------------------------------------------------------ checks
def install_quality_extras(rep_add) -> None:
    """--fix --full: install the enrichment-quality extras ([ner] GLiNER, [browser] crawl4ai) so a fresh
    machine's first bootstrap yields full-quality sheets, not the heuristic floor."""
    root = _repo_root()
    editable = (root / "pyproject.toml").is_file()  # non-editable installs have no repo to -e

    def _importable_fresh(mod: str) -> bool:
        # a module installed seconds ago is invisible to this process's stale import-path caches;
        # a child interpreter sees the truth
        return subprocess.run([sys.executable, "-c", f"import {mod}"], capture_output=True).returncode == 0

    for extra, probe_mod, post, packages in QUALITY_EXTRAS:
        already = _importable_fresh(probe_mod)
        if not already:
            # editable checkout: install the extra so pins stay authoritative; otherwise install
            # the concrete packages directly ('pip install -e C:\\Python\\Lib[ner]' was the old
            # failure mode under a plain `pip install .`)
            args = ["-e", f"{root}[{extra}]"] if editable else packages
            proc = subprocess.run([sys.executable, "-m", "pip", "install", *args],
                                  capture_output=True, encoding="utf-8", errors="replace")
            ok = proc.returncode == 0 and _importable_fresh(probe_mod)
        else:
            ok = True
        if ok and post and shutil.which(post):
            try:
                subprocess.run([shutil.which(post)], capture_output=True, encoding="utf-8",
                               errors="replace", timeout=600)
            except subprocess.TimeoutExpired:
                # browser download can exceed 10 min on slow links — report, don't crash the doctor
                rep_add(CheckResult(f"extra-{extra}-setup", False, msg=f"{post} timed out",
                                    hint=f"re-run {post} manually (large download)"))
        fix_hint = (f"pip install -e {root}[{extra}]" if editable
                    else f"pip install {' '.join(packages)}")
        rep_add(CheckResult(f"extra-{extra}", ok, fixed=ok and not already,
                            msg="installed" if ok else "install failed",
                            hint="" if ok else fix_hint))
        if ok and extra == "ner":
            try:
                fetch_ner_model()
                rep_add(CheckResult("ner-model", True, msg="pinned model and tokenizer in the local cache"))
            except Exception as e:  # noqa: BLE001 — reported; run keeps NER off until it is fetched
                rep_add(CheckResult("ner-model", False, msg=f"fetch failed: {type(e).__name__}",
                                    hint="re-run leadforge doctor --fix --full"))


def fetch_ner_model() -> None:
    """The ONLY place the NER model and its tokenizer are downloaded (C3), each at its pinned commit.
    The tokenizer repo's refs/main is pointed at its pin: GLiNER asks for it by name, and offline that
    name resolves through refs/main to the pinned snapshot."""
    import importlib

    from leadforge.enrich.ner_worker import BACKBONE_NAME, MODEL_FILES, pinned_revision
    importlib.invalidate_caches()  # huggingface_hub may have been installed seconds ago
    from huggingface_hub import snapshot_download

    for name, files in MODEL_FILES.items():
        rev = pinned_revision(name)
        snap = Path(snapshot_download(name, revision=rev, allow_patterns=list(files)))
        if name == BACKBONE_NAME:
            ref = snap.parent.parent / "refs" / "main"
            ref.parent.mkdir(parents=True, exist_ok=True)
            ref.write_text(rev, encoding="utf-8")


def run_doctor(cfg: Config, fix: bool = False, strict: bool = False, full: bool = False,
               network: bool = True) -> DoctorReport:
    """network=False is the local-only check `run` uses: nothing is downloaded or installed and no
    socket is opened (C3); fixing is left to an explicit `leadforge doctor --fix`."""
    fix = fix and network
    rep = DoctorReport()
    add = rep.results.append
    if fix and full:
        install_quality_extras(add)

    ver = sys.version_info
    add(CheckResult("python>=3.11", ver >= (3, 11), msg=f"{ver.major}.{ver.minor}.{ver.micro}",
                    hint="install Python 3.11+ and reinstall: pip install -e ."))

    missing = [mod for mod in CORE_IMPORTS if not _importable(mod)]
    had_missing = bool(missing)
    if missing and fix and (_repo_root() / "pyproject.toml").is_file():
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(_repo_root())],
                       capture_output=True, encoding="utf-8", errors="replace")
        missing = [m for m in missing if not _importable(m)]
    add(CheckResult("core-imports", not missing, fixed=had_missing and not missing,
                    msg="all present" if not missing else f"missing: {', '.join(missing)}",
                    hint="pip install -e <repo-root>"))

    try:
        for d in (cfg.data_path, cfg.bin_dir, cfg.cache_dir, cfg.exports_dir, cfg.logs_dir):
            probe = d / ".w"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
        add(CheckResult("data-dirs-writable", True, msg=str(cfg.data_path)))
    except OSError as e:
        add(CheckResult("data-dirs-writable", False, msg=str(e), hint="check permissions / --data-dir"))

    free_gb = shutil.disk_usage(cfg.data_path).free / 1e9
    add(CheckResult("disk>=2GB", free_gb >= 2, msg=f"{free_gb:.1f} GB free", hint="free disk space"))

    if network:
        _network_checks(cfg, add)

    extras = [f"{tag}({mod})" for mod, tag in OPTIONAL_EXTRAS.items() if _importable(mod)]
    add(CheckResult("optional-extras", True, msg=", ".join(extras) if extras else
                    "none installed (fine) — [browser]/[ner]/[addressing] available"))

    add(CheckResult("ner-device", True, msg=_ner_device_report(cfg)))

    if rep.ok:
        _write_stamp(cfg)
    if strict and not rep.ok:
        raise EnvError("; ".join(r.name for r in rep.results if not r.ok))
    return rep


def _network_checks(cfg: Config, add) -> None:
    try:
        with httpx.Client(timeout=8) as client:
            client.head("https://github.com")
        add(CheckResult("network", True, msg="https reachable"))
    except httpx.HTTPError as e:
        add(CheckResult("network", False, msg=type(e).__name__, hint="check connectivity"))

    try:
        from leadforge.enrich.validate import get_resolver
        res = get_resolver()
        res.resolve("gmail.com", "MX", lifetime=cfg.validation.dns_timeout_s)
        add(CheckResult("dns-mx", True, msg=f"resolver ok ({', '.join(map(str, res.nameservers[:2]))})"))
    except Exception as e:  # noqa: BLE001 — any resolver failure is the same answer
        add(CheckResult("dns-mx", False, msg=type(e).__name__,
                        hint="email tiers will be 'unknown' until DNS works"))


def _ner_device_report(cfg: Config) -> str:
    """Layer 3: info only, never a failure — reports which device `leadforge enrich` will actually
    use for GLiNER (the model-worker process, enrich/ner_worker.py), not whether NER works at all
    (that is optional-extras' job)."""
    if not cfg.enrich.ner:
        return "off (enrich.ner: false)"
    if not _importable("gliner"):
        return "off ([ner] extra not installed — heuristic extractor only)"
    from leadforge.enrich.ner_worker import resolve_device
    requested = cfg.enrich.ner_device
    device = resolve_device(requested)
    if requested == "auto":
        return f"{device} (auto)"
    return device


def _importable(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def _repo_root() -> Path:
    # src/leadforge/doctor.py -> repo root
    return Path(__file__).resolve().parents[2]


def _write_stamp(cfg: Config) -> None:
    (cfg.data_path / STAMP_NAME).write_text(
        json.dumps({"at": now_iso(), "t": time.time()}), encoding="utf-8"
    )


def ensure_ready(cfg: Config, max_age_h: float = 24.0) -> None:
    """Cheap gate for pipeline commands: trust a recent ok-stamp, else run the local-only doctor.
    It never downloads, installs or opens a socket (C3): a missing piece is reported with its fix."""
    stamp = cfg.data_path / STAMP_NAME
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
        if time.time() - float(data["t"]) < max_age_h * 3600:
            return
    except (OSError, ValueError, KeyError):
        pass
    rep = run_doctor(cfg, network=False)
    if not rep.ok:
        failed = "; ".join(f"{r.name} ({r.hint})" for r in rep.results if not r.ok)
        raise EnvError(f"environment not ready: {failed}")
