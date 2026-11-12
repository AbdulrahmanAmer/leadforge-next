// Forget is report-first (src/forget.ts): the engine's dry run first, the confirmation shows its numbers, only the
// confirm makes the real call. Each test says what it was seen red against in docs/slices/L11-window.md.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { EngineError } from "../src/engine.ts";
import { createMockEngine } from "../src/engine.mock.ts";
import { ForgetFlow, holdsNothing, reportLines } from "../src/forget.ts";

const ui = join(dirname(fileURLToPath(import.meta.url)), "..");
const KNOWN = "priya@harbourside-motors.example"; // the made-up workspace holds this person
const DOMAIN = "harbourside-motors.example";

/** An engine that records every forget call as [value, dryRun], over a real mock engine. */
function recorded(over = {}) {
  const mock = createMockEngine({ speed: 0 });
  const calls = [];
  const engine = {
    ...mock,
    async forgetPerson(value, dryRun) {
      calls.push([value, dryRun]);
      if (over.dry && dryRun) return over.dry(value);
      if (over.real && !dryRun) return over.real(value);
      return mock.forgetPerson(value, dryRun);
    },
  };
  return { engine, mock, calls };
}

test("a dry run changes nothing in the workspace; the real call does, and returns the same numbers", async () => {
  const e = createMockEngine({ speed: 0 });
  const before = JSON.stringify([await e.listPeople({ search: "", limit: 50 }), await e.purgeReport()]);
  const dry = await e.forgetPerson(DOMAIN, true);
  assert.ok(dry.rows > 0 && dry.filesRemoved > 0, "the made-up workspace holds this domain");
  assert.equal(JSON.stringify([await e.listPeople({ search: "", limit: 50 }), await e.purgeReport()]), before, "nothing changed");
  const real = await e.forgetPerson(DOMAIN, false);
  assert.deepEqual([real.kind, real.rows, real.filesRemoved, real.filesEdited], [dry.kind, dry.rows, dry.filesRemoved, dry.filesEdited]);
  assert.notEqual(JSON.stringify([await e.listPeople({ search: "", limit: 50 }), await e.purgeReport()]), before, "the real call changed it");
});

test("check asks the engine for a dry run and only that; the state shows its numbers and its words", async () => {
  const { engine, calls } = recorded();
  const flow = new ForgetFlow(engine);
  await flow.check(KNOWN);
  assert.deepEqual(calls, [[KNOWN, true]], "one call, a dry run");
  assert.equal(flow.state.step, "report");
  const r = flow.state.report;
  assert.deepEqual(reportLines(r), ["7 database rows", "2 files that would be removed", "3 files that would be edited (lines taken out)"]);
  assert.ok(r.warnings.some((w) => w.startsWith("Nothing was deleted")), "the engine's warnings are kept as they came");
});

test("only confirm makes the real call, after the dry run, and the real result is the end state", async () => {
  const { engine, calls } = recorded();
  const flow = new ForgetFlow(engine);
  assert.equal(await flow.confirm(), null, "nothing to confirm before a report");
  assert.deepEqual(calls, []);
  await flow.check(KNOWN);
  const result = await flow.confirm();
  assert.deepEqual(calls, [[KNOWN, true], [KNOWN, false]], "two answers in order: the report, then the real call");
  assert.equal(flow.state.step, "done");
  assert.equal(flow.state.result, result);
  assert.equal(result.rows, 7);
  assert.ok(!result.warnings.some((w) => w.startsWith("Nothing was deleted")), "the real result has the real answer's words");
});

test("a dry run that finds nothing says so and has no way to delete", async () => {
  const { engine, calls } = recorded();
  const flow = new ForgetFlow(engine);
  await flow.check("nobody-here@nowhere.example");
  assert.equal(flow.state.step, "nothing");
  assert.ok(holdsNothing(flow.state.report));
  assert.equal(await flow.confirm(), null, "confirm does nothing from here");
  assert.deepEqual(calls, [["nobody-here@nowhere.example", true]], "no real call was ever made");
  assert.equal(flow.state.step, "nothing");
});

test("any one of the three numbers keeps the flow out of 'nothing'", () => {
  const base = { kind: "domain", value: "x.example", rows: 0, filesRemoved: 0, filesEdited: 0, warnings: [] };
  assert.equal(holdsNothing(base), true);
  assert.equal(holdsNothing({ ...base, rows: 1 }), false);
  assert.equal(holdsNothing({ ...base, filesRemoved: 1 }), false);
  assert.equal(holdsNothing({ ...base, filesEdited: 1 }), false);
});

