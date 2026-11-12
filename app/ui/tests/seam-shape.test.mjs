// The seam's shape rule, checked against the TYPES in src/engine.ts (parsed here, so the types are the one answer):
//   a field that left a type is ABSENT from the JSON; a nullable field is PRESENT with null; every other field is not null.
// Both answerers are held to it: the mock engine (what the screens and renders run on) and the stand-in engine
// (what the real window runs on until the engine's own `window` commands exist). Each must also carry every
// nullable field as null at least once, so a screen that mishandles a null is met by the tests and the renders.
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { after, before, test } from "node:test";
import { fileURLToPath } from "node:url";
import { createMockEngine } from "../src/engine.mock.ts";

const ui = join(dirname(fileURLToPath(import.meta.url)), "..");
const STANDIN = join(ui, "..", "src-tauri", "test-resources", "standin", "leadforge_window_standin.py");
const PYTHON = process.env.LEADFORGE_TEST_PYTHON ?? "python";

/* ------------------------------------------------------------ the types, as written in engine.ts */
function parseInterfaces(source) {
  const out = {};
  for (const m of source.matchAll(/export interface (\w+)(?: extends [\w, ]+)? \{\n([\s\S]*?)\n\}/g)) {
    const fields = {};
    for (const line of m[2].split("\n")) {
      const f = /^  (\w+)(\?)?: (.+);$/.exec(line);
      if (f) fields[f[1]] = { optional: Boolean(f[2]), nullable: /(^|\| )null$/.test(f[3]) };
    }
    out[m[1]] = fields;
  }
  return out;
}
const TYPES = parseInterfaces(readFileSync(join(ui, "src", "engine.ts"), "utf8"));

/** Every nullable field the decisions name, as "Type.field": each must be null somewhere in each answerer's data. */
const NULLABLE_FIELDS = [
  "RunStatus.campaign", "RunStatus.done", "RunCounts.purged", "RunCounts.expiringIn30Days",
  "Campaign.name", "Campaign.source", "Campaign.keptUntil",
  "Person.source", "Person.foundAt", "Person.campaign",
];

test("engine.ts: the types hold the decided nullable fields, and theme, accent and windowVersion are gone", () => {
  for (const key of NULLABLE_FIELDS) {
    const [type, field] = key.split(".");
    assert.ok(TYPES[type]?.[field]?.nullable, `${key} is nullable`);
  }
  assert.deepEqual(Object.keys(TYPES.Settings).sort(), ["openSheetWhenDone", "sheetFormats", "sources", "workspace"]);
  assert.deepEqual(Object.keys(TYPES.About).sort(), ["engineVersion", "licence", "licences"]);
  assert.ok("offer" in TYPES.CampaignDraft && "sicCodes" in TYPES.CampaignDraft);
});

/** `seen` collects the Type.field pairs found null. Throws on any extra, missing or wrongly null field. */
function exact(value, type, where, seen) {
  assert.ok(TYPES[type], `no type ${type}`);
  assert.ok(value !== null && typeof value === "object" && !Array.isArray(value), `${where}: an object`);
  assert.deepEqual(Object.keys(value).sort(), Object.keys(TYPES[type]).sort(), `${where}: exactly the fields of ${type}`);
  for (const [field, info] of Object.entries(TYPES[type])) {
    if (value[field] === null) {
      assert.ok(info.nullable, `${where}.${field} is null but ${type}.${field} is not nullable`);
      seen.add(`${type}.${field}`);
    }
  }
}
const each = (list, type, where, seen) => { assert.ok(Array.isArray(list)); list.forEach((v, i) => exact(v, type, `${where}[${i}]`, seen)); };

function checkOutputs(o, seen) {
  exact(o.plan, "CampaignPlan", "plan", seen);
  exact(o.status, "RunStatus", "status", seen);
  exact(o.status.counts, "RunCounts", "status.counts", seen);
  exact(o.stopped, "RunStatus", "stopped", seen);
  exact(o.stopped.counts, "RunCounts", "stopped.counts", seen);
  each(o.campaigns, "Campaign", "campaigns", seen);
  for (const c of o.campaigns) if (c.sheet) { exact(c.sheet, "Sheet", "campaign.sheet", seen); each(c.sheet.files, "SheetFile", "files", seen); }
  exact(o.sheet, "Sheet", "sheet", seen);
  exact(o.people, "PeoplePage", "people", seen);
  each(o.people.people, "Person", "people.people", seen);
  exact(o.forget, "ForgetResult", "forget", seen);
  exact(o.suppress, "SuppressResult", "suppress", seen);
  for (const k of ["report", "applied"]) exact(o[k], "PurgeReport", k, seen);
  exact(o.everything, "PurgeEverythingResult", "everything", seen);
  for (const k of ["retention", "retentionSet"]) exact(o[k], "Retention", k, seen);
  each(o.keys, "KeyStatus", "keys", seen);
  exact(o.keySaved, "KeyStatus", "keySaved", seen);
  exact(o.keyRemoved, "KeyStatus", "keyRemoved", seen);
  for (const k of ["settings", "settingsSet"]) exact(o[k], "Settings", k, seen);
  exact(o.about, "About", "about", seen);
  each(o.about.licences, "Licence", "licences", seen);
}

