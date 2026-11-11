"""C3 (slice L2b): the plugin launcher installs from a hashed lock.

The lock agrees with uv.lock, and bin/leadforge, run for real in a fresh data folder, installs from it with
pip's hash checking: one changed hash and the install fails before anything is stamped. Offline: pip gets
no index (PIP_NO_INDEX) and finds a made-up wheel in a local folder; the plugin root is a made-up project
with an in-tree build backend whose package prints a marker."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / "requirements.lock"


def _lock_entries(text: str) -> dict[str, tuple[str, set[str]]]:
    """name -> (version, hashes) of a pip requirements file in uv export's layout."""
    out: dict[str, tuple[str, set[str]]] = {}
    for block in re.split(r"\n(?=[A-Za-z0-9])", text):
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;\\]+)", block)
        if m:
            out[m.group(1).lower()] = (m.group(2), set(re.findall(r"--hash=(sha256:[0-9a-f]{64})", block)))
    return out


def test_lock_agrees_with_uv_lock():
    entries = _lock_entries(LOCK.read_text(encoding="utf-8"))
    uv = {p["name"]: p for p in tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))["package"]}
    assert entries, "requirements.lock has no pinned packages"
    for name, (version, hashes) in entries.items():
        pkg = uv.get(name)
        assert pkg is not None, f"{name} is in requirements.lock but not in uv.lock"
        assert version == pkg["version"], f"{name}: lock {version}, uv.lock {pkg['version']}"
        known = {w["hash"] for w in pkg.get("wheels", [])} | ({pkg["sdist"]["hash"]} if "sdist" in pkg else set())
        assert hashes and hashes <= known, f"{name}: hashes missing or not from uv.lock"
    deps = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    for dep in deps:
        name = re.match(r"[A-Za-z0-9_.\-]+", dep).group(0).lower().replace("_", "-")
        assert name in entries, f"runtime dependency {name} is missing from requirements.lock"
    build = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["build-system"]["requires"]
    for req in build:
        assert re.match(r"[A-Za-z0-9_.\-]+", req).group(0).lower() in entries, f"build backend {req} not locked"


def test_launcher_installs_from_the_lock_with_hashes():
    text = (REPO / "bin" / "leadforge").read_text(encoding="utf-8")
    assert '--require-hashes' in text and '-r "${plugin_root}/requirements.lock"' in text
    assert "--upgrade pip" not in text
    assert '--no-deps --no-build-isolation' in text


# ------------------------------------------------------------------ the launcher, run for real
BACKEND = r'''
import base64, hashlib, zipfile
from pathlib import Path

def make_wheel(dest, dist, version, files):
    info = f"{dist}-{version}.dist-info"
    files = dict(files)
    files[f"{info}/METADATA"] = f"Metadata-Version: 2.1\nName: {dist}\nVersion: {version}\n"
    files[f"{info}/WHEEL"] = "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    record = []
    for path, body in files.items():
        data = body.encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record.append(f"{path},sha256={digest},{len(data)}")
    files[f"{info}/RECORD"] = "\n".join(record + [f"{info}/RECORD,,"]) + "\n"
    name = f"{dist}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(Path(dest) / name, "w") as zf:
        for path, body in files.items():
            zf.writestr(path, body)
    return name

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return make_wheel(wheel_directory, "lf_probe", "1.0", {
        "leadforge/__init__.py": "",
        "leadforge/__main__.py": "print('probe-launched')\n",
    })
'''


def _posix_sh() -> str | None:
    if os.name != "nt":
        return shutil.which("sh")
    git = shutil.which("git")  # Git for Windows' own sh, never WSL's bash
    if git:
        root = Path(git).resolve().parents[1]
        for cand in (root / "usr" / "bin" / "sh.exe", root / "bin" / "sh.exe"):
            if cand.is_file():
                return str(cand)
    return None


# resolved at import: conftest stubs shutil.which inside every test
POSIX_SH = _posix_sh()


