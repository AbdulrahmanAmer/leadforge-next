/**
 * The Run screen's state: what the run looks like after each answer, engine event and shell message.
 * Pure (no React, no Tauri), so tests/run-view.test.mjs runs it in Node. Only erasable TypeScript.
 */
import { EngineError, STAGES } from "./engine.ts";
import type { RunMessage, RunStatus, StageId, StreamClosed } from "./engine.ts";

/** `done: null` is a stage whose progress the engine could not say (an end status with `done` null). */
export interface StageView { done: number | null; total: number | null; summary: string | null; message: string }

export interface RunView {
  /** `stopping`: `run_stop` answered and the engine is finishing the business it is on, until its end event or
   *  the shell's `stream-closed`. */
  phase: "idle" | "starting" | "running" | "stopping" | "finished" | "stopped" | "failed";
  campaign: string | null;
  runId: string | null;
  current: StageId | null;
  stages: Record<StageId, StageView>;
  etaSeconds: number | null;
  notices: string[];
  status: RunStatus | null;
  /** Why the run did not start, or why it failed. */
  error: unknown;
  /** The stop request is on its way (the button is busy); after it answers the phase is `stopping`. */
  stopping: boolean;
  /** The shell said the stream closed without an end event: the screen asks `runStatus` once. */
  closed: StreamClosed | null;
}

/** What the screen says when the stream closed with no end event and the engine's status does not say more. */
export const ENGINE_SILENT = "The engine stopped without saying why.";
export const ENGINE_SILENT_NEXT = "What was found so far is kept. Continue the run to pick it up where it stopped.";

export function freshStages(): Record<StageId, StageView> {
  const out = {} as Record<StageId, StageView>;
  for (const s of STAGES) out[s] = { done: 0, total: null, summary: null, message: "" };
  return out;
}

export const IDLE: RunView = { phase: "idle", campaign: null, runId: null, current: null, stages: freshStages(), etaSeconds: null, notices: [], status: null, error: null, stopping: false, closed: null };

export type RunAction =
  | { type: "starting"; campaign: string }
  | { type: "started"; runId: string }
  | { type: "refused"; error: unknown }
  | { type: "event"; event: RunMessage }
  | { type: "stopping" }
  | { type: "stopped"; status: RunStatus }
  | { type: "stop-refused"; error: unknown }
  /** The one `runStatus` asked after `stream-closed`: its answer, or null when it failed. */
  | { type: "status-after-close"; status: RunStatus | null };

const ENDED: readonly RunView["phase"][] = ["finished", "stopped", "failed"];

/** The run is still going (its Run screen shows it live; the rail shows the dot). */
export function isLive(phase: RunView["phase"]): boolean {
  return phase === "starting" || phase === "running" || phase === "stopping";
}

/** An end status says where the run stopped: its stage keeps the status's `done`, which may be null (not known). */
function withStatus(view: RunView, status: RunStatus): RunView {
  const stage = view.stages[status.stage];
  return { ...view, status, stages: { ...view.stages, [status.stage]: { ...stage, done: status.done, total: status.total ?? stage.total } } };
}

/** The run as the engine left it, after `stream-closed`: its own end state if it says one, else a failed run. */
function afterClose(view: RunView, status: RunStatus | null): RunView {
  const base: RunView = { ...view, closed: null, stopping: false, etaSeconds: null };
  if (status && status.state === "finished") return { ...base, phase: "finished", status, current: null };
  if (status && status.state === "stopped") return { ...withStatus(base, status), phase: "stopped" };
  if (status && status.state === "failed") {
    return { ...withStatus(base, status), phase: "failed", error: new EngineError("startRun", "failed", status.reason ?? ENGINE_SILENT, [], ENGINE_SILENT_NEXT) };
  }
  // the call failed, or the engine still says running: it cannot say why it stopped
  return { ...base, phase: "failed", error: new EngineError("startRun", "failed", ENGINE_SILENT, [], ENGINE_SILENT_NEXT) };
}

export function reduceRun(view: RunView, action: RunAction): RunView {
  switch (action.type) {
    case "starting":
      return { ...IDLE, stages: freshStages(), phase: "starting", campaign: action.campaign };
    case "started":
      return { ...view, phase: view.phase === "starting" ? "running" : view.phase, runId: action.runId };
    case "refused":
      return { ...view, phase: "failed", error: action.error };
    case "stopping":
      return { ...view, stopping: true, error: null };
    case "stopped":
      // run_stop answered: the engine finishes the business it is on and then writes its end event
      if (ENDED.includes(view.phase)) return { ...view, stopping: false };
      return { ...view, phase: "stopping", stopping: false };
    case "stop-refused":
      return { ...view, stopping: false, error: action.error };
    case "status-after-close":
      return view.closed ? afterClose(view, action.status) : view;
    case "event": {
      const e = action.event;
      // nothing after an end: not a late progress line, not the shell's stream-closed
      if (ENDED.includes(view.phase) || view.phase === "idle") return view;
      if (e.type === "stream-closed") return { ...view, closed: e };
      if (e.type === "progress") {
        return {
          ...view, phase: view.phase === "stopping" ? "stopping" : "running", current: e.stage, etaSeconds: e.etaSeconds,
          stages: { ...view.stages, [e.stage]: { ...view.stages[e.stage], done: e.done, total: e.total, message: e.message } },
        };
      }
      if (e.type === "stage-done") {
        const stage = view.stages[e.stage];
        return { ...view, stages: { ...view.stages, [e.stage]: { ...stage, done: stage.total ?? stage.done, summary: e.summary } } };
      }
      if (e.type === "notice") return { ...view, notices: [...view.notices, e.text] };
      if (e.type === "finished") return { ...view, phase: "finished", status: e.status, current: null, etaSeconds: null };
      if (e.type === "stopped") return { ...withStatus(view, e.status), phase: "stopped", stopping: false };
      return { ...withStatus(view, e.status), phase: "failed", error: new EngineError("startRun", e.error.kind, e.error.message, e.error.details) };
    }
  }
}