/* ------------------------------------------------------------------------------- the mock */
test("the mock engine answers every command in exactly the fields of its type, and carries each nullable field as null", async () => {
  const engine = createMockEngine({ speed: 0, runEndsNull: true });
  const draft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "Online booking", sicCodes: [], maxLeads: 50 };
  const events = [];
  const ended = new Promise((resolve) => {
    void engine.startRun({ campaign: "bristol-mot-garages", resume: false }, (e) => { events.push(e); if (e.type === "finished") resolve(); });
  });
  await ended;
  const finished = events.at(-1);
  const status = finished.status;
  const stopRun = createMockEngine({ speed: 0, runEndsNull: true, runFreezesAfter: 3 });
  await stopRun.startRun({ campaign: "x", resume: false }, () => {});
  const out = {
    plan: await engine.createCampaign(draft), status, stopped: await stopRun.stopRun("r-20261112-5e90"),
    campaigns: await engine.listCampaigns(), sheet: await engine.exportSheet("r-20261103-a41c"),
    people: await engine.listPeople({ search: "", limit: 50 }),
    forget: await engine.forgetPerson("nadia@fishpondsroad.example"), suppress: await engine.suppressAddress("cliftondowngarage.example"),
    report: await engine.purgeReport(), applied: await engine.purgeApply(), everything: await createMockEngine({ speed: 0 }).purgeEverything(),
    retention: await engine.getRetention(), retentionSet: await engine.setRetention(6),
    keys: await engine.listKeys(), keySaved: await engine.saveKey("opencorporates_token", "made-up-000"), keyRemoved: await engine.removeKey("opencorporates_token"),
    settings: await engine.getSettings(), settingsSet: await engine.setSettings({ openSheetWhenDone: false }), about: await engine.about(),
  };
  // the run handle is the first thing a run gives back; every event of the stream that carries a status is exact too
  const seen = new Set();
  const handle = await createMockEngine({ speed: 0 }).startRun({ campaign: "c", resume: false }, () => {});
  assert.deepEqual(Object.keys(handle), ["runId"]);
  checkOutputs(out, seen);
  assert.equal(events.at(-1).type, "finished");
  for (const key of NULLABLE_FIELDS) assert.ok(seen.has(key), `the mock never carries ${key} as null`);
});

/* ---------------------------------------------------------------------------- the stand-in */
let work;
before(() => { work = mkdtempSync(join(ui, ".standin-work-")); });
after(() => { rmSync(work, { recursive: true, force: true }); });

function standin(name, args, cwd = work) {
  const r = spawnSync(PYTHON, ["-X", "utf8", "-I", STANDIN, "window", name], { cwd, input: JSON.stringify(args), encoding: "utf8", timeout: 20000 });
  assert.equal(r.error, undefined, `could not start ${PYTHON}`);
  const text = r.stdout.trim();
  assert.ok(text, `${name}: no stdout (stderr: ${r.stderr})`);
  return { doc: JSON.parse(text), code: r.status };
}
const ok = (name, args, cwd) => { const r = standin(name, args, cwd); assert.equal(r.code, 0, `${name}: ${JSON.stringify(r.doc)}`); return r.doc; };

/** A run of the stand-in, stopped after its first progress event; resolves with every stdout line, parsed. */
function standinRun(campaign, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, ["-X", "utf8", "-I", STANDIN, "window", "run_start"], { cwd, stdio: ["pipe", "pipe", "ignore"] });
    const lines = [];
    let buffer = "";
    let flagged = false;
    const timer = setTimeout(() => { child.kill(); reject(new Error("the stand-in run did not end in 30 s")); }, 30000);
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      buffer += chunk;
      let at;
      while ((at = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, at); buffer = buffer.slice(at + 1);
        if (!line.trim()) continue;
        const doc = JSON.parse(line);
        lines.push(doc);
        if (doc.type === "progress" && !flagged) { flagged = true; writeFileSync(join(cwd, "standin-stop.flag"), "stop"); }
      }
    });
    child.on("close", () => { clearTimeout(timer); resolve(lines); });
    child.stdin.end(JSON.stringify({ args: { campaign, resume: false } }));
  });
}

