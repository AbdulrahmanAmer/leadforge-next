/**
 * The one seam between the screens and the engine.
 *
 * Every action a person can take in the window is one method here (docs/window-actions.md lists them
 * with the engine command each one runs). Screens import this file and nothing else: no Tauri, no fetch,
 * no file access. Two implementations:
 *   - mockEngine  (engine.mock.ts)   made-up data, used in development, tests and renders
 *   - tauriEngine (engine.tauri.ts)  calls the Rust shell with `invoke`; the shell starts the engine
 *
 * Only erasable TypeScript in the engine files: Node runs the tests on them directly.
 */

export const ACTIONS = [
  "createCampaign", "startRun", "stopRun", "runStatus", "listCampaigns", "exportSheet", "openSheet",
  "listPeople", "forgetPerson", "suppressAddress", "purgeReport", "purgeApply", "purgeEverything",
  "getRetention", "setRetention", "listKeys", "saveKey", "removeKey", "getSettings", "setSettings", "about",
] as const;
export type ActionName = (typeof ACTIONS)[number];

/** What went wrong, in the engine's own terms: its exit code and the warnings of its digest line. */
export type ErrorKind =
  | "failed"       // exit 1: the engine stopped unexpectedly
  | "usage"        // exit 2: a value the engine refused (or a broken leadforge.yaml)
  | "environment"  // exit 3: something on this computer is missing
  | "input"        // exit 4: the campaign or the workspace is not usable as it is
  | "source"       // exit 5: a register did not answer
  | "keyring"      // the shell could not reach the Windows keyring
  | "missing";     // the engine has no command for this yet

export class EngineError extends Error {
  action: ActionName;
  kind: ErrorKind;
  /** The engine's warnings, already plain sentences. */
  details: string[];
  /** What the engine suggests next, when it says. */
  next: string | null;

  constructor(action: ActionName, kind: ErrorKind, message: string, details: string[] = [], next: string | null = null) {
    super(message);
    this.name = "EngineError";
    this.action = action;
    this.kind = kind;
    this.details = details;
    this.next = next;
  }
}

/* ------------------------------------------------------------------ campaigns */

/** The two public registers the engine can search. */
export type SourceId = "dvsa" | "companies_house";

export interface CampaignDraft {
  /** Kinds of business, e.g. "MOT garage". At least one. */
  kinds: string[];
  /** Towns, counties or postcode areas. At least one. */
  places: string[];
  /** ISO country code; the engine requires it. */
  country: string;
  /** One of `Settings.sources`. The engine refuses (`input`, field `source`) one that is not configured. */
  source: SourceId;
  /** What the user offers these businesses, one or two lines. Required: an empty one is refused (`input`, field `offer`). */
  offer: string;
  /** SIC codes. Asked for, and required (`input`, field `sicCodes`), only when `source` is `companies_house`; `[]` otherwise. */
  sicCodes: string[];
  /** Stop after this many businesses. */
  maxLeads: number;
}

export interface CampaignPlan {
  campaign: string;
  searches: number;
  /** The three estimates. Null: not estimated (a register campaign: the engine does not count a register before the
   *  run; ruling 15 of 2026-11-12). The plan card then says "up to <the cap>" and shows no time. */
  estimatedBusinesses: number | null;
  estimatedSites: number | null;
  estimatedMinutes: number | null;
  /** Plain sentences from the engine, e.g. a plan much larger than the cap. */
  warnings: string[];
  retentionMonths: number;
}

export type StageId = "discover" | "enrich" | "label" | "score" | "draft" | "export";
export const STAGES: readonly StageId[] = ["discover", "enrich", "label", "score", "draft", "export"];

export type RunState = "running" | "finished" | "stopped" | "failed";

export interface RunArgs {
  campaign: string;
  /** Continue a stopped or failed run where it left off. */
  resume: boolean;
}

export interface RunCounts {
  businesses: number;
  contacts: number;
  /** Records the start-of-run clean-up deleted, and how many expire within 30 days. Null: the engine did not count. */
  purged: number | null;
  expiringIn30Days: number | null;
}

