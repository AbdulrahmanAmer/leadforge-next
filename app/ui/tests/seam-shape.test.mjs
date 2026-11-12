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
  // ruling 15 (2026-11-12): a register campaign is not estimated
  "CampaignPlan.estimatedBusinesses", "CampaignPlan.estimatedSites", "CampaignPlan.estimatedMinutes",
];

test("engine.ts: rulings 15 and 16 and the licence: the estimates and About.licence are nullable, KeyStatus.inUse is optional", () => {
  for (const f of ["estimatedBusinesses", "estimatedSites", "estimatedMinutes"]) assert.ok(TYPES.CampaignPlan[f].nullable, f);
  assert.ok(TYPES.About.licence.nullable, "About.licence");
  assert.deepEqual(TYPES.KeyStatus.inUse, { optional: true, nullable: false }, "TIGHTEN LATER: required once the follow-up lands");
});

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
  // an optional field (`name?:`) may be absent: only `KeyStatus.inUse`, until the engine's follow-up is on master
  const required = Object.entries(TYPES[type]).filter(([, i]) => !i.optional).map(([f]) => f);
  const extra = Object.keys(value).filter((f) => !(f in TYPES[type]));
  assert.deepEqual(extra, [], `${where}: fields that are not in ${type}`);
  assert.deepEqual(required.filter((f) => !(f in value)), [], `${where}: fields of ${type} missing`);
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
  const patched = ok("settings_set", { patch: { openSheetWhenDone: false } }, cwd);
  assert.deepEqual(Object.keys(patched).sort(), ["openSheetWhenDone", "sheetFormats", "sources", "workspace"]);
  assert.equal(patched.openSheetWhenDone, false);
  assert.ok(!JSON.stringify(ok("settings_get", {}, cwd)).match(/theme|accent|windowVersion/));
  const about = ok("about", {}, cwd);
  assert.ok(!JSON.stringify(about).match(/theme|accent|windowVersion/), "about carries no theme, accent or windowVersion");
});

test("the stand-in refuses a campaign draft with no `offer` key at all, kind input, naming `offer`", () => {
  const cwd = mkdtempSync(join(work, "no-offer-key-"));
  const { offer: _gone, ...noKey } = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "x", sicCodes: [], maxLeads: 50 };
  assert.ok(!("offer" in noKey));
  const r = standin("campaign_create", { draft: noKey }, cwd);
  assert.equal(r.code, 4);
  assert.equal(r.doc.kind, "input");
  assert.ok(r.doc.details.some((d) => d.startsWith("offer:")), `details name offer: ${JSON.stringify(r.doc.details)}`);
});

test("the stand-in refuses settings_set carrying a key the engine does not own (theme, accent, any unknown key), kind usage", () => {
  const cwd = mkdtempSync(join(work, "foreign-keys-"));
  for (const key of ["theme", "accent", "windowVersion", "somethingElse"]) {
    const r = standin("settings_set", { patch: { [key]: "dark", openSheetWhenDone: false } }, cwd);
    assert.equal(r.doc.kind, "usage", `${key}: ${JSON.stringify(r.doc)}`);
    assert.notEqual(r.code, 0, `${key} refused with a non-zero exit`);
    assert.ok(r.doc.details.some((d) => d.includes(key)), `${key}: details name the key`);
  }
  // refused whole: nothing of the patch was applied
  assert.equal(ok("settings_get", {}, cwd).openSheetWhenDone, true);
});

/* ------------------------------------------------------------------- the real engine (2026-11-12) */
// The 21 real commands' answers, collected through the core's own code path (app/src-tauri/tests/real_engine_shapes.rs,
// run by packaging/real-shapes.ps1 against a throwaway workspace and the repository's loopback fakes) into one file.
// Skipped when LF_REAL_ANSWERS is not set (CI has no fakes running). Every difference is listed, not only the first.
const ERROR_KINDS = ["failed", "usage", "environment", "input", "source", "keyring", "missing"];
const REAL = process.env.LF_REAL_ANSWERS;