test("the stand-in answers every command in exactly the fields of its type, and carries each nullable field as null", async () => {
  const cwd = mkdtempSync(join(work, "all-"));
  const draft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "Online booking", sicCodes: [], maxLeads: 50 };
  const lines = await standinRun("unnamed-run", cwd);
  assert.deepEqual(Object.keys(lines[0]), ["runId"], "line 1 of run_start is the RunHandle");
  const last = lines.at(-1);
  assert.equal(last.type, "stopped", "the last event ends the run");
  for (const line of lines.slice(1)) if (line.status) assert.equal(lines.indexOf(line), lines.length - 1, "only the last event carries a status");
  const stopFlag = join(cwd, "standin-stop.flag");
  rmSync(stopFlag, { force: true });
  const out = {
    plan: ok("campaign_create", { draft }, cwd), status: last.status, stopped: null,
    campaigns: ok("campaigns_list", {}, cwd), sheet: ok("sheet_export", { runId: "r-20261103-a41c" }, cwd),
    people: ok("people_list", { query: { search: "", limit: 50 } }, cwd),
    forget: ok("person_forget", { value: "nadia@fishpondsroad.example" }, cwd), suppress: ok("address_suppress", { value: "cliftondowngarage.example", kind: null }, cwd),
    report: ok("purge_report", {}, cwd), applied: ok("purge_apply", {}, cwd),
    retention: ok("retention_get", {}, cwd), retentionSet: ok("retention_set", { months: 6 }, cwd),
    keys: ok("keys_list", {}, cwd), keySaved: ok("key_save", { name: "opencorporates_token", value: "made-up-000" }, cwd),
    keyRemoved: ok("key_remove", { name: "opencorporates_token" }, cwd),
    settings: ok("settings_get", {}, cwd), settingsSet: ok("settings_set", { patch: { openSheetWhenDone: false } }, cwd), about: ok("about", {}, cwd),
  };
  // run_stop needs a running run: the state holds the stopped one, so ask for its status the way the window does
  out.stopped = ok("run_status", { runId: last.status.runId }, cwd);
  out.everything = ok("purge_everything", { confirm: true }, cwd);
  const seen = new Set();
  checkOutputs(out, seen);
  for (const key of NULLABLE_FIELDS) assert.ok(seen.has(key), `the stand-in never carries ${key} as null`);
});

test("the stand-in refuses a blank offer, SIC codes missing for Companies House, and a register that is not configured", () => {
  const cwd = mkdtempSync(join(work, "refusals-"));
  const base = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "Online booking", sicCodes: [], maxLeads: 50 };
  ok("settings_get", {}, cwd); // makes the state file
  const refusal = (draft) => { const r = standin("campaign_create", { draft }, cwd); assert.equal(r.code, 4); assert.equal(r.doc.kind, "input"); return r.doc; };

  assert.ok(refusal({ ...base, offer: "" }).details.some((d) => d.startsWith("offer:")), "blank offer names `offer`");
  assert.ok(refusal({ ...base, offer: "   " }).details.some((d) => d.startsWith("offer:")), "a blank offer of spaces");
  const noSic = refusal({ ...base, source: "companies_house", sicCodes: [] });
  assert.ok(noSic.details.some((d) => d.startsWith("sicCodes:")), "Companies House without SIC codes names `sicCodes`");
  assert.ok(!refusal({ ...base, offer: "" }).details.some((d) => d.startsWith("sicCodes:")), "dvsa needs none");
  assert.equal(ok("campaign_create", { draft: { ...base, source: "companies_house", sicCodes: ["45200"] } }, cwd).searches, 12);

  // a workspace configured for dvsa alone: Companies House is refused on the `source` field, and `next` names the configured one
  const state = join(cwd, "standin-state.json");
  const held = JSON.parse(readFileSync(state, "utf8"));
  held.configured = ["dvsa"];
  held.settings.sources = ["dvsa"];
  writeFileSync(state, JSON.stringify(held));
  assert.deepEqual(ok("settings_get", {}, cwd).sources, ["dvsa"]);
  const stale = refusal({ ...base, source: "companies_house", sicCodes: ["45200"] });
  assert.ok(stale.details.some((d) => d.startsWith("source:")));
  assert.match(stale.next, /dvsa/);
  assert.doesNotMatch(stale.next, /companies_house/);
  assert.equal(ok("campaign_create", { draft: base }, cwd).searches, 12);
});

test("the stand-in's settings carry no theme and no accent, whatever an old state file or a patch holds", () => {
  const cwd = mkdtempSync(join(work, "settings-"));
  // a state file of an older stand-in (no version, theme and accent inside) is not read
  writeFileSync(join(cwd, "standin-state.json"), JSON.stringify({ settings: { theme: "dark", accent: "brass", workspace: "X:\\old", sheetFormats: ["csv"], openSheetWhenDone: false }, people: [], campaigns: [] }));
  const fresh = ok("settings_get", {}, cwd);
  assert.deepEqual(Object.keys(fresh).sort(), ["openSheetWhenDone", "sheetFormats", "sources", "workspace"]);
  const patched = ok("settings_set", { patch: { theme: "dark", accent: "ember", openSheetWhenDone: false } }, cwd);
  assert.deepEqual(Object.keys(patched).sort(), ["openSheetWhenDone", "sheetFormats", "sources", "workspace"]);
  assert.equal(patched.openSheetWhenDone, false);
  assert.ok(!JSON.stringify(ok("settings_get", {}, cwd)).match(/theme|accent/));
  assert.ok(!Object.hasOwn(ok("about", {}, cwd), "windowVersion"));
});