export interface RunStatus {
  runId: string;
  /** Null when the engine does not know the campaign's name; the screen shows the run id. */
  campaign: string | null;
  state: RunState;
  stage: StageId;
  /** Null when the engine cannot say how far the stage is; the screen shows an indeterminate bar. */
  done: number | null;
  total: number | null;
  etaSeconds: number | null;
  counts: RunCounts;
  startedAt: string;
  /** Set when state is "failed": the engine's reason. */
  reason: string | null;
}

/** The progress stream of one run. `progress` repeats many times; `finished`, `stopped` or `failed` ends it. */
export type RunEvent =
  | { type: "progress"; stage: StageId; done: number; total: number | null; message: string; etaSeconds: number | null; at: string }
  | { type: "stage-done"; stage: StageId; summary: string; at: string }
  | { type: "notice"; text: string; at: string }
  | { type: "finished"; status: RunStatus }
  | { type: "stopped"; status: RunStatus }
  | { type: "failed"; status: RunStatus; error: { kind: ErrorKind; message: string; details: string[] } };

/**
 * NOT an engine event: the shell's own last message on a run's channel. The Rust core sends exactly one when the
 * engine's stream ended without `finished`, `stopped` or `failed` (after the last relayed line; never after an end
 * event). `exitCode` is null when the core ended the process. `reason`: `exit` the engine ended by itself;
 * `ended-by-core` the core ended it (the wait after a stop ran out, or the window closed); `line-too-long` the
 * engine's last line was over the 64 KiB cap and was not relayed; `timeout` the run's 12-hour limit.
 * The Run screen then asks `runStatus` once (docs/window-actions.md, "The seam's contract").
 */
export interface StreamClosed {
  type: "stream-closed";
  exitCode: number | null;
  reason: "exit" | "ended-by-core" | "line-too-long" | "timeout";
}

/** What arrives on a run's channel: the engine's events, and at most one `stream-closed` from the shell. */
export type RunMessage = RunEvent | StreamClosed;

export interface RunHandle {
  runId: string;
}

export interface Campaign {
  runId: string;
  /** Null when the engine has none; the screen shows the run id. */
  name: string | null;
  kinds: string[];
  places: string[];
  /** Null when not recorded. */
  source: SourceId | null;
  state: RunState;
  stage: StageId;
  startedAt: string;
  /** The day the engine deletes what this campaign found. Null: the screen makes no claim about it. */
  keptUntil: string | null;
  businesses: number;
  withEmail: number;
  withPhone: number;
  tiers: { a: number; b: number; c: number };
  sheet: Sheet | null;
}

export interface SheetFile {
  kind: "xlsx" | "csv" | "report";
  /** As the engine printed it. Shown as text; only the shell can open it. */
  path: string;
}

export interface Sheet {
  runId: string;
  writtenAt: string;
  leads: number;
  tabs: { name: string; rows: number }[];
  files: SheetFile[];
  /** The engine's "why" lines for the best leads. */
  highlights: string[];
}

/* --------------------------------------------------------------------- people */

export interface Person {
  id: string;
  name: string;
  role: string;
  business: string;
  domain: string;
  email: string | null;
  phone: string | null;
  /** Where the detail was found (a page address, shown as text) and when. Null: shown as "not recorded". */
  source: string | null;
  foundAt: string | null;
  /** The campaign that found the person. Null: shown as "not recorded". */
  campaign: string | null;
  suppressed: boolean;
}

export interface PeopleQuery {
  search: string;
  limit: number;
}

export interface PeoplePage {
  people: Person[];
  total: number;
  matching: number;
}

export type ForgetKind = "email" | "domain" | "name";

export interface ForgetResult {
  kind: ForgetKind;
  value: string;
  rows: number;
  filesRemoved: number;
  filesEdited: number;
  /** What the engine could not reach, in its words. */
  warnings: string[];
}

export type SuppressKind = "email" | "domain";

export interface SuppressResult {
  kind: SuppressKind;
  value: string;
  /** How many entries the suppression list holds now. */
  suppressed: number;
}

/* -------------------------------------------------------- data and retention */

/** `armed: false` is a workspace before its first check: the first clean-up only reports. */
export interface PurgeReport {
  state: "report" | "armed" | "purged" | "no_workspace";
  months: number;
  total: number;
  expired: number;
  expiringIn30Days: number;
  deleted: number;
  armed: boolean;
  suppressed: number;
}

export interface PurgeEverythingResult {
  filesRemoved: number;
}

