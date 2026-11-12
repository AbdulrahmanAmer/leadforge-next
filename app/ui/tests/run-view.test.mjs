// The Run screen's state (src/run.ts): the stopping state after run_stop answers, the shell's stream-closed,
// and the one runStatus asked after it. Run with `npm test`.
import assert from "node:assert/strict";
import { test } from "node:test";
import { EngineError } from "../src/engine.ts";
import { ENGINE_SILENT, IDLE, isLive, reduceRun } from "../src/run.ts";
import { createMockEngine } from "../src/engine.mock.ts";

const status = (state, extra = {}) => ({
  runId: "r-1", campaign: "bristol-mot-garages", state, stage: "enrich", done: 36, total: 212, etaSeconds: null,
  counts: { businesses: 212, contacts: 40, purged: 4, expiringIn30Days: 9 }, startedAt: "2026-11-12T10:00:00Z", reason: null, ...extra,
});
const progress = { type: "progress", stage: "enrich", done: 36, total: 212, message: "harbourside-motors.example: 1 phone", etaSeconds: 60, at: "2026-11-12T10:01:00Z" };
const closed = { type: "stream-closed", exitCode: null, reason: "ended-by-core" };

function running() {
  let v = reduceRun(IDLE, { type: "starting", campaign: "bristol-mot-garages" });
  v = reduceRun(v, { type: "started", runId: "r-1" });
  return reduceRun(v, { type: "event", event: progress });
}

test("after run_stop answers the run is stopping until its end event, and stays live", () => {
  let v = reduceRun(running(), { type: "stopping" });
  assert.equal(v.stopping, true, "the request is on its way");
  v = reduceRun(v, { type: "stopped", status: status("stopped") });
  assert.equal(v.phase, "stopping", "the answer to run_stop is not the end of the run");
  assert.equal(v.stopping, false);
  assert.ok(isLive(v.phase));
  v = reduceRun(v, { type: "event", event: { ...progress, done: 37 } });
  assert.equal(v.phase, "stopping", "progress while finishing the current business keeps the stopping state");
  v = reduceRun(v, { type: "event", event: { type: "stopped", status: status("stopped") } });
  assert.equal(v.phase, "stopped");
  assert.ok(!isLive(v.phase));
});

test("an end event that came before run_stop's answer is kept", () => {
  let v = reduceRun(running(), { type: "event", event: { type: "stopped", status: status("stopped") } });
  v = reduceRun(v, { type: "stopped", status: status("stopped") });
  assert.equal(v.phase, "stopped");
});

test("stream-closed with no end event: the engine's own answer to runStatus is shown", () => {
  let v = reduceRun(running(), { type: "event", event: closed });
  assert.deepEqual(v.closed, closed, "the screen now asks runStatus once");
  assert.equal(v.phase, "running");
  const failed = reduceRun(v, { type: "status-after-close", status: status("failed", { reason: "The run's process was ended from outside." }) });
  assert.equal(failed.phase, "failed");
  assert.equal(failed.error.message, "The run's process was ended from outside.");
  assert.equal(failed.closed, null);
  const stopped = reduceRun(v, { type: "status-after-close", status: status("stopped") });
  assert.equal(stopped.phase, "stopped");
});

test("stream-closed and runStatus still says running, or fails: a failed run, a plain sentence, and continue", () => {
  const v = reduceRun(reduceRun(running(), { type: "stopped", status: status("stopped") }), { type: "event", event: closed });
  for (const answer of [status("running"), null]) {
    const after = reduceRun(v, { type: "status-after-close", status: answer });
    assert.equal(after.phase, "failed");
    assert.ok(after.error instanceof EngineError);
    assert.equal(after.error.message, ENGINE_SILENT);
    assert.match(after.error.next, /Continue the run/);
    assert.equal(after.runId, "r-1", "the run id stays: the screen offers Continue the run");
  }
});

test("nothing after an end event: not stream-closed, not a late progress line, not a late status", () => {
  const ended = reduceRun(running(), { type: "event", event: { type: "finished", status: status("finished") } });
  assert.equal(reduceRun(ended, { type: "event", event: closed }), ended);
  assert.equal(reduceRun(ended, { type: "event", event: progress }), ended);
  assert.equal(reduceRun(ended, { type: "status-after-close", status: null }), ended);
});

test("a refused start is the start-refused state: failed, no run id, the engine's error", () => {
  const error = new EngineError("startRun", "input", "The engine could not start the run: there is no such campaign.");
  const v = reduceRun(reduceRun(IDLE, { type: "starting", campaign: "standin-refuse-mot-garages" }), { type: "refused", error });
  assert.equal(v.phase, "failed");
  assert.equal(v.runId, null);
  assert.equal(v.error, error);
});

test("the mock: stopRun answers at once and the run writes its own stopped event after it", async () => {
  const engine = createMockEngine({ speed: 0.01, runFreezesAfter: 3 });
  const events = [];
  await engine.startRun({ campaign: "c", resume: false }, (e) => events.push(e));
  const answer = await engine.stopRun("r-20261112-5e90");
  assert.equal(answer.state, "stopped");
  assert.equal(events.filter((e) => e.type === "stopped").length, 0, "not yet");
  await new Promise((r) => setTimeout(r, 100));
  assert.equal(events.at(-1).type, "stopped");
});

test("the mock: a run that dies ends with one stream-closed and no end event", async () => {
  const engine = createMockEngine({ speed: 0, runDiesAfter: 2 });
  const events = [];
  await engine.startRun({ campaign: "c", resume: false }, (e) => events.push(e));
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(events.at(-1), { type: "stream-closed", exitCode: 1, reason: "exit" });
  assert.equal(events.filter((e) => ["finished", "stopped", "failed"].includes(e.type)).length, 0);
});
