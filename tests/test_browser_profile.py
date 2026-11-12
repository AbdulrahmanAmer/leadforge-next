"""L7 (ADOPT risk 15): every browser the product starts takes its profile folder from `prepare_profile`.

No browser is started here, ever: the profile function is called on a temp folder, and the scan only reads source.
"""
import ast
import json
from pathlib import Path

import pytest

from leadforge.browser_profile import LOCAL_STATE, free_slot, local_state_text, prepare_profile, take_slot

SRC = Path(__file__).resolve().parents[1] / "src" / "leadforge"


def test_a_new_profile_folder_holds_the_seeded_file_when_it_is_handed_out(tmp_path):
    now_ms = 1_800_000_000_000
    folder = prepare_profile(tmp_path / "profiles", "tool-0", now_ms=now_ms)
    state = json.loads((folder / LOCAL_STATE).read_text(encoding="utf-8"))
    assert state == {"password_manager": {"os_password_blank": False,
                                          "os_password_last_changed": str((now_ms + 11644473600000) * 1000)}}
    assert [p.name for p in folder.iterdir()] == [LOCAL_STATE]  # no leftover temp file


def test_a_folder_that_exists_is_reused_and_its_file_is_left_alone(tmp_path):
    folder = prepare_profile(tmp_path, "tool-0", now_ms=1_800_000_000_000)
    before = (folder / LOCAL_STATE).read_text(encoding="utf-8")
    (folder / "Default").mkdir()  # the browser has been here
    again = prepare_profile(tmp_path, "tool-0", now_ms=1_900_000_000_000)
    assert again == folder and (folder / LOCAL_STATE).read_text(encoding="utf-8") == before


def test_an_empty_folder_left_by_an_interrupted_start_is_seeded(tmp_path):
    (tmp_path / "tool-0").mkdir()
    assert (prepare_profile(tmp_path, "tool-0") / LOCAL_STATE).is_file()


@pytest.mark.parametrize("name", ["", ".", "..", "../x", "a/b", "a\\b"])
def test_a_name_must_be_one_plain_folder_name(tmp_path, name):
    with pytest.raises(ValueError):
        prepare_profile(tmp_path, name)


def test_slots_are_the_lowest_free_number_and_come_back():
    a, b = take_slot("t-slots"), take_slot("t-slots")
    assert (a, b) == (0, 1)
    free_slot("t-slots", a)
    assert take_slot("t-slots") == 0
    free_slot("t-slots", 0), free_slot("t-slots", b)


def test_the_recipe_text_is_what_the_setup_documents():
    assert json.loads(local_state_text(0))["password_manager"]["os_password_last_changed"] == "11644473600000000"


# ------------------------------------------------------------------------------- the scan: no start bypasses it
_STARTS = {"AsyncWebCrawler", "launch", "launch_persistent_context"}


def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def browser_start_violations(source: str, where: str) -> tuple[list[str], int]:
    """-> (violations, number of browser starts seen) for one module's source.
    A start is a call to AsyncWebCrawler(...), .launch(...) or .launch_persistent_context(...):
    - `.launch(...)` is always a violation (a throw-away profile on every start);
    - `launch_persistent_context` needs a folder: a first argument or user_data_dir=;
    - `AsyncWebCrawler` needs, in the function that holds it, a call with user_data_dir=;
    - a module with any start must call `prepare_profile(` somewhere."""
    tree = ast.parse(source)
    bad: list[str] = []
    starts = 0

    def kw_names(call: ast.Call) -> set[str]:
        return {k.arg for k in call.keywords}

    def top_function(node):
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and node in ast.walk(fn):
                outer = fn
                for fn2 in ast.walk(tree):
                    if isinstance(fn2, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn in ast.walk(fn2):
                        outer = fn2 if len(list(ast.walk(fn2))) > len(list(ast.walk(outer))) else outer
                return outer
        return tree

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) not in _STARTS:
            continue
        starts += 1
        name, line = _call_name(node), f"{where}:{node.lineno}"
        if name == "launch":
            bad.append(f"{line} .launch() starts a browser on a throw-away profile")
        elif name == "launch_persistent_context":
            if not node.args and "user_data_dir" not in kw_names(node):
                bad.append(f"{line} launch_persistent_context() without a profile folder")
        else:
            holder = top_function(node)
            if not any(isinstance(c, ast.Call) and "user_data_dir" in kw_names(c) for c in ast.walk(holder)):
                bad.append(f"{line} AsyncWebCrawler started in a function that never sets user_data_dir")
    if starts and not any(isinstance(c, ast.Call) and _call_name(c) == "prepare_profile" for c in ast.walk(tree)):
        bad.append(f"{where} starts a browser but never calls prepare_profile")
    return bad, starts


def test_every_browser_start_in_the_product_goes_through_the_profile_function():
    seen = {}
    violations = []
    for path in sorted(SRC.rglob("*.py")):
        bad, n = browser_start_violations(path.read_text(encoding="utf-8"), path.relative_to(SRC.parent).as_posix())
        violations += bad
        if n:
            seen[path.name] = n
    # the scan is not empty: it finds the one start the public product has (the crawl4ai render); the Maps provider, its other start,
    # moved to a private add-on in L8 (that add-on imports `prepare_profile` from here)
    assert set(seen) == {"browser.py"}, seen
    assert violations == []


_BAD_THROWAWAY = "def go(pw):\n    return pw.chromium.launch(headless=True)\n"
_BAD_NO_FOLDER = "def go(pw):\n    return pw.chromium.launch_persistent_context()\n"
_BAD_CRAWL4AI = "def go():\n    from crawl4ai import AsyncWebCrawler\n    return AsyncWebCrawler()\n"
_BAD_NO_PREPARE = ("def go(pw):\n    return pw.chromium.launch_persistent_context('/tmp/made-up-folder')\n")
_GOOD = ("from leadforge.browser_profile import prepare_profile\n"
         "def go(pw, root):\n    return pw.chromium.launch_persistent_context(str(prepare_profile(root, 'x')))\n"
         "def render(root):\n    cfg = BrowserConfig(user_data_dir=str(prepare_profile(root, 'y')))\n"
         "    async def run():\n        async with AsyncWebCrawler(config=cfg):\n            pass\n")


@pytest.mark.parametrize("source,needle", [
    (_BAD_THROWAWAY, "throw-away"), (_BAD_NO_FOLDER, "without a profile folder"),
    (_BAD_CRAWL4AI, "never sets user_data_dir"), (_BAD_NO_PREPARE, "never calls prepare_profile"),
])
def test_the_scan_flags_a_planted_start_that_bypasses_the_profile_function(source, needle):
    bad, starts = browser_start_violations(source, "planted.py")
    assert starts >= 1 and any(needle in b for b in bad), bad


def test_the_scan_passes_a_start_that_uses_it():
    bad, starts = browser_start_violations(_GOOD, "good.py")
    assert starts == 2 and bad == []
