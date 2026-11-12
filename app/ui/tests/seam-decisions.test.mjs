// The seam decisions of 2026-11-12 as the mock engine and the screens' helpers keep them.
import assert from "node:assert/strict";
import { test } from "node:test";
import { EngineError } from "../src/engine.ts";
import { createMockEngine, UNNAMED_RUN } from "../src/engine.mock.ts";
import { NOT_RECORDED, cleanUpLine, formatDateOrNot, runTitle, textOrNot } from "../src/lib.ts";

const draft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "Online booking for MOT tests", sicCodes: [], maxLeads: 50 };
const refused = (engine, d) => engine.createCampaign(d).then(() => assert.fail("was not refused"), (e) => { assert.ok(e instanceof EngineError); return e; });

/* 2 and 3: the three refusals, each naming its field */
test("an empty offer is refused with kind input, naming the field `offer`", async () => {
  const engine = createMockEngine({ speed: 0 });
  for (const offer of ["", "   "]) {
    const e = await refused(engine, { ...draft, offer });
    assert.equal(e.kind, "input");
    assert.ok(e.details.some((d) => d.startsWith("offer:")));
  }
  assert.ok((await engine.createCampaign(draft)).searches > 0, "a filled offer is accepted");
});

test("Companies House without SIC codes is refused (`sicCodes`); dvsa needs none; with codes it is accepted", async () => {
  const engine = createMockEngine({ speed: 0 });
  const e = await refused(engine, { ...draft, source: "companies_house", sicCodes: [] });
  assert.equal(e.kind, "input");
  assert.ok(e.details.some((d) => d.startsWith("sicCodes:")));
  assert.ok(!(await refused(engine, { ...draft, offer: "" })).details.some((d) => d.startsWith("sicCodes:")));
  assert.ok((await engine.createCampaign({ ...draft, source: "companies_house", sicCodes: ["45200", "45111"] })).searches > 0);
});

test("a register that is not configured is refused on `source`, and `next` names the configured one", async () => {
  const engine = createMockEngine({ speed: 0, sources: ["dvsa", "companies_house"], configured: ["dvsa"] });
  const e = await refused(engine, { ...draft, source: "companies_house", sicCodes: ["45200"] });
  assert.equal(e.kind, "input");
  assert.ok(e.details.some((d) => d.startsWith("source:")));
  assert.match(e.next, /dvsa/);
  assert.doesNotMatch(e.next, /companies_house/);
  const none = await refused(createMockEngine({ speed: 0, sources: [] }), draft);
  assert.ok(none.details.some((d) => d.startsWith("source:")));
});

test("settings_get lists the configured registers (both by default, none when none is switched on)", async () => {
  assert.deepEqual((await createMockEngine({ speed: 0 }).getSettings()).sources, ["dvsa", "companies_house"]);
  assert.deepEqual((await createMockEngine({ speed: 0, sources: ["dvsa"] }).getSettings()).sources, ["dvsa"]);
  assert.deepEqual((await createMockEngine({ speed: 0, sources: [] }).getSettings()).sources, []);
});

/* 8: the engine's settings never carry the look */
test("settings_set refuses a theme or an accent, and settings_get never carries them", async () => {
  const engine = createMockEngine({ speed: 0 });
  for (const patch of [{ theme: "dark" }, { accent: "brass" }, { openSheetWhenDone: false, theme: "light" }]) {
    await assert.rejects(engine.setSettings(patch), (e) => e.kind === "usage" && e.details.some((d) => /theme|accent/.test(d)));
  }
  const s = await engine.getSettings();
  assert.deepEqual(Object.keys(s).sort(), ["openSheetWhenDone", "sheetFormats", "sources", "workspace"]);
  assert.equal(s.openSheetWhenDone, true, "a refused patch changed nothing");
});

/* 9: about */
test("about returns the engine's version and the licences only", async () => {
  assert.deepEqual(Object.keys(await createMockEngine({ speed: 0 }).about()).sort(), ["engineVersion", "licence", "licences"]);
});

