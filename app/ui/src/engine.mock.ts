/**
 * mockEngine: the Engine with made-up data, for development, tests and renders.
 * Nothing here is real: business names are invented, every domain ends in `.example`, and phone numbers
 * come from the ranges Ofcom keeps for drama (01632 960xxx, 0117 496 0xxx, 07700 900xxx).
 * Each action waits about as long as the real one would, and each has an error path (`fail`).
 */
import { EngineError, STAGES } from "./engine.ts";
import type {
  About, ActionName, Campaign, CampaignDraft, CampaignPlan, Engine, ForgetKind, ForgetResult, KeyName, KeyStatus,
  PeoplePage, PeopleQuery, Person, PurgeEverythingResult, PurgeReport, Retention, RunArgs, RunEvent, RunHandle,
  RunMessage, RunStatus, Settings, SettingsPatch, Sheet, SourceId, StageId, SuppressKind, SuppressResult,
} from "./engine.ts";

/** The name that makes a run answer with the engine's "unknown" fields: shared with the stand-in. */
export const UNNAMED_RUN = "unnamed-run";

export interface MockOptions {
  /** Multiplies every delay. 0 answers at once (tests and renders). Default 1. */
  speed?: number;
  /** Actions that fail the way the real engine would. */
  fail?: readonly ActionName[] | "all";
  /** Actions that never answer: holds a screen in its loading state for a render. */
  hang?: readonly ActionName[] | "all";
  /** A workspace nobody has used yet. */
  empty?: boolean;
  /** A run stops sending events after this many (a render of a run in progress). */
  runFreezesAfter?: number;
  /** The run fails while visiting websites. */
  runFails?: boolean;
  /** After `stopRun` answers, the run writes `stopped` after this long (ms, before `speed`). Null: never (a render of
   *  the stopping state). Default 1500. */
  stopTakesMs?: number | null;
  /** The stream ends after this many events with the shell's `stream-closed` (reason `exit`) and no end event;
   *  `runStatus` then still says `running`, as a stale engine would. */
  runDiesAfter?: number;
  /** Actions the engine cannot do yet: they answer kind `missing`. */
  missing?: readonly ActionName[];
  /** The registers `settings_get` lists. Default both. */
  sources?: readonly SourceId[];
  /** The registers the engine really accepts. Default: the same as `sources` (a different list is a stale view). */
  configured?: readonly SourceId[];
  /** The run's statuses carry null campaign, done, purged and expiringIn30Days (also: campaign name "unnamed-run"). */
  runEndsNull?: boolean;
  /** The clock the mock reads. */
  now?: () => Date;
  /** A register campaign's plan: `null` (default, ruling 15: not estimated) or `zero` (today's engine 0.9.0: 0, 0, 0). */
  estimates?: "null" | "zero";
  /** The workspace does not read the keyring (`registry.keyring: false`): a saved key is not in use, `key_save` refuses. */
  keyringOff?: boolean;
  /** Key statuses without `inUse` (today's engine 0.9.0). */
  inUseMissing?: boolean;
  /** `about` finds no notices file: `licence` null, no licences. */
  noLicence?: boolean;
}

const FIXED_NOW = "2026-11-12T10:24:00Z";

