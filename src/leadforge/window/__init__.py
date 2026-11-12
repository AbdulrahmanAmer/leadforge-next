"""`leadforge window <name>`: the engine's side of the window's seam (slice L11a, docs/slices/L11a-window-commands.md).

One JSON document in on stdin (the arguments object), one JSON document out on stdout (the result), exit 0. On an error a
non-zero exit and `{"kind", "message", "details", "next"}` on stdout. Nothing else reaches stdout: while a command runs,
`sys.stdout` points at stderr, and logs go to stderr and the workspace log file. Arguments never travel in argv. `run_start`
alone writes JSON lines (the run handle, then one RunEvent per line). The types are `app/ui/src/engine.ts` of the window.
There is no send or outreach command here (C14).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from typing import Any, TextIO

from leadforge.util import EnvError, InputError, LeadForgeError, ProviderFailed

NAMES = (
    "campaign_create", "run_start", "run_stop", "run_status", "campaigns_list", "sheet_export", "sheet_open", "people_list",
    "person_forget", "address_suppress", "purge_report", "purge_apply", "purge_everything", "retention_get", "retention_set",
    "keys_list", "key_save", "key_remove", "settings_get", "settings_set", "about",
)

# engine.ts ErrorKind, exactly these seven: the screens show any other kind as a generic failure
KINDS = ("failed", "usage", "environment", "input", "source", "keyring", "missing")
# ErrorKind -> exit code: util.py's exit codes; `keyring` and `missing` exit 1, as the window's stand-in engine does
EXIT_CODES = {"failed": 1, "usage": 2, "environment": 3, "input": 4, "source": 5, "keyring": 1, "missing": 1}
# the window core's limit on the arguments document (app/src-tauri/src/engine.rs, MAX_INPUT_BYTES)
MAX_ARGS_BYTES = 1024 * 1024
KEY_COMMANDS = ("keys_list", "key_save", "key_remove")


class WindowError(Exception):
    def __init__(self, kind: str, message: str, details: list[str] | None = None, next_: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.details = details or []
        self.next = next_

    def document(self) -> dict:
        return {"kind": self.kind, "message": self.message, "details": self.details, "next": self.next}

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.kind]


def usage(message: str, *details: str, next_: str | None = None) -> WindowError:
    return WindowError("usage", message, list(details), next_)


def from_engine(e: LeadForgeError, message: str) -> WindowError:
    """An engine error in the window's terms: the kind follows the exit code, the engine's own words are the details."""
    kind = ("input" if isinstance(e, InputError) else "environment" if isinstance(e, EnvError)
            else "source" if isinstance(e, ProviderFailed) else {2: "usage"}.get(e.exit_code, "failed"))
    return WindowError(kind, message, [ln.strip(" -") for ln in str(e).splitlines() if ln.strip(" -")][:8])


# ------------------------------------------------------------------ arguments
def read_arguments(stdin: TextIO) -> dict:
    text = stdin.read()
    size = len(text.encode("utf-8", "surrogatepass"))
    if size > MAX_ARGS_BYTES:
        raise WindowError("input", "The arguments are larger than 1 MiB.", [f"stdin holds {size} bytes"], None)
    try:
        args = json.loads(text)
    except ValueError as e:
        raise usage("The arguments are not one JSON document.", f"stdin: {type(e).__name__} at character {getattr(e, 'pos', '?')}",
                    next_='Send the arguments as one JSON object on stdin, {} when there are none.') from None
    if not isinstance(args, dict):
        raise usage("The arguments must be one JSON object.", f"stdin holds a JSON {type(args).__name__}")
    return args


def only(args: dict, *allowed: str) -> None:
    extra = sorted(set(args) - set(allowed))
    if extra:
        raise usage("Unknown arguments.", *(f"not an argument of this command: {k}" for k in extra))


def text_arg(args: dict, key: str, *, required: bool = True, allow_null: bool = False) -> str | None:
    if key not in args:
        if required:
            raise usage(f"The argument {key} is missing.")
        return None
    v = args[key]
    if v is None and allow_null:
        return None
    if not isinstance(v, str):
        raise usage(f"The argument {key} must be text.")
    return v


def int_arg(args: dict, key: str) -> int:
    v = args.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise usage(f"The argument {key} must be a whole number.")
    return v


def object_arg(args: dict, key: str) -> dict:
    v = args.get(key)
    if not isinstance(v, dict):
        raise usage(f"The argument {key} must be a JSON object.")
    return v


# ------------------------------------------------------------------ the entry point
def write_json(stdout: TextIO, doc: Any) -> None:
    stdout.write(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def _logs_to_stderr() -> None:
    """Library logs on stderr (warnings and up); the engine's own file log stays as the command line has it."""
    root = logging.getLogger()
    if not any(getattr(h, "_leadforge_window", False) for h in root.handlers):
        h = logging.StreamHandler(sys.stderr)
        h.setLevel(logging.WARNING)
        h._leadforge_window = True  # type: ignore[attr-defined]
        root.addHandler(h)


def main(argv: list[str], stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
    out = stdout or sys.stdout
    inp = stdin or sys.stdin
    name = argv[0] if argv else ""
    with contextlib.redirect_stdout(sys.stderr):   # whatever the engine prints goes to stderr; `out` is the seam
        try:
            if not argv:
                raise usage("No command name.", next_="leadforge window <name>, the arguments as JSON on stdin")
            if len(argv) > 1:
                raise usage("Arguments never travel in argv.", f"refused {len(argv) - 1} argument(s) after the command name",
                            next_="Send the arguments as one JSON object on stdin.")
            if name not in NAMES:
                raise usage("Unknown command.", f"not a window command: {name[:40]}")
            _logs_to_stderr()
            args = read_arguments(inp)
            from leadforge.window import commands, run

            if name == "run_start":
                return run.start(args, out)
            result = (run.COMMANDS.get(name) or commands.COMMANDS[name])(args)
        except WindowError as e:
            write_json(out, e.document())
            return e.exit_code
        except LeadForgeError as e:
            err = from_engine(e, "The engine stopped.")
            write_json(out, err.document())
            return err.exit_code
        except Exception as e:  # noqa: BLE001 — the seam answers with its error document, never a stack trace on stdout
            # a key command never shows or logs the exception's text: a backend may quote what it was given
            if name in KEY_COMMANDS:
                logging.getLogger("leadforge").error("window %s failed: %s", name, type(e).__name__)
                detail = type(e).__name__
            else:
                logging.getLogger("leadforge").exception("window %s failed", name)
                detail = f"{type(e).__name__}: {str(e)[:200]}"
            write_json(out, {"kind": "failed", "message": "The engine stopped unexpectedly.", "details": [detail], "next": None})
            return 1
    write_json(out, result)
    return 0