def _setup(tmp_path: Path, lock_hash: str | None = None) -> tuple[list[str], dict, Path]:
    ns: dict = {}
    exec(BACKEND, ns)  # noqa: S102 — the made-up backend, also used to make the locked wheel
    wheels = tmp_path / "wheels"
    wheels.mkdir(parents=True)
    whl = ns["make_wheel"](wheels, "lfdummy", "1.0", {"lfdummy/__init__.py": "OK = True\n"})
    real_hash = hashlib.sha256((wheels / whl).read_bytes()).hexdigest()

    plugin = tmp_path / "plugin"
    (plugin / "bin").mkdir(parents=True)
    (plugin / ".claude-plugin").mkdir()
    shutil.copy(REPO / "bin" / "leadforge", plugin / "bin" / "leadforge")
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "0.0.0-test"}), encoding="utf-8")
    (plugin / "requirements.lock").write_text(
        f"lfdummy==1.0 \\\n    --hash=sha256:{lock_hash or real_hash}\n", encoding="utf-8")
    (plugin / "pyproject.toml").write_text(
        '[build-system]\nrequires = []\nbuild-backend = "probe_backend"\nbackend-path = ["_build"]\n',
        encoding="utf-8")
    (plugin / "_build").mkdir()
    (plugin / "_build" / "probe_backend.py").write_text(BACKEND, encoding="utf-8")

    shim = tmp_path / "shim"
    shim.mkdir()
    exe = Path(sys.executable).as_posix()
    for name in ("python3", "python"):  # this laptop's python3 alias hangs; point both at this interpreter
        (shim / name).write_text(f'#!/bin/sh\nexec "{exe}" "$@"\n', encoding="utf-8", newline="\n")
        (shim / name).chmod(0o755)

    data = tmp_path / "data"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "VIRTUAL_ENV", "UV_"))}
    env.update(CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PLUGIN_DATA=str(data), PIP_NO_INDEX="1",
               PIP_FIND_LINKS=str(wheels), PIP_NO_CACHE_DIR="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               PATH=os.pathsep.join([str(shim), str(Path(POSIX_SH or "").parent), env.get("PATH", "")]))
    return [POSIX_SH, str(plugin / "bin" / "leadforge")], env, data


def _venv_python(data: Path) -> Path:
    for p in (data / "venv" / "bin" / "python", data / "venv" / "Scripts" / "python.exe"):
        if p.exists():
            return p
    raise AssertionError("launcher made no venv")


@pytest.mark.timeout(600)
@pytest.mark.skipif(POSIX_SH is None, reason="no POSIX sh (Git for Windows' sh on Windows)")
def test_launcher_install_refuses_a_changed_hash(tmp_path):
    good_cmd, good_env, good_data = _setup(tmp_path / "good")
    res = subprocess.run(good_cmd, env=good_env, capture_output=True, encoding="utf-8", errors="replace",
                         timeout=540)
    assert res.returncode == 0, res.stderr[-2000:]
    assert "probe-launched" in res.stdout
    assert (good_data / ".installed-version").read_text(encoding="utf-8") == "0.0.0-test"
    probe = subprocess.run([str(_venv_python(good_data)), "-c", "import lfdummy; print(lfdummy.OK)"],
                           capture_output=True, encoding="utf-8", timeout=60)
    assert probe.stdout.strip() == "True", "the locked package was not installed from the lock"

    bad_cmd, bad_env, bad_data = _setup(tmp_path / "bad", lock_hash="0" * 64)
    res = subprocess.run(bad_cmd, env=bad_env, capture_output=True, encoding="utf-8", errors="replace",
                         timeout=540)
    assert res.returncode != 0, "an install with a changed lock hash must fail"
    assert "DO NOT MATCH THE HASHES" in res.stderr.upper(), res.stderr[-2000:]
    assert "probe-launched" not in res.stdout
    assert not (bad_data / ".installed-version").exists()