/** The failure each action shows, copied from what the engine prints for that case. */
const FAILURES: Record<ActionName, [kind: EngineError["kind"], message: string, details: string[], next: string | null]> = {
  createCampaign: ["input", "The campaign is not complete.", ["target.geography.country: country is required", "target.categories: at least one kind of business"], "Fill in the marked fields and check the plan again."],
  startRun: ["environment", "The engine could not start the run.", ["The MOT test stations register file is missing from this workspace."], "Check the workspace folder in Settings, then try again."],
  stopRun: ["failed", "The run did not stop.", ["The engine process did not end within 10 seconds."], "Try again; the run keeps its place either way."],
  runStatus: ["usage", "The workspace settings file cannot be read.", ["leadforge.yaml invalid: ValidationError"], "Repair the value in Settings."],
  listCampaigns: ["missing", "The engine cannot list campaigns yet.", ["There is no engine command that lists the runs of a workspace."], null],
  exportSheet: ["input", "The sheet was not written.", ["no run found"], "Run the campaign first."],
  openSheet: ["failed", "Windows could not open the sheet.", ["No program is set to open .xlsx files."], "Open the exports folder and pick a program."],
  listPeople: ["missing", "The engine cannot list contacts yet.", ["There is no engine command that returns contacts with their source and date."], null],
  forgetPerson: ["input", "Nothing was changed.", ["This workspace was made by an older version and must be upgraded before anything can be deleted from it."], "nothing was changed"],
  suppressAddress: ["usage", "The address was not added.", ["empty value: nothing to suppress"], null],
  purgeReport: ["input", "The clean-up report could not be made.", ["This workspace is half upgraded; nothing was changed."], "nothing was changed"],
  purgeApply: ["input", "Nothing was deleted.", ["148 of 212 businesses are past the 12-month limit: more than half of the workspace, so nothing was deleted (a wrong clock looks like this)."], "Check the date on this computer, then try again."],
  purgeEverything: ["failed", "Not everything could be deleted.", ["A sheet in the exports folder is open in another program."], "Close the sheet and try again."],
  getRetention: ["usage", "The retention period could not be read.", ["leadforge.yaml invalid: ValidationError"], "Repair leadforge.yaml in the workspace folder, then try again."],
  setRetention: ["usage", "The retention period was not changed.", ["invalid value for retention.months: ValidationError"], "Choose 1 to 12 months."],
  listKeys: ["keyring", "The Windows keyring did not answer.", ["Credential Manager is not available for this account."], "Sign in to Windows again, then reopen this page."],
  saveKey: ["keyring", "The key was not saved.", ["The Windows keyring refused the entry."], "Nothing was stored. Try again."],
  removeKey: ["keyring", "The key was not removed.", ["The Windows keyring refused the change."], "Try again."],
  getSettings: ["failed", "The settings could not be read.", ["The settings file of the window is damaged."], "The defaults are in use."],
  setSettings: ["usage", "The setting was not saved.", ["invalid value for export.formats: ValidationError"], null],
  about: ["failed", "The engine did not answer.", ["The bundled engine did not start within 5 seconds."], "Reinstall LeadForge if this keeps happening."],
};

/** The title of a `missing` answer, for the actions a screen can meet it on. */
const MISSING: Partial<Record<ActionName, string>> = {
  listKeys: "Keys cannot be managed from this window yet.",
  saveKey: "The key was not saved: the engine cannot store keys yet.",
  removeKey: "The key was not removed: the engine cannot remove keys yet.",
};

const BUSINESSES: [name: string, domain: string, town: string][] = [
  ["Harbourside Motors", "harbourside-motors.example", "Bristol"],
  ["Clifton Down Garage", "cliftondowngarage.example", "Bristol"],
  ["Redcliffe MOT Centre", "redcliffe-mot.example", "Bristol"],
  ["Avon Gorge Autos", "avongorgeautos.example", "Bristol"],
  ["Bedminster Tyre and Test", "bedminstertest.example", "Bristol"],
  ["Kingswood Service Station", "kingswood-service.example", "Kingswood"],
  ["Fishponds Road Garage", "fishpondsroad.example", "Bristol"],
  ["Portway Vehicle Care", "portwayvehicle.example", "Avonmouth"],
  ["Stokes Croft Auto Repair", "stokescroftauto.example", "Bristol"],
  ["Severn View Motor Works", "severnview-motors.example", "Thornbury"],
];

const NAMES: [name: string, role: string][] = [
  ["Priya Nair", "Owner"], ["Tomasz Zielinski", "Workshop manager"], ["Aoife Brennan", "Director"],
  ["Daniel Okafor", "Service manager"], ["Megan Hartley", "Owner"], ["Yusuf Demir", "General manager"],
  ["Rhys Calloway", "Director"], ["Hannah Whitcombe", "Office manager"], ["Luca Marchetti", "Owner"],
  ["Sofia Lindqvist", "Service manager"], ["Callum Ferreira", "Director"], ["Nadia Rahman", "General manager"],
];

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