/** Every shape finding in one collected answer set, as "label | field | expected | got". */
export function realFindings(answers) {
  const findings = [];
  const check = (fn) => { try { fn(); } catch (e) { findings.push(String(e.message).split("\n")[0]); } };
  const seen = new Set();
  const one = (label, type) => {
    const a = answers[label];
    if (!a) { findings.push(`${label} | (answer) | collected | not collected`); return; }
    if (!a.ok) { findings.push(`${label} | (answer) | ${type} | error ${JSON.stringify(a.doc).slice(0, 300)}`); return; }
    if (type === "null") { if (a.doc !== null) findings.push(`${label} | (answer) | null | ${JSON.stringify(a.doc).slice(0, 120)}`); return; }
    const many = type.endsWith("[]");
    const t = many ? type.slice(0, -2) : type;
    const list = many ? a.doc : [a.doc];
    if (many && !Array.isArray(list)) { findings.push(`${label} | (answer) | ${type} | ${typeof a.doc}`); return; }
    list.forEach((v, i) => {
      const where = many ? `${label}[${i}]` : label;
      check(() => exact(v, t, where, seen));
      if (t === "RunStatus" && v?.counts) check(() => exact(v.counts, "RunCounts", `${where}.counts`, seen));
      if (t === "Campaign" && v?.sheet) { check(() => exact(v.sheet, "Sheet", `${where}.sheet`, seen)); (v.sheet.files ?? []).forEach((f, j) => check(() => exact(f, "SheetFile", `${where}.sheet.files[${j}]`, seen))); }
      if (t === "Sheet") (v?.files ?? []).forEach((f, j) => check(() => exact(f, "SheetFile", `${where}.files[${j}]`, seen)));
      if (t === "PeoplePage") (v?.people ?? []).forEach((p, j) => check(() => exact(p, "Person", `${where}.people[${j}]`, seen)));
      if (t === "About") (v?.licences ?? []).forEach((l, j) => check(() => exact(l, "Licence", `${where}.licences[${j}]`, seen)));
    });
  };
  const expected = {
    settings_get: "Settings", campaign_create: "CampaignPlan", run_start_first_handle: "RunHandle", run_start_handle: "RunHandle", run_end_status: "RunStatus",
    run_status: "RunStatus", run_status_latest: "RunStatus", run_stop: "RunStatus", run_stop_end_status: "RunStatus",
    campaigns_list: "Campaign[]", sheet_export: "Sheet", people_list: "PeoplePage", person_forget: "ForgetResult",
    address_suppress: "SuppressResult", purge_report: "PurgeReport", purge_apply: "PurgeReport", retention_get: "Retention",
    retention_set: "Retention", keys_list: "KeyStatus[]", key_save: "KeyStatus", key_remove: "KeyStatus",
    settings_set: "Settings", about: "About", purge_everything: "PurgeEverythingResult", sheet_open: "null",
  };
  for (const [label, type] of Object.entries(expected)) {
    if (answers[label]?.expectError) continue;
    one(label, type);
  }
  // the answers that are errors on purpose, and every error document: exactly {kind, message, details, next}
  for (const [label, a] of Object.entries(answers)) {
    if (!a || a.ok || typeof a !== "object" || !("doc" in a)) continue;
    const d = a.doc;
    check(() => assert.deepEqual(Object.keys(d ?? {}).sort(), ["details", "kind", "message", "next"], `${label} | error document | kind, message, details, next | ${Object.keys(d ?? {}).join(", ")}`));
    check(() => assert.ok(ERROR_KINDS.includes(d?.kind), `${label} | kind | one of ${ERROR_KINDS.join(" ")} | ${d?.kind}`));
  }
  // the stream: every progress line, and the end events' status
  for (const [i, e] of (answers.run_start_events ?? []).entries()) {
    const keys = { progress: ["at", "done", "etaSeconds", "message", "stage", "total", "type"], "stage-done": ["at", "stage", "summary", "type"],
      notice: ["at", "text", "type"], finished: ["status", "type"], stopped: ["status", "type"], failed: ["error", "status", "type"] }[e.type];
    if (!keys) { findings.push(`run_start line ${i + 2} | type | a RunEvent type | ${e.type}`); continue; }
    check(() => assert.deepEqual(Object.keys(e).sort(), keys, `run_start line ${i + 2} (${e.type}) | fields | ${keys.join(", ")} | ${Object.keys(e).sort().join(", ")}`));
  }
  return findings;
}

test("the REAL engine's 21 commands answer in exactly the screens' types (LF_REAL_ANSWERS)", { skip: !REAL && "LF_REAL_ANSWERS not set" }, () => {
  const answers = JSON.parse(readFileSync(join(REAL, "answers.json"), "utf8"));
  const findings = realFindings(answers);
  for (const f of findings) console.log(`FINDING ${f}`);
  for (const [label, a] of Object.entries(answers)) {
    if (a?.expectError) console.log(`ANSWERED WITH AN ERROR (on purpose or for want of a keyring, so its type was not seen): ${label} ${JSON.stringify(a.doc).slice(0, 200)}`);
  }
  assert.deepEqual(findings, [], `${findings.length} finding(s)`);
});

test("the real-answer check can fail: a planted extra field, a missing field and a wrong null are each a finding", () => {
  const good = { ok: true, doc: { months: 6, min: 1, max: 12 } };
  const answers = { retention_get: good, retention_set: { ok: true, doc: { months: 6, min: 1, max: 12, extra: 1 } },
    purge_everything: { ok: true, doc: {} }, sheet_open: { ok: true, doc: null },
    about: { ok: true, doc: { engineVersion: null, licence: null, licences: [] } } };
  const f = realFindings(answers);
  assert.ok(f.some((x) => x.startsWith("retention_set: fields that are not in Retention")), f.join("\n"));
  assert.ok(f.some((x) => x.startsWith("purge_everything: fields of PurgeEverythingResult missing")), f.join("\n"));
  assert.ok(f.some((x) => x.includes("about.engineVersion is null")), f.join("\n"));
  assert.ok(!f.some((x) => x.includes("about.licence")), "About.licence may be null");
});
