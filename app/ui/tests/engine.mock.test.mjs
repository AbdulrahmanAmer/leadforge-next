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
  forgetPerson: (e) => e.forgetPerson("priya@harbourside-motors.example"),
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
  await assert.rejects(engine.forgetPerson("  "), (error) => error.action === "forgetPerson");
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
  assert.deepEqual(Object.keys(status).sort(), ["name", "saved", "savedAt"]);
  assert.ok(!JSON.stringify(await engine.listKeys()).includes("made-up-token-000"));
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