function makePeople(): Person[] {
  return NAMES.map(([name, role], i) => {
    const [business, domain] = BUSINESSES[i % BUSINESSES.length]!;
    const first = name.split(" ")[0]!.toLowerCase();
    const hasEmail = i % 5 !== 3;
    const hasPhone = i % 4 !== 2;
    const phone = i % 3 === 0 ? `0117 496 0${pad(100 + i * 37, 3)}` : i % 3 === 1 ? `01632 960${pad(100 + i * 53, 3)}` : `07700 900${pad(100 + i * 41, 3)}`;
    return {
      id: `p${i + 1}`,
      name, role, business, domain,
      email: hasEmail ? `${first}@${domain}` : null,
      phone: hasPhone ? phone : null,
      // the last two people carry the engine's "not recorded": one lacks the page, the last lacks all three
      source: i >= 10 ? null : `${domain}/${["contact", "about-us", "our-team", "contact-us"][i % 4]}`,
      foundAt: i === 11 ? null : `2026-${i < 7 ? "11" : "09"}-${pad(i < 7 ? 3 + i : 14 + (i - 7), 2)}`,
      campaign: i === 11 ? null : i < 7 ? "bristol-mot-garages" : "bath-tyre-fitters",
      suppressed: i === 9,
    };
  });
}

function makeSheet(runId: string, leads: number, writtenAt: string): Sheet {
  const dir = `leadforge_data\\exports\\${runId}`;
  return {
    runId, writtenAt, leads,
    tabs: [{ name: "Leads", rows: leads }, { name: "Drafts", rows: Math.round(leads * 0.62) }, { name: "Summary", rows: 14 }, { name: "About", rows: 9 }],
    files: [
      { kind: "xlsx", path: `${dir}\\leads.xlsx` },
      { kind: "csv", path: `${dir}\\leads.csv` },
      { kind: "report", path: `${dir}\\report.json` },
    ],
    highlights: [
      "No online booking on the site, phone only",
      "Site last changed more than two years ago",
      "Owner named on the contact page",
    ],
  };
}

function makeCampaigns(): Campaign[] {
  return [
    {
      runId: "r-20261103-a41c", name: "bristol-mot-garages", kinds: ["MOT garage"], places: ["Bristol"], source: "dvsa",
      state: "finished", stage: "export", startedAt: "2026-11-03T09:12:00Z", keptUntil: "2027-11-03",
      businesses: 212, withEmail: 164, withPhone: 201, tiers: { a: 38, b: 97, c: 77 },
      sheet: makeSheet("r-20261103-a41c", 212, "2026-11-03T09:58:00Z"),
    },
    {
      runId: "r-20261028-77be", name: "somerset-plumbing-firms", kinds: ["Plumbing and heating"], places: ["Taunton", "Yeovil"], source: "companies_house",
      state: "stopped", stage: "enrich", startedAt: "2026-10-28T14:40:00Z", keptUntil: "2027-10-28",
      businesses: 96, withEmail: 31, withPhone: 58, tiers: { a: 0, b: 0, c: 0 }, sheet: null,
    },
    {
      runId: "r-20260914-0d3f", name: "bath-tyre-fitters", kinds: ["Tyre fitter"], places: ["Bath"], source: "dvsa",
      state: "finished", stage: "export", startedAt: "2026-09-14T11:05:00Z", keptUntil: "2027-09-14",
      businesses: 64, withEmail: 47, withPhone: 60, tiers: { a: 9, b: 31, c: 24 },
      sheet: makeSheet("r-20260914-0d3f", 64, "2026-09-14T11:31:00Z"),
    },
    {
      // every nullable field null: the engine has no name, register or deletion day for this run
      runId: "r-20260802-3c1a", name: null, kinds: ["Roofing contractor"], places: ["Exeter"], source: null,
      state: "finished", stage: "export", startedAt: "2026-08-02T08:20:00Z", keptUntil: null,
      businesses: 41, withEmail: 22, withPhone: 38, tiers: { a: 4, b: 19, c: 18 }, sheet: makeSheet("r-20260802-3c1a", 41, "2026-08-02T08:44:00Z"),
    },
  ];
}

const STAGE_SUMMARY: Record<StageId, string> = {
  discover: "212 businesses from 48 searches",
  enrich: "204 websites read, 8 refused and left alone",
  label: "151 businesses with a named decision maker",
  score: "38 strong, 97 fair, 77 weak",
  draft: "131 draft notes for the sheet",
  export: "Sheet written: 212 rows",
};

