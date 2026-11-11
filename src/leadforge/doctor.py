"""Environment doctor & self-bootstrap (U0.5).

Checks the machine BEFORE any pipeline work and (with --fix) installs what is missing:
- Python >= 3.11, core imports, writable data dirs, disk space
- pinned gosom google-maps-scraper binary (auto-download per-OS release asset -> leadforge_data/bin/)
- network + DNS reachability
- optional extras present (reported, never required)

A 24h ok-stamp keeps repeat checks cheap; pipeline commands call ensure_ready().
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from leadforge import GOSOM_VERSION
from leadforge.config import Config
from leadforge.util import LOG, EnvError, now_iso

GOSOM_REPO = "gosom/google-maps-scraper"
STAMP_NAME = ".doctor_ok.json"
CORE_IMPORTS = [
    "typer", "pydantic", "yaml", "httpx", "selectolax", "trafilatura",
    "phonenumbers", "email_validator", "dns", "pyap", "tenacity", "openpyxl",
]
OPTIONAL_EXTRAS = {"crawl4ai": "browser", "gliner": "ner", "usaddress": "addressing", "yt_dlp": "social"}
# extras --fix --full installs, with the concrete packages to fall back on when there is no
# source checkout to `pip install -e .[extra]` from (non-editable installs live in site-packages)
QUALITY_EXTRAS: list[tuple[str, str, str | None, list[str]]] = [
    ("ner", "gliner", None, ["gliner"]),
    ("browser", "crawl4ai", "crawl4ai-setup", ["crawl4ai"]),
    ("social", "yt_dlp", None, ["yt-dlp"]),
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


# ------------------------------------------------------------------ gosom binary management
# SHA-256 of every release asset of the pinned version (C3). A file whose hash differs is refused and
# deleted, never run. Source: GitHub's asset digests for v1.17.4 (published 2026-08-22); the Windows
# asset was also downloaded once and hashed by hand (slice L2b). Bump with GOSOM_VERSION, never alone.
GOSOM_SHA256 = {
    f"google_maps_scraper-{GOSOM_VERSION}-darwin-amd64":
        "d6de77ef36e2a6ad2ee54294df9c2b235429f7c523c70f13649f35eaac6f1f25",
    f"google_maps_scraper-{GOSOM_VERSION}-linux-amd64":
        "afff7a583a669def1453c461f0fedd078a25732c536b034426d8b7b617d00ac0",
    f"google_maps_scraper-{GOSOM_VERSION}-windows-amd64.exe":
        "a1538350bd91a8150776b344b801de24e192fdf6b4ebb1254963d069117ffb48",
}


def gosom_asset_name() -> str:
    osname = {"Windows": "windows", "Darwin": "darwin", "Linux": "linux"}.get(platform.system(), "linux")
    # the pinned release ships amd64 assets only; arm64 machines run them under emulation/rosetta
    ext = ".exe" if osname == "windows" else ""
    return f"google_maps_scraper-{GOSOM_VERSION}-{osname}-amd64{ext}"


def gosom_path(cfg: Config) -> Path:
    return cfg.bin_dir / gosom_asset_name()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gosom_verified(path: Path) -> bool:
    """True when `path` holds the pinned asset byte for byte. A present file with any other hash is
    deleted here, so it can never be run."""
    if not path.is_file():
        return False
    want = GOSOM_SHA256.get(path.name)
    if want is not None and _sha256(path) == want:
        return True
    LOG.warning("gosom binary %s does not match its pinned SHA-256; refused and deleted", path.name)
    path.unlink(missing_ok=True)
    return False


def download_gosom(cfg: Config) -> Path:
    """Download the pinned release asset from its release URL and keep it only if its SHA-256 matches."""
    dest = gosom_path(cfg)
    if gosom_verified(dest):
        return dest
    asset = gosom_asset_name()
    want = GOSOM_SHA256.get(asset)
    if want is None:
        raise EnvError(f"no pinned SHA-256 for {asset}; this platform has no checked gosom binary")
    url = f"https://github.com/{GOSOM_REPO}/releases/download/v{GOSOM_VERSION}/{asset}"
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        LOG.info("downloading gosom binary: %s", url)
        with httpx.Client(follow_redirects=True, timeout=60) as client, client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_bytes(1 << 16):
                    fh.write(chunk)
    except httpx.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise EnvError(f"binary download failed: {asset} ({e}). Manually place it at {dest} from "
                       f"https://github.com/{GOSOM_REPO}/releases/tag/v{GOSOM_VERSION}") from e
    got = _sha256(tmp)
    if got != want:
        tmp.unlink(missing_ok=True)
        raise EnvError(f"downloaded {asset} has SHA-256 {got}, pinned {want}: refused and deleted")
    tmp.replace(dest)
    if platform.system() != "Windows":
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return dest


def gosom_runs(path: Path) -> bool:
    if not gosom_verified(path):
        return False
    try:
        proc = subprocess.run([str(path), "-h"], capture_output=True, timeout=20, encoding="utf-8", errors="replace")
        return proc.returncode in (0, 2)  # go flag package exits 2 on -h
    except (OSError, subprocess.TimeoutExpired):
        return False


# ------------------------------------------------------------------ checks
def install_quality_extras(rep_add) -> None:
    """--fix --full: install the enrichment-quality extras ([ner] GLiNER, [browser] crawl4ai,
    [social] yt-dlp) so a fresh machine's first bootstrap yields full-quality sheets, not the
    heuristic floor."""
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

    bin_path = gosom_path(cfg)
    fixed = False
    present = bin_path.exists()
    if not gosom_runs(bin_path):
        refused = present and not bin_path.exists()
        if fix:
            try:
                download_gosom(cfg)
                fixed = gosom_runs(bin_path)
            except EnvError as e:
                add(CheckResult("gosom-binary", False, msg=str(e),
                                hint="download the asset manually into leadforge_data/bin/"))
            else:
                add(CheckResult("gosom-binary", fixed, fixed=fixed, msg=f"v{GOSOM_VERSION} -> {bin_path.name}",
                                hint="manual download; see message"))
        else:
            msg = (f"{bin_path.name} did not match its pinned SHA-256: refused and deleted" if refused
                   else f"missing: {bin_path.name}")
            add(CheckResult("gosom-binary", False, msg=msg, hint="leadforge doctor --fix"))
    else:
        add(CheckResult("gosom-binary", True, msg=f"v{GOSOM_VERSION} present"))

    if network:
        _network_checks(cfg, add)

    extras = [f"{tag}({mod})" for mod, tag in OPTIONAL_EXTRAS.items() if _importable(mod)]
    add(CheckResult("optional-extras", True, msg=", ".join(extras) if extras else
                    "none installed (fine) — [browser]/[ner]/[social]/[addressing] available"))

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
        add(CheckResult("network", False, msg=type(e).__name__, hint="check connectivity/proxy"))

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
        json.dumps({"at": now_iso(), "t": time.time(), "gosom": GOSOM_VERSION}), encoding="utf-8"
    )


def ensure_ready(cfg: Config, max_age_h: float = 24.0) -> None:
    """Cheap gate for pipeline commands: trust a recent ok-stamp, else run the local-only doctor.
    It never downloads, installs or opens a socket (C3): a missing piece is reported with its fix."""
    stamp = cfg.data_path / STAMP_NAME
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
        if time.time() - float(data["t"]) < max_age_h * 3600 and data.get("gosom") == GOSOM_VERSION:
            return
    except (OSError, ValueError, KeyError):
        pass
    rep = run_doctor(cfg, network=False)
    if not rep.ok:
        failed = "; ".join(f"{r.name} ({r.hint})" for r in rep.results if not r.ok)
        raise EnvError(f"environment not ready: {failed}")
