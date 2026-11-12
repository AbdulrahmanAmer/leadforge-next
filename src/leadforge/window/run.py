"""The window's run group: run_start (a stream of JSON lines), run_stop (the cooperative stop), run_status.

run_start drives the engine's own `pipeline.run_pipeline`, the same path `run --detach` takes (a run made first, then
continued), in this process. The engine's progress reaches the stream through `util.set_progress_listener`; whatever the
engine prints goes to stderr. run_stop writes a flag file; `util.emit_progress` and the pipeline's stage boundaries check
it and raise `util.RunStopped`, so the run stops between two businesses with its stage unchanged, and `run --resume`
(or run_start with `resume: true`) continues it.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import TextIO

from leadforge import db, util
from leadforge.config import Config
from leadforge.util import LeadForgeError, RunStopped
from leadforge.window import WindowError, from_engine, object_arg, only, text_arg, usage, write_json
from leadforge.window.commands import campaign_dir, db_file, load_cfg, reading

WINDOW_STAGES = ("discover", "enrich", "label", "score", "draft", "export")
# the engine's run stages (pipeline.STAGES) and progress stages, in the window's six
STAGE_OF = {"planned": "discover", "discovering": "discover", "discovered": "discover", "enriching": "enrich",
            "enriched": "enrich", "dm_pending": "label", "labeling": "label", "scoring": "score", "scored": "score",
            "drafting": "draft", "exported": "export",
            "discover": "discover", "registry": "enrich", "enrich": "enrich", "infer": "enrich", "validate": "enrich",
            "gbp": "enrich", "resolve": "enrich", "label": "label", "score": "score", "draft": "draft", "export": "export"}


def window_stage(stage: str | None) -> str:
    return STAGE_OF.get(stage or "", "discover")


def stop_file(cfg: Config) -> Path:
    return Path(cfg.workspace) / cfg.data_dir / "window-run.stop"


def state_of(row, stats: dict) -> tuple[str, str | None]:
    """(state, reason) of a run, from what the engine and run_start recorded."""
    pid = stats.get("window_pid") or stats.get("pid")
    if pid is not None and util.pid_alive(pid):
        return "running", None
    if row["stage"] == "exported":
        return "finished", None
    recorded = stats.get("window_state")
    if recorded in ("stopped", "failed"):
        return recorded, stats.get("window_reason")
    if recorded == "running":
        return "failed", "The engine process ended before the run did."
    return "stopped", None   # not running and not finished: it can be continued


def status_doc(cfg: Config, conn, row, *, state: str | None = None, reason: str | None = None) -> dict:
    stats = json.loads(row["stats_json"] or "{}")
    if state is None:
        state, reason = state_of(row, stats)
    stage = window_stage(row["stage"])
    done = total = eta = None
    if state == "running":
        from leadforge.cli import _status_progress

        feed = _status_progress(cfg)
        if feed and window_stage(feed.get("progress_stage")) == stage:
            done, total, eta = feed.get("progress_done"), feed.get("progress_total"), feed.get("eta_seconds")
    elif stats.get("window_progress_stage") == stage:   # where run_start's last progress line left the run's stage
        done, total = stats.get("window_done"), stats.get("window_total")
    rid = row["id"]
    one = lambda sql: conn.execute(sql, (rid,)).fetchone()[0]  # noqa: E731
    return {
        "runId": rid, "campaign": _campaign_name(row), "state": state, "stage": stage,
        "done": done, "total": total, "etaSeconds": eta,
        "counts": {"businesses": one("SELECT COUNT(*) FROM businesses WHERE first_run_id=?"),
                   "contacts": one("SELECT COUNT(*) FROM contacts c JOIN businesses b ON b.id=c.business_id WHERE b.first_run_id=?"),
                   "purged": stats.get("purged"), "expiringIn30Days": stats.get("expiring_30d")},
        "startedAt": row["started_at"], "reason": reason,
    }


def _campaign_name(row) -> str | None:
    from leadforge.window.commands import _icp_of

    icp = _icp_of(row["icp_path"])
    return icp.campaign if icp else None


def _find(conn, run_id: str | None):
    if run_id is None:
        return db.latest_run(conn)
    return conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()


# ------------------------------------------------------------------ run_status, run_stop
def run_status(args: dict) -> dict | None:
    only(args, "runId")
    run_id = text_arg(args, "runId", required=False, allow_null=True)
    cfg = load_cfg()
    with reading(cfg) as conn:
        if conn is None:
            return None
        row = _find(conn, run_id)
        if row is None and run_id is not None:
            raise WindowError("input", "There is no run with that id in this workspace.", [], None)
        return None if row is None else status_doc(cfg, conn, row)


def run_stop(args: dict) -> dict:
    only(args, "runId")
    run_id = text_arg(args, "runId")
    cfg = load_cfg()
    with reading(cfg) as conn:
        row = None if conn is None else _find(conn, run_id)
        stats = json.loads(row["stats_json"] or "{}") if row else {}
        if row is None or stats.get("window_state") != "running" or state_of(row, stats)[0] != "running":
            raise WindowError("input", "There is no run to stop.", ["No run started by the window is running for this workspace."], None)
        flag = stop_file(cfg)
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(run_id, encoding="utf-8")
        return status_doc(cfg, conn, row)


COMMANDS = {"run_stop": run_stop, "run_status": run_status}


# ------------------------------------------------------------------ run_start
def _at(ts: float | None = None) -> str:
    from datetime import UTC, datetime

    return (datetime.fromtimestamp(ts, UTC) if ts else util.utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


# the window core relays no run_start line longer than 64 KiB (app/src-tauri/src/engine.rs, MAX_LINE_BYTES)
MAX_LINE_BYTES = 64 * 1024
CUT_MARK = " [cut]"


def _bounded(v, cut: int):
    """`v` with every text longer than `cut` characters cut there and marked, and lists kept to their first 20 items."""
    if isinstance(v, str):
        return v if len(v) <= cut else v[:cut] + CUT_MARK
    if isinstance(v, dict):
        return {k: _bounded(x, cut) for k, x in v.items()}
    if isinstance(v, list):
        return [_bounded(x, cut) for x in v[:20]]
    return v


def write_line(out: TextIO, event: dict) -> None:
    """One run_start line, never over MAX_LINE_BYTES: long texts are cut (4,000 characters, then 200 if still too long)."""
    for cut in (4000, 200):
        event = _bounded(event, cut)
        if len(json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "surrogatepass")) < MAX_LINE_BYTES:
            break
    write_json(out, event)


class _Stream:
    """The run's JSON lines. The engine calls `progress` from its driver threads too, hence the lock."""

    def __init__(self, out: TextIO):
        self.out = out
        self.lock = threading.Lock()
        self.stage: str | None = None
        self.last: dict | None = None

    def send(self, event: dict) -> None:
        with self.lock:
            write_line(self.out, event)


    def progress(self, payload: dict) -> None:
        stage = window_stage(payload.get("stage"))
        with self.lock:
            if self.stage is not None and WINDOW_STAGES.index(stage) > WINDOW_STAGES.index(self.stage):
                self._close_stages_before_locked(stage)
            if self.stage is None or WINDOW_STAGES.index(stage) >= WINDOW_STAGES.index(self.stage):
                self.stage = stage
            event = {"type": "progress", "stage": stage, "done": payload.get("done", 0), "total": payload.get("total"),
                     "message": payload.get("msg", ""), "etaSeconds": None, "at": _at(payload.get("ts"))}
            self.last = event
            write_line(self.out, event)

    def _close_stages_before_locked(self, stage: str) -> None:
        """A `stage-done` for the current stage and every stage passed over on the way to `stage` (the lock is held)."""
        for s in WINDOW_STAGES[WINDOW_STAGES.index(self.stage):WINDOW_STAGES.index(stage)]:
            last = self.last if self.last and self.last["stage"] == s else None
            summary = (f"{last['done']} of {last['total']}" if last and last["total"] is not None
                       else f"{last['done']}" if last else "done")
            write_line(self.out, {"type": "stage-done", "stage": s, "summary": summary, "at": _at()})

    def finish(self) -> None:
        with self.lock:
            if self.stage is not None:
                end = WINDOW_STAGES[-1]
                self._close_stages_before_locked(end)
                self.stage = end
                write_line(self.out, {"type": "stage-done", "stage": end, "summary": "done", "at": _at()})