export interface Retention {
  months: number;
  /** The engine's limits: it can be shortened, never set above the maximum. */
  min: number;
  max: number;
}

/* ----------------------------------------------------------------------- keys */

export type KeyName = "companies_house_key" | "opencorporates_token";

/** A key's value never comes back from the shell: only whether one is saved, and since when. */
export interface KeyStatus {
  name: KeyName;
  saved: boolean;
  savedAt: string | null;
  /** Saved AND this workspace reads the keyring (`registry.keyring` in its leadforge.yaml; ruling 16 of 2026-11-12). Always present. */
  inUse: boolean;
}

/* ------------------------------------------------------------------- settings */

/** The engine's settings. The window's look (theme, accent) is not here: the window keeps it itself (prefs.ts). */
export interface Settings {
  /** The folder the engine works in. Changed through the shell's own folder dialog. */
  workspace: string;
  sheetFormats: ("xlsx" | "csv")[];
  openSheetWhenDone: boolean;
  /** The registers this workspace is configured for. The new-campaign form offers these and no others. */
  sources: SourceId[];
}

export type SettingsPatch = Partial<Pick<Settings, "sheetFormats" | "openSheetWhenDone">>;

export interface Licence {
  name: string;
  version: string;
  licence: string;
  /** The notice text that ships with the installer. */
  notice: string;
}

/** The engine's version and the licence notices. The window's own version is a build-time constant (version.ts). */
export interface About {
  engineVersion: string;
  /** Null: the engine did not find the notices file; the screen says so (never an empty box). */
  licence: string | null;
  licences: Licence[];
}

/* ----------------------------------------------------------------- the seam */

export interface Engine {
  /** New campaign: checks the answers and returns the plan. Nothing is collected yet. */
  createCampaign(draft: CampaignDraft): Promise<CampaignPlan>;
  /**
   * Run: starts the engine and streams its progress to `onEvent` until one of the three end events, or the shell's
   * `stream-closed` when the stream ended without one. A refused start rejects (and sends nothing to `onEvent`).
   */
  startRun(args: RunArgs, onEvent: (event: RunMessage) => void): Promise<RunHandle>;
  /** The clear stop. The run can be continued later with `resume`. */
  stopRun(runId: string): Promise<RunStatus>;
  /** The current or last run, or null when the workspace has none. */
  runStatus(runId?: string): Promise<RunStatus | null>;
  /** Results: every campaign of the workspace, newest first. */
  listCampaigns(): Promise<Campaign[]>;
  /** Writes the sheet of a run again (xlsx, csv, report). */
  exportSheet(runId: string): Promise<Sheet>;
  /** Asks the shell to open a sheet file in the program Windows uses for it. */
  openSheet(path: string): Promise<void>;
  /** People: the engine's named people, with an email or phone only where it was recorded as that person's. */
  listPeople(query: PeopleQuery): Promise<PeoplePage>;
  /** Forget: removes an email address, a domain or a name from the workspace and keeps them off new runs.
   *  `dryRun` true (sent as `dry_run`): the engine answers the same shape for what it WOULD delete and changes nothing.
   *  The People screen always asks with `dryRun` true first (src/forget.ts). */
  forgetPerson(value: string, dryRun: boolean): Promise<ForgetResult>;
  /** Suppress: the address or domain leaves every export and is not collected again. */
  suppressAddress(value: string, kind?: SuppressKind): Promise<SuppressResult>;
  /** What the next clean-up would delete. Changes nothing. */
  purgeReport(): Promise<PurgeReport>;
  /** Deletes what is past the retention limit. */
  purgeApply(): Promise<PurgeReport>;
  /** Deletes the whole workspace's data. */
  purgeEverything(): Promise<PurgeEverythingResult>;
  getRetention(): Promise<Retention>;
  setRetention(months: number): Promise<Retention>;
  listKeys(): Promise<KeyStatus[]>;
  /** Stores a key in the Windows keyring. The value is not returned and cannot be read back. */
  saveKey(name: KeyName, value: string): Promise<KeyStatus>;
  removeKey(name: KeyName): Promise<KeyStatus>;
  getSettings(): Promise<Settings>;
  setSettings(patch: SettingsPatch): Promise<Settings>;
  /** About: versions and the licence notices that ship with the installer. */
  about(): Promise<About>;
}