test("a dry run that fails shows the engine's error, deletes nothing, and can be asked again", async () => {
  let failing = true;
  const { engine, calls } = recorded({
    dry: (v) => {
      if (failing) throw new EngineError("forgetPerson", "input", "Nothing was changed.", ["in use by a running run"], "nothing was changed");
      return { kind: "domain", value: v, rows: 3, filesRemoved: 1, filesEdited: 0, warnings: [] };
    },
  });
  const flow = new ForgetFlow(engine);
  await flow.check(DOMAIN);
  assert.equal(flow.state.step, "report-failed");
  assert.equal(flow.state.error.message, "Nothing was changed.");
  assert.deepEqual(flow.state.error.details, ["in use by a running run"]);
  assert.equal(await flow.confirm(), null);
  assert.deepEqual(calls, [[DOMAIN, true]], "no real call after a failed report");
  failing = false;
  await flow.check(DOMAIN);
  assert.equal(flow.state.step, "report");
});

test("a real call that fails keeps the report and the error, and confirm can be tried again", async () => {
  let failing = true;
  const { engine, calls } = recorded({
    real: (v) => {
      if (failing) throw new EngineError("forgetPerson", "failed", "Not everything could be deleted.", ["a sheet is open"], null);
      return { kind: "domain", value: v, rows: 21, filesRemoved: 2, filesEdited: 3, warnings: [] };
    },
  });
  const flow = new ForgetFlow(engine);
  await flow.check(DOMAIN);
  assert.equal(await flow.confirm(), null);
  assert.equal(flow.state.step, "delete-failed");
  assert.equal(flow.state.report.rows, 14, "the report (the dry run's own 14 rows) is still on screen");
  failing = false;
  assert.equal((await flow.confirm()).rows, 21);
  assert.equal(flow.state.step, "done");
  assert.deepEqual(calls.map(([, dry]) => dry), [true, false, false]);
});

test("a check overtaken by a newer one never reaches the state: the report is always the one for the value shown", async () => {
  const gates = {};
  const { engine, calls } = recorded({
    dry: (v) => new Promise((resolve) => { gates[v] = () => resolve({ kind: "domain", value: v, rows: v === "slow.example" ? 99 : 1, filesRemoved: 1, filesEdited: 0, warnings: [] }); }),
  });
  const flow = new ForgetFlow(engine);
  const slow = flow.check("slow.example");
  const fast = flow.check("fast.example");
  gates["fast.example"]();
  await fast;
  gates["slow.example"]();
  await slow;
  assert.equal(flow.state.value, "fast.example");
  assert.equal(flow.state.report.rows, 1);
  await flow.confirm();
  assert.deepEqual(calls.at(-1), ["fast.example", false], "the confirm acts on the value of the report shown");
});

test("while the real call runs, a second confirm does not make a second call", async () => {
  let release;
  const { engine, calls } = recorded({ real: (v) => new Promise((r) => { release = () => r({ kind: "domain", value: v, rows: 1, filesRemoved: 1, filesEdited: 0, warnings: [] }); }) });
  const flow = new ForgetFlow(engine);
  await flow.check(DOMAIN);
  const first = flow.confirm();
  assert.equal(await flow.confirm(), null);
  release();
  await first;
  assert.deepEqual(calls.filter(([, dry]) => !dry).length, 1);
});

test("the screen reaches the engine's forget only through the flow", () => {
  const people = readFileSync(join(ui, "src", "screens", "People.tsx"), "utf8");
  assert.doesNotMatch(people, /forgetPerson\(/, "People.tsx never calls forgetPerson itself");
  const flow = readFileSync(join(ui, "src", "forget.ts"), "utf8");
  assert.equal([...flow.matchAll(/forgetPerson\(\w+(?:\.\w+)?, (true|false)\)/g)].map((m) => m[1]).join(","), "true,false", "one dry call, one real call");
});

test("the seam sends the engine's own key, dry_run (snake_case), true then false", async () => {
  const sent = [];
  globalThis.window = {
    __TAURI_INTERNALS__: {
      invoke: async (cmd, args) => { sent.push([cmd, args]); return { kind: "domain", value: "x.example", rows: 0, filesRemoved: 0, filesEdited: 0, warnings: [] }; },
      transformCallback: () => 0,
    },
  };
  const { tauriEngine } = await import("../src/engine.tauri.ts");
  await tauriEngine.forgetPerson("x.example", true);
  await tauriEngine.forgetPerson("x.example", false);
  assert.deepEqual(sent, [
    ["person_forget", { value: "x.example", dry_run: true }],
    ["person_forget", { value: "x.example", dry_run: false }],
  ]);
});