def _start_of_run_purge(cfg: Config) -> dict:
    """The engine's retention pass at the start of every run (C5), as `run` makes it (cli._start_of_run_purge), with the
    window's error document instead of a digest line."""
    from leadforge import retention

    try:
        res = retention.purge(cfg, util.utcnow(), "auto")
    except LeadForgeError as e:
        raise from_engine(e, "The run did not start: nothing was changed.") from None
    if res["state"] == "stopped_over_half":
        raise WindowError("input", "The run did not start: nothing was deleted.",
                          [f"{res['expired']} of {res['total']} businesses and {res['files_expired']} of {res['files_total']} files in "
                           f"exports and cache are past the {res['months']}-month limit: more than half of the workspace, so nothing "
                           "was deleted and the run stopped (a wrong clock looks like this)"],
                          "Check the date on this computer; then delete them from Data (purge), or look at the report first.")
    if res["state"] == "no_workspace":
        return {}
    return {"purged": res["deleted"], "expiring_30d": res["expiring_30d"], "armed_now": res["state"] == "armed", "expired": res["expired"]}


def start(args: dict, out: TextIO) -> int:
    from leadforge import pipeline
    from leadforge.intake import load_icp

    only(args, "args")
    run_args = object_arg(args, "args")
    only(run_args, "campaign", "resume")
    campaign = text_arg(run_args, "campaign")
    resume = run_args.get("resume")
    if not isinstance(resume, bool):
        raise usage("The argument resume must be true or false.")
    icp_path = campaign_dir(campaign) / "icp.yaml"
    cfg = load_cfg()
    if not icp_path.is_file():
        raise WindowError("input", "There is no campaign of that name in this workspace.", [], "Create the campaign first.")
    try:
        icp = load_icp(icp_path)
    except LeadForgeError as e:
        raise from_engine(e, "The campaign file cannot be read.") from None

    os.environ["LEADFORGE_NO_UI"] = "1"   # no console window, no sheet opened by the engine: the window does both
    # Until a run exists a refusal is the seam's error document alone (there is no run id to hand over). From the handle on,
    # every way out below ends the stream with `finished`, `stopped` or `failed`.
    if resume:
        if not db_file(cfg).is_file():
            raise WindowError("input", "There is no run of this campaign to continue.", [], "Start the run instead.")
        conn = db.connect(cfg.db_path)
        row = db.latest_run(conn, icp.icp_hash())
        if row is None:
            raise WindowError("input", "There is no run of this campaign to continue.", [], "Start the run instead.")
        purge_counts = _start_of_run_purge(cfg)
        run_id = row["id"]
    else:
        purge_counts = _start_of_run_purge(cfg)
        conn = db.connect(cfg.db_path)
        run_id = db.create_run(conn, str(icp_path), icp.icp_hash())

    stream = _Stream(out)
    stream.send({"runId": run_id})   # the RunHandle first (see "Seam changes proposed" 1), then the events
    flag = stop_file(cfg)
    first_status: dict | None = None
    end: dict
    code = 0
    try:
        if not resume:
            pipeline._plan_into_db(conn, cfg, icp, run_id)
        armed_now, expired = purge_counts.pop("armed_now", False), purge_counts.pop("expired", 0)
        db.set_run_meta(conn, run_id, window_pid=os.getpid(), window_state="running", window_reason=None, **purge_counts)
        flag.unlink(missing_ok=True)
        first_status = status_doc(cfg, conn, conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone(), state="running")
        if purge_counts:   # the engine's own retention lines (cli._start_of_run_purge), as one notice
            first = (f"Clean-up before the run: this is the first check of this workspace, so nothing was deleted; {expired} records "
                     f"are past the {cfg.retention.months}-month limit and the next run deletes them." if armed_now else
                     f"Clean-up before the run: {purge_counts['purged']} businesses past the {cfg.retention.months}-month limit "
                     "were deleted.")
            stream.send({"type": "notice", "at": _at(), "text": f"{first} {purge_counts['expiring_30d']} more expire in the next 30 days."})
        util.set_stop_file(flag)
        util.set_progress_listener(stream.progress)
        result = pipeline.run_pipeline(cfg, icp, icp_path, resume=True)
    except RunStopped:
        end = {"type": "stopped", "state": "stopped", "reason": None}
    except LeadForgeError as e:
        err = from_engine(e, str(e).splitlines()[0][:200] if str(e) else "The run failed.")
        end = {"type": "failed", "state": "failed", "reason": err.message,
               "error": {"kind": err.kind, "message": err.message, "details": err.details}}
        code = err.exit_code
    except Exception as e:  # noqa: BLE001 — the stream ends with its `failed` event, never a stack trace on stdout
        util.LOG.exception("window run %s failed", run_id)
        reason = f"{type(e).__name__}: {str(e)[:200]}"
        end = {"type": "failed", "state": "failed", "reason": reason, "error": {"kind": "failed", "message": reason, "details": []}}
        code = 1
    except BaseException as e:  # an interrupt or an exit inside the engine: the stream still ends
        reason = f"The run was interrupted ({type(e).__name__})."
        end = {"type": "failed", "state": "failed", "reason": reason, "error": {"kind": "failed", "message": reason, "details": []}}
        code = 1
    else:
        if result["stage"] == "exported":
            stream.finish()
            end = {"type": "finished", "state": "finished", "reason": None}
        else:   # paused for decision-maker labels (autopilot off): stopped, and the engine says what comes next
            if result.get("next"):
                stream.send({"type": "notice", "text": f"The run is waiting: {result['next']}", "at": _at()})
            end = {"type": "stopped", "state": "stopped", "reason": None}
    finally:
        util.set_progress_listener(None)
        util.set_stop_file(None)
        with contextlib.suppress(OSError):
            flag.unlink(missing_ok=True)
    try:
        conn = db.connect(cfg.db_path)
        last = stream.last
        place = {"window_progress_stage": last["stage"] if last else None, "window_done": last["done"] if last else None,
                 "window_total": last["total"] if last else None}
        db.set_run_meta(conn, run_id, window_state=end["state"], window_reason=end["reason"], window_pid=None, **place)
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        status = status_doc(cfg, conn, row, state=end["state"], reason=end["reason"])
    except Exception:  # noqa: BLE001 — the end event is still written, from the status read when the run began
        util.LOG.exception("window run %s: the end of the run could not be recorded", run_id)
        status = {**(first_status or {"runId": run_id, "campaign": icp.campaign, "stage": "discover", "startedAt": None,
                                      "counts": {"businesses": None, "contacts": None, "purged": None, "expiringIn30Days": None}}),
                  "state": end["state"], "reason": end["reason"], "done": None, "total": None, "etaSeconds": None}
    event = {"type": end["type"], "status": status}
    if "error" in end:
        event["error"] = end["error"]
    stream.send(event)
    return code
