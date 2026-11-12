// The mock engine's error paths: every action of the seam can fail, and fails as an EngineError that
// names its action. Run with `npm test` (Node runs the TypeScript engine files directly).
import assert from "node:assert/strict";
import { test } from "node:test";
import { ACTIONS, EngineError } from "../src/engine.ts";
import { createMockEngine } from "../src/engine.mock.ts";

const draft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "Online booking for MOT tests", sicCodes: [], maxLeads: 50 };

/** One call per action, with arguments the working mock accepts. */
const CALLS = {
  createCampaign: (e) => e.createCampaign(draft),
  startRun: (e) => e.startRun({ campaign: "bristol-mot-garages", resume: false }, () => {}),
  stopRun: (e) => e.stopRun("r-20261112-5e90"),
  runStatus: (e) => e.runStatus(),
  listCampaigns: (e) => e.listCampaigns(),
  exportSheet: (e) => e.exportSheet("r-20261103-a41c"),
  openSheet: (e) => e.openSheet("leadforge_data\\exports\\r-20261103-a41c\\leads.xlsx"),
  listPeople: (e) => e.listPeople({ search: "", limit: 50 }),
  forgetPerson: (e) => e.forgetPerson("priya@harbourside-motors.example", false),
  suppressAddress: (e) => e.suppressAddress("cliftondowngarage.example"),
  purgeReport: (e) => e.purgeReport(),
  purgeApply: (e) => e.purgeApply(),
  purgeEverything: (e) => e.purgeEverything(),
  getRetention: (e) => e.getRetention(),
  setRetention: (e) => e.setRetention(6),
  listKeys: (e) => e.listKeys(),
  saveKey: (e) => e.saveKey("companies_house_key", "made-up-key-000"),
  removeKey: (e) => e.removeKey("companies_house_key"),
  getSettings: (e) => e.getSettings(),
  setSettings: (e) => e.setSettings({ openSheetWhenDone: false }),
  about: (e) => e.about(),
};

test("the test covers every action of the seam", () => {
  assert.deepEqual(Object.keys(CALLS).sort(), [...ACTIONS].sort());
});

for (const action of ACTIONS) {
  test(`${action}: the planted failure is an EngineError that names the action`, async () => {
    const engine = createMockEngine({ speed: 0, fail: [action] });
    await assert.rejects(CALLS[action](engine), (error) => {
      assert.ok(error instanceof EngineError, "an EngineError");
      assert.equal(error.action, action);
      assert.ok(error.message.length > 0, "a message for the screen");
      assert.ok(error.details.length > 0, "the engine's own words");
      return true;
    });
  });

  test(`${action}: other actions still work when only this one fails`, async () => {
    const other = action === "about" ? "getSettings" : "about";
    const engine = createMockEngine({ speed: 0, fail: [action] });
    await assert.doesNotReject(CALLS[other](engine));
  });
}

test("a campaign without a country is refused with the field named", async () => {
  const engine = createMockEngine({ speed: 0 });
  await assert.rejects(engine.createCampaign({ ...draft, country: "" }), (error) => {
    assert.equal(error.kind, "input");
    assert.ok(error.details.some((d) => d.startsWith("target.geography.country")));
    return true;
  });
});

test("the retention period cannot be set above 12 months, and stays as it was", async () => {
  const engine = createMockEngine({ speed: 0 });
  await assert.rejects(engine.setRetention(13), (error) => error.kind === "usage" && error.action === "setRetention");
  await assert.rejects(engine.setRetention(0), EngineError);
  assert.equal((await engine.getRetention()).months, 12);
});

test("forget and suppress refuse an empty value", async () => {
  const engine = createMockEngine({ speed: 0 });
  await assert.rejects(engine.forgetPerson("  ", false), (error) => error.action === "forgetPerson");
  await assert.rejects(engine.suppressAddress(""), (error) => error.action === "suppressAddress");
});

test("stop without a run, a sheet for an unknown run and a file outside exports are refused", async () => {
  const engine = createMockEngine({ speed: 0 });
  await assert.rejects(engine.stopRun("r-none"), (error) => error.action === "stopRun");
  await assert.rejects(engine.exportSheet("r-none"), (error) => error.action === "exportSheet");
  await assert.rejects(engine.openSheet("C:\\Windows\\notepad.exe"), (error) => error.action === "openSheet" && error.kind === "usage");
});