/** The run as a list of timed events: the same every time, so renders and tests can count on it. */
function runScript(fails: boolean): { wait: number; event: Omit<Extract<RunEvent, { type: "progress" }>, "at"> | { type: "stage-done"; stage: StageId } | { type: "notice"; text: string } | { type: "fail" } }[] {
  const out: ReturnType<typeof runScript> = [];
  out.push({ wait: 300, event: { type: "notice", text: "Clean-up before the run: 4 businesses past the 12-month limit were deleted. 9 more expire in the next 30 days." } });
  const steps: [StageId, number, number, (i: number) => string][] = [
    ["discover", 48, 6, (i) => `${["Bristol", "Kingswood", "Avonmouth", "Thornbury"][i % 4]}: ${3 + (i * 7) % 9} MOT test stations`],
    ["enrich", 212, 12, (i) => { const b = BUSINESSES[i % BUSINESSES.length]!; return `${b[1]}: ${["1 email, 1 phone", "1 phone", "2 emails, 1 phone", "robots.txt forbids it, skipped"][i % 4]}`; }],
    ["label", 204, 34, (i) => `${BUSINESSES[i % BUSINESSES.length]![0]}: ${NAMES[i % NAMES.length]![1].toLowerCase()} named`],
    ["score", 212, 53, () => "Scoring against the campaign"],
    ["draft", 131, 44, (i) => `Draft note for ${BUSINESSES[i % BUSINESSES.length]![0]}`],
    ["export", 3, 1, (i) => ["leads.xlsx", "leads.csv", "report.json"][i % 3]!],
  ];
  for (const [stage, total, step, msg] of steps) {
    for (let done = 0, i = 0; done <= total; done = done === total ? total + 1 : Math.min(total, done + step), i++) {
      if (fails && stage === "enrich" && done > total * 0.4) {
        out.push({ wait: 500, event: { type: "fail" } });
        return out;
      }
      const left = total - done;
      out.push({ wait: stage === "enrich" ? 420 : 260, event: { type: "progress", stage, done, total, message: msg(i), etaSeconds: stage === "export" ? null : Math.round(left * (stage === "enrich" ? 1.9 : 0.6)) } });
    }
    out.push({ wait: 200, event: { type: "stage-done", stage } });
  }
  return out;
}