/* 4: a key command the engine cannot do yet answers `missing`, no new kind */
test("a key command the engine cannot do yet answers kind `missing`, in words about keys", async () => {
  const engine = createMockEngine({ speed: 0, missing: ["listKeys", "saveKey", "removeKey"] });
  for (const [call, action] of [[() => engine.listKeys(), "listKeys"], [() => engine.saveKey("companies_house_key", "made-up"), "saveKey"], [() => engine.removeKey("companies_house_key"), "removeKey"]]) {
    await assert.rejects(call(), (e) => {
      assert.equal(e.kind, "missing");
      assert.equal(e.action, action);
      assert.match(e.message, /key/i, "the title is about keys");
      assert.ok(e.details.length > 0);
      return true;
    });
  }
});

/* 5 to 7: nullable fields, and what the screens' helpers make of a null */
test("the made-up workspace carries a run, campaign and person whose nullable fields are all null", async () => {
  const engine = createMockEngine({ speed: 0 });
  const campaign = (await engine.listCampaigns()).find((c) => c.name === null);
  assert.ok(campaign && campaign.source === null && campaign.keptUntil === null && Object.hasOwn(campaign, "keptUntil"));
  const { people } = await engine.listPeople({ search: "", limit: 50 });
  assert.ok(people.some((p) => p.source === null && p.foundAt === null && p.campaign === null));
  assert.ok(people.some((p) => p.source === null && p.foundAt !== null), "and one with only the page missing");
  const seen = [];
  await new Promise((resolve) => { void engine.startRun({ campaign: UNNAMED_RUN, resume: false }, (e) => { if (e.type === "finished") { seen.push(e.status); resolve(); } }); });
  const [status] = seen;
  assert.equal(status.campaign, null);
  assert.equal(status.done, null);
  assert.deepEqual(status.counts, { businesses: status.counts.businesses, contacts: status.counts.contacts, purged: null, expiringIn30Days: null });
});

test("a null is said in words: never empty, never a dash, never \"Invalid Date\"", () => {
  assert.equal(NOT_RECORDED, "not recorded");
  for (const v of [null, "", "   ", "not a date"]) {
    assert.equal(formatDateOrNot(v), NOT_RECORDED, JSON.stringify(v));
  }
  assert.equal(formatDateOrNot("2026-11-03"), "3 Nov 2026");
  assert.equal(textOrNot(null), NOT_RECORDED);
  assert.equal(textOrNot(" "), NOT_RECORDED);
  assert.equal(textOrNot("harbourside-motors.example/contact"), "harbourside-motors.example/contact");
  for (const out of [formatDateOrNot(null), textOrNot(null)]) assert.doesNotMatch(out, /^[-–—]$|Invalid|NaN|undefined|null/);
});

test("the run is named by its id when the engine has no campaign name", () => {
  assert.equal(runTitle({ campaign: null, runId: "r-20261112-5e90" }), "r-20261112-5e90");
  assert.equal(runTitle({ campaign: "bristol-mot-garages", runId: "r-1" }), "bristol-mot-garages");
});

test("the clean-up line leaves out a null count, and is absent when both are null", () => {
  assert.equal(cleanUpLine({ purged: 4, expiringIn30Days: 9 }), "Clean-up: 4 records deleted at the start, 9 expire in the next 30 days.");
  assert.equal(cleanUpLine({ purged: null, expiringIn30Days: 9 }), "Clean-up: 9 expire in the next 30 days.");
  assert.equal(cleanUpLine({ purged: 1, expiringIn30Days: null }), "Clean-up: 1 record deleted at the start.");
  assert.equal(cleanUpLine({ purged: 0, expiringIn30Days: 0 }), "Clean-up: 0 records deleted at the start, 0 expire in the next 30 days.", "zero is a count, not a null");
  assert.equal(cleanUpLine({ purged: null, expiringIn30Days: null }), null);
});