test("a failing run ends its event stream with one failed event that carries the reason", async () => {
  const engine = createMockEngine({ speed: 0, runFails: true });
  const events = [];
  const ended = new Promise((resolve) => {
    void engine.startRun({ campaign: "bristol-mot-garages", resume: false }, (event) => {
      events.push(event);
      if (event.type === "failed" || event.type === "finished") resolve();
    });
  });
  await ended;
  const last = events.at(-1);
  assert.equal(last.type, "failed");
  assert.equal(last.status.state, "failed");
  assert.equal(last.error.kind, "environment");
  assert.equal(events.filter((e) => e.type === "failed").length, 1);
  assert.ok(events.some((e) => e.type === "progress" && e.stage === "enrich"));
});

test("a saved key never comes back: the status holds no value", async () => {
  const engine = createMockEngine({ speed: 0 });
  const status = await engine.saveKey("opencorporates_token", "made-up-token-000");
  assert.deepEqual(Object.keys(status).sort(), ["inUse", "name", "saved", "savedAt"]);
  assert.ok(!JSON.stringify(await engine.listKeys()).includes("made-up-token-000"));
});

/* ---- rulings 15 and 16 of 2026-11-12, and About.licence null (src/follow.ts) ---- */
import { keyBadge, keyFieldProblem, keyInUse, licenceLine, planFigures } from "../src/follow.ts";

test("ruling 15: a null estimate reads 'up to the cap' with no time; a count, a zero included, is shown", async () => {
  const draft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", offer: "x", sicCodes: [], maxLeads: 80 };
  const followUp = await createMockEngine({ speed: 0 }).createCampaign(draft);
  assert.equal(followUp.estimatedBusinesses, null);
  const fig = planFigures(followUp, "dvsa", 80);
  assert.equal(fig.counted, false);
  assert.equal(fig.line, "Up to 80 businesses; this register is not counted before the run.");
  assert.deepEqual(planFigures({ ...followUp, estimatedBusinesses: 120, estimatedSites: 77, estimatedMinutes: 5 }, "dvsa", 50),
    { counted: true, businesses: 120, sites: 77, minutes: 5 });
  // no tolerance for an older engine: 0, 0, 0 is a count of zero, shown as such
  assert.deepEqual(planFigures({ ...followUp, estimatedBusinesses: 0, estimatedSites: 0, estimatedMinutes: 0 }, "companies_house", 50),
    { counted: true, businesses: 0, sites: 0, minutes: 0 });
});

test("ruling 16: saved and not in use reads as such, naming registry.keyring; save is refused on the field; remove works", async () => {
  const off = createMockEngine({ speed: 0, keyringOff: true });
  const ch = (await off.listKeys()).find((k) => k.name === "companies_house_key");
  assert.equal(ch.saved, true);
  assert.equal(ch.inUse, false);
  const b = keyBadge(ch);
  assert.equal(b.text, "Saved, not in use");
  assert.match(b.note, /^Saved, but this workspace is set not to read the keyring: registry\.keyring in the workspace's leadforge\.yaml\.$/);
  const refused = await off.saveKey("opencorporates_token", "made-up").catch((e) => e);
  assert.equal(refused.kind, "input");
  assert.match(keyFieldProblem(refused), /registry\.keyring/);
  assert.equal(keyFieldProblem({ kind: "keyring", message: "x", details: [] }), null, "other refusals stay a banner");
  assert.equal((await off.removeKey("companies_house_key")).saved, false, "remove always works");
  // saved and in use (the workspace reads the keyring)
  const on = createMockEngine({ speed: 0 });
  const saved = (await on.listKeys()).find((k) => k.saved);
  assert.equal(saved.inUse, true);
  assert.equal(keyInUse(saved), true);
  assert.equal(keyBadge(saved).text, "Saved");
  // `inUse` is never inferred: the engine's false is not in use, even for a saved key
  assert.equal(keyInUse({ name: "companies_house_key", saved: true, savedAt: null, inUse: false }), false);
  assert.equal(keyInUse({ name: "companies_house_key", saved: false, savedAt: null, inUse: false }), false);
});

test("About.licence null: the screen says the notices were not found, never an empty line", async () => {
  const about = await createMockEngine({ speed: 0, noLicence: true }).about();
  assert.equal(about.licence, null);
  assert.deepEqual(about.licences, []);
  assert.equal(licenceLine(about), "The licence notices were not found in this installation.");
  assert.equal(licenceLine({ ...about, licence: "MIT" }), "MIT");
});

test("made-up data only: every domain ends in .example and every phone is in a drama range", async () => {
  const engine = createMockEngine({ speed: 0 });
  const { people } = await engine.listPeople({ search: "", limit: 100 });
  assert.ok(people.length > 0);
  for (const p of people) {
    assert.match(p.domain, /\.example$/);
    if (p.email) assert.match(p.email, /@[a-z0-9-]+\.example$/);
    if (p.phone) assert.match(p.phone, /^(0117 496 0\d{3}|01632 960\d{3}|07700 900\d{3})$/);
  }
});