export function createMockEngine(options: MockOptions = {}): Engine {
  const speed = options.speed ?? 1;
  const now = options.now ?? (() => new Date(FIXED_NOW));
  const stamp = () => now().toISOString();

  // the made-up workspace this engine instance holds
  let people = options.empty ? [] : makePeople();
  let campaigns = options.empty ? [] : makeCampaigns();
  let suppressed = options.empty ? 0 : 23;
  let months = 12;
  let expired = options.empty ? 0 : 14;
  let total = options.empty ? 0 : 372;
  const listedSources: SourceId[] = [...(options.sources ?? ["dvsa", "companies_house"])];
  const configuredSources: SourceId[] = [...(options.configured ?? listedSources)];
  let settings: Settings = { workspace: "D:\\Leads\\west-country", sheetFormats: ["xlsx", "csv"], openSheetWhenDone: true, sources: listedSources };
  const keys: Record<KeyName, KeyStatus> = {
    companies_house_key: { name: "companies_house_key", saved: !options.empty, savedAt: options.empty ? null : "2026-11-03T08:50:00Z" },
    opencorporates_token: { name: "opencorporates_token", saved: false, savedAt: null },
  };
  // ruling 16: `inUse` is saved AND the workspace reads the keyring; today's engine (`inUseMissing`) has no such field
  const keyOut = (k: KeyStatus): KeyStatus => {
    const { inUse: _drop, ...plain } = k;
    return options.inUseMissing ? { ...plain } : { ...plain, inUse: k.saved && !options.keyringOff };
  };
  let run: { status: RunStatus; stopped: boolean; unknown: boolean; onEvent: (event: RunMessage) => void } | null = null;
  /** A status the way the engine sends it when it does not know: campaign, done and the clean-up counts null. */
  const shown = (status: RunStatus, unknown: boolean): RunStatus =>
    unknown ? { ...status, campaign: null, done: null, counts: { ...status.counts, purged: null, expiringIn30Days: null } } : { ...status, counts: { ...status.counts } };

  const sleep = (ms: number) => (speed === 0 ? Promise.resolve() : new Promise<void>((r) => setTimeout(r, ms * speed)));
  const listed = (set: MockOptions["fail"], action: ActionName) => set === "all" || (set ?? []).includes(action);

  /** Every action goes through here: the delay, then the hang or the planted failure. */
  async function begin(action: ActionName, ms: number): Promise<void> {
    if (listed(options.hang, action)) await new Promise<never>(() => {});
    await sleep(ms);
    if (listed(options.missing, action)) {
      // no new error kind: a command the engine cannot do yet is `missing`, with the window command named
      throw new EngineError(action, "missing", MISSING[action] ?? "The engine cannot do this yet.", [`The engine has no command for this yet.`], null);
    }
    if (listed(options.fail, action)) {
      const [kind, message, details, next] = FAILURES[action];
      throw new EngineError(action, kind, message, details, next);
    }
  }

  function purgeState(state: PurgeReport["state"], deleted: number): PurgeReport {
    return { state, months, total, expired, expiringIn30Days: options.empty ? 0 : 9, deleted, armed: true, suppressed };
  }

  return {
    async createCampaign(draft: CampaignDraft): Promise<CampaignPlan> {
      await begin("createCampaign", 900);
      const problems: string[] = [];
      if (!draft.kinds.some((k) => k.trim())) problems.push("target.categories: at least one kind of business");
      if (!draft.places.some((p) => p.trim())) problems.push("target.geography.areas: at least one place");
      if (!draft.country.trim()) problems.push("target.geography.country: country is required");
      if (!(draft.maxLeads >= 1)) problems.push("caps.max_leads: must be 1 or more");
      // the three refusals of the seam decisions (each names its field; the shape is the engine's `input`)
      if (!draft.offer || !draft.offer.trim()) problems.push("offer: say in a line or two what you offer these businesses");
      if (draft.source === "companies_house" && !(draft.sicCodes ?? []).some((c) => c.trim())) problems.push("sicCodes: at least one SIC code is needed for Companies House");
      if (!configuredSources.includes(draft.source)) {
        const names = configuredSources.length ? configuredSources.join(", ") : "no register";
        throw new EngineError("createCampaign", "input", "The campaign is not complete.", [...problems, `source: ${draft.source} is not switched on`], `this workspace is configured for ${names}`);
      }
      if (problems.length) throw new EngineError("createCampaign", "input", "The campaign is not complete.", problems, "Fill in the marked fields and check the plan again.");
      const searches = draft.kinds.length * draft.places.length * 12;
      const slug = `${draft.places[0]}-${draft.kinds[0]}s`.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      // every source the window offers is a register, which the engine does not count before the run (ruling 15)
      const est = options.estimates === "zero" ? 0 : null;
      return {
        campaign: slug, searches, estimatedBusinesses: est, estimatedSites: est, estimatedMinutes: est,
        warnings: [], retentionMonths: months,
      };
    },

    async startRun(args: RunArgs, onEvent: (event: RunMessage) => void): Promise<RunHandle> {
      await begin("startRun", 700);
      const runId = "r-20261112-5e90";
      const status: RunStatus = {
        runId, campaign: args.campaign, state: "running", stage: "discover", done: 0, total: null, etaSeconds: null,
        counts: { businesses: 0, contacts: 0, purged: 4, expiringIn30Days: 9 }, startedAt: stamp(), reason: null,
      };
      const unknown = options.runEndsNull === true || args.campaign === UNNAMED_RUN;
      const mine = { status, stopped: false, unknown, onEvent };
      run = mine;
      const script = runScript(options.runFails === true);
      void (async () => {
        let sent = 0;
        for (const { wait, event } of script) {
          if (options.runFreezesAfter !== undefined && sent >= options.runFreezesAfter) return;
          if (options.runDiesAfter !== undefined && sent >= options.runDiesAfter) {
            // the engine died: no end event; the shell says so once, and the stale status still says running
            await sleep(wait);
            onEvent({ type: "stream-closed", exitCode: 1, reason: "exit" });
            return;
          }
          await sleep(wait);
          if (mine.stopped) return;
          sent++;
          if (event.type === "progress") {
            status.stage = event.stage; status.done = event.done; status.total = event.total; status.etaSeconds = event.etaSeconds;
            if (event.stage === "discover") status.counts.businesses = Math.round((event.done / 48) * 212);
            if (event.stage === "enrich") status.counts.contacts = Math.round((event.done / 212) * 318);
            onEvent({ ...event, at: stamp() });
          } else if (event.type === "stage-done") {
            onEvent({ type: "stage-done", stage: event.stage, summary: STAGE_SUMMARY[event.stage], at: stamp() });
          } else if (event.type === "notice") {
            onEvent({ type: "notice", text: event.text, at: stamp() });
          } else {
            status.state = "failed";
            status.reason = "This computer went offline while the websites were being read.";
            onEvent({ type: "failed", status: shown(status, unknown), error: { kind: "environment", message: status.reason, details: ["Five requests in a row got no answer.", "What was found so far is kept; the run can continue from this stage."] } });
            return;
          }
        }
        status.state = "finished";
        status.stage = STAGES[STAGES.length - 1]!;
        campaigns = [{
          runId, name: args.campaign, kinds: ["MOT garage"], places: ["Bristol"], source: "dvsa", state: "finished", stage: "export",
          startedAt: status.startedAt, keptUntil: "2027-11-12", businesses: 212, withEmail: 164, withPhone: 201,
          tiers: { a: 38, b: 97, c: 77 }, sheet: makeSheet(runId, 212, stamp()),
        }, ...campaigns];
        onEvent({ type: "finished", status: shown(status, unknown) });
      })();
      return { runId };
    },

    async stopRun(runId: string): Promise<RunStatus> {
      await begin("stopRun", 600);
      if (!run || run.status.runId !== runId || run.status.state !== "running") {
        throw new EngineError("stopRun", "input", "There is no run to stop.", ["No engine process is running for this workspace."], null);
      }
      // the answer comes at once; the run finishes the business it is on and then writes its own `stopped`
      const mine = run;
      mine.stopped = true;
      const takes = options.stopTakesMs === undefined ? 1500 : options.stopTakesMs;
      if (takes !== null) {
        void sleep(takes).then(() => {
          mine.status.state = "stopped";
          mine.onEvent({ type: "stopped", status: shown(mine.status, mine.unknown) });
        });
      }
      return { ...shown(mine.status, mine.unknown), state: "stopped" };
    },

    async runStatus(runId?: string): Promise<RunStatus | null> {
      await begin("runStatus", 250);
      if (run && (!runId || run.status.runId === runId)) return shown(run.status, run.unknown);
      return null;
    },

    async listCampaigns(): Promise<Campaign[]> {
      await begin("listCampaigns", 500);
      return campaigns.map((c) => ({ ...c }));
    },

    async exportSheet(runId: string): Promise<Sheet> {
      await begin("exportSheet", 1400);
      const c = campaigns.find((x) => x.runId === runId);
      if (!c) throw new EngineError("exportSheet", "input", "The sheet was not written.", ["no run found"], "Run the campaign first.");
      c.sheet = makeSheet(runId, c.businesses, stamp());
      return c.sheet;
    },

    async openSheet(path: string): Promise<void> {
      await begin("openSheet", 300);
      if (!/\\exports\\/.test(path)) throw new EngineError("openSheet", "usage", "That file is not a sheet of this workspace.", ["Only files in the exports folder can be opened."], null);
    },

    async listPeople(query: PeopleQuery): Promise<PeoplePage> {
      await begin("listPeople", 450);
      const q = query.search.trim().toLowerCase();
      const hit = q ? people.filter((p) => [p.name, p.email ?? "", p.domain, p.business, p.phone ?? ""].some((v) => v.toLowerCase().includes(q))) : people;
      return { people: hit.slice(0, query.limit).map((p) => ({ ...p })), total: people.length, matching: hit.length };
    },

    async forgetPerson(value: string): Promise<ForgetResult> {
      await begin("forgetPerson", 1600);
      const v = value.trim().toLowerCase();
      if (!v) throw new EngineError("forgetPerson", "usage", "Nothing was changed.", ["Give an email address, a domain or a name."], "nothing was changed");
      const kind: ForgetKind = v.includes("@") ? "email" : /^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(v) ? "domain" : "name";
      const gone = people.filter((p) => (kind === "email" ? p.email?.toLowerCase() === v : kind === "domain" ? p.domain === v : p.name.toLowerCase() === v));
      people = people.filter((p) => !gone.includes(p));
      suppressed += 1;
      return {
        kind, value: value.trim(), rows: gone.length * 7, filesRemoved: gone.length ? 2 : 0, filesEdited: gone.length ? 3 : 0,
        warnings: ["Sheets already handed out, or written outside this folder, cannot be reached from here."],
      };
    },

    async suppressAddress(value: string, kind?: SuppressKind): Promise<SuppressResult> {
      await begin("suppressAddress", 500);
      const v = value.trim().toLowerCase();
      if (!v) throw new EngineError("suppressAddress", "usage", "The address was not added.", ["empty value: nothing to suppress"], null);
      const k: SuppressKind = kind ?? (v.includes("@") ? "email" : "domain");
      people = people.map((p) => ((k === "email" ? p.email?.toLowerCase() === v : p.domain === v) ? { ...p, suppressed: true } : p));
      suppressed += 1;
      return { kind: k, value: value.trim(), suppressed };
    },

    async purgeReport(): Promise<PurgeReport> {
      await begin("purgeReport", 700);
      return purgeState(options.empty ? "no_workspace" : "report", 0);
    },

    async purgeApply(): Promise<PurgeReport> {
      await begin("purgeApply", 1800);
      const deleted = expired;
      total -= deleted;
      expired = 0;
      return purgeState("purged", deleted);
    },

    async purgeEverything(): Promise<PurgeEverythingResult> {
      await begin("purgeEverything", 2200);
      const filesRemoved = options.empty ? 0 : 1846;
      people = []; campaigns = []; total = 0; expired = 0;
      return { filesRemoved };
    },

    async getRetention(): Promise<Retention> {
      await begin("getRetention", 250);
      return { months, min: 1, max: 12 };
    },

    async setRetention(value: number): Promise<Retention> {
      await begin("setRetention", 500);
      if (!Number.isInteger(value) || value < 1 || value > 12) {
        throw new EngineError("setRetention", "usage", "The retention period was not changed.", ["invalid value for retention.months: ValidationError"], "Choose 1 to 12 months.");
      }
      months = value;
      return { months, min: 1, max: 12 };
    },

    async listKeys(): Promise<KeyStatus[]> {
      await begin("listKeys", 350);
      return Object.values(keys).map(keyOut);
    },

    async saveKey(name: KeyName, value: string): Promise<KeyStatus> {
      await begin("saveKey", 600);
      if (!value.trim()) throw new EngineError("saveKey", "usage", "The key was not saved.", ["The key is empty."], null);
      if (options.keyringOff) {
        throw new EngineError("saveKey", "input", "The key was not saved: this workspace is set not to read the keyring.",
          ["registry.keyring: false in this workspace's leadforge.yaml, so the engine would not use a saved key"], "Set registry.keyring to true in leadforge.yaml, then save the key again.");
      }
      // the value is dropped here on purpose: nothing keeps it, nothing returns it
      keys[name] = { name, saved: true, savedAt: stamp() };
      return keyOut(keys[name]);
    },

    async removeKey(name: KeyName): Promise<KeyStatus> {
      await begin("removeKey", 400);
      // remove always works, whatever the keyring switch says
      keys[name] = { name, saved: false, savedAt: null };
      return keyOut(keys[name]);
    },

    async getSettings(): Promise<Settings> {
      await begin("getSettings", 150);
      return { ...settings, sources: [...settings.sources] };
    },

    async setSettings(patch: SettingsPatch): Promise<Settings> {
      await begin("setSettings", 300);
      // the engine's settings only: theme and accent are the window's own and never reach here
      const known = ["sheetFormats", "openSheetWhenDone"];
      const stray = Object.keys(patch).filter((k) => !known.includes(k));
      if (stray.length) throw new EngineError("setSettings", "usage", "The setting was not saved.", stray.map((k) => `unknown setting: ${k}`), null);
      if (patch.sheetFormats && patch.sheetFormats.length === 0) {
        throw new EngineError("setSettings", "usage", "The setting was not saved.", ["Keep at least one sheet format."], null);
      }
      settings = { ...settings, ...patch };
      return { ...settings, sources: [...settings.sources] };
    },

    async about(): Promise<About> {
      await begin("about", 400);
      return {
        engineVersion: "0.9.0", licence: options.noLicence ? null : "MIT",
        licences: options.empty || options.noLicence ? [] : [
          { name: "React", version: "19.3.1", licence: "MIT", notice: "Copyright (c) Meta Platforms, Inc. and affiliates. Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction." },
          { name: "Tauri", version: "2.x", licence: "Apache-2.0 OR MIT", notice: "Copyright (c) The Tauri Programme within The Commons Conservancy. Licensed under Apache-2.0 or MIT, at your option." },
          { name: "Python", version: "3.12", licence: "PSF-2.0", notice: "Copyright (c) Python Software Foundation. Licensed under the Python Software Foundation License Version 2." },
          { name: "openpyxl", version: "3.1", licence: "MIT", notice: "Copyright (c) 2010 openpyxl. Permission is hereby granted, free of charge, to any person obtaining a copy of this software." },
          { name: "pydantic", version: "2.x", licence: "MIT", notice: "Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors." },
        ],
      };
    },
  };
}

export const mockEngine: Engine = createMockEngine();
