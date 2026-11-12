/**
 * tauriEngine: the Engine that talks to the Rust shell. One `invoke` per action; the command names and
 * their argument and result types are the table in docs/window-actions.md. The shell starts the engine;
 * this file can start nothing, read no file and reach no network.
 *
 * A failed command rejects with a plain object `{ kind, message, details, next }` (the shell builds it
 * from the engine's exit code and digest line); it becomes an EngineError here.
 */
import { Channel, invoke } from "@tauri-apps/api/core";
import { EngineError } from "./engine.ts";
import type {
  About, ActionName, Campaign, CampaignDraft, CampaignPlan, Engine, ErrorKind, ForgetResult, KeyName, KeyStatus,
  PeoplePage, PeopleQuery, PurgeEverythingResult, PurgeReport, Retention, RunArgs, RunHandle, RunMessage, RunStatus,
  Settings, SettingsPatch, Sheet, SuppressKind, SuppressResult,
} from "./engine.ts";

/** The Tauri command behind each action. */
export const COMMANDS: Record<ActionName, string> = {
  createCampaign: "campaign_create",
  startRun: "run_start",
  stopRun: "run_stop",
  runStatus: "run_status",
  listCampaigns: "campaigns_list",
  exportSheet: "sheet_export",
  openSheet: "sheet_open",
  listPeople: "people_list",
  forgetPerson: "person_forget",
  suppressAddress: "address_suppress",
  purgeReport: "purge_report",
  purgeApply: "purge_apply",
  purgeEverything: "purge_everything",
  getRetention: "retention_get",
  setRetention: "retention_set",
  listKeys: "keys_list",
  saveKey: "key_save",
  removeKey: "key_remove",
  getSettings: "settings_get",
  setSettings: "settings_set",
  about: "about",
};

const KINDS: readonly ErrorKind[] = ["failed", "usage", "environment", "input", "source", "keyring", "missing"];

function toEngineError(action: ActionName, raw: unknown): EngineError {
  const o = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  const kind = KINDS.includes(o.kind as ErrorKind) ? (o.kind as ErrorKind) : "failed";
  const message = typeof o.message === "string" ? o.message : typeof raw === "string" ? raw : "The engine did not answer.";
  const details = Array.isArray(o.details) ? o.details.filter((d): d is string => typeof d === "string") : [];
  return new EngineError(action, kind, message, details, typeof o.next === "string" ? o.next : null);
}

async function call<T>(action: ActionName, args?: Record<string, unknown>): Promise<T> {
  try {
    return await invoke<T>(COMMANDS[action], args);
  } catch (raw) {
    throw toEngineError(action, raw);
  }
}

export const tauriEngine: Engine = {
  createCampaign: (draft: CampaignDraft) => call<CampaignPlan>("createCampaign", { draft }),
  startRun: (args: RunArgs, onEvent: (event: RunMessage) => void) => {
    // the engine's events, and the shell's one `stream-closed` when the stream ended without an end event
    const events = new Channel<RunMessage>();
    events.onmessage = onEvent;
    return call<RunHandle>("startRun", { args, events });
  },
  stopRun: (runId: string) => call<RunStatus>("stopRun", { runId }),
  runStatus: (runId?: string) => call<RunStatus | null>("runStatus", { runId: runId ?? null }),
  listCampaigns: () => call<Campaign[]>("listCampaigns"),
  exportSheet: (runId: string) => call<Sheet>("exportSheet", { runId }),
  openSheet: (path: string) => call<void>("openSheet", { path }),
  listPeople: (query: PeopleQuery) => call<PeoplePage>("listPeople", { query }),
  forgetPerson: (value: string) => call<ForgetResult>("forgetPerson", { value }),
  suppressAddress: (value: string, kind?: SuppressKind) => call<SuppressResult>("suppressAddress", { value, kind: kind ?? null }),
  purgeReport: () => call<PurgeReport>("purgeReport"),
  purgeApply: () => call<PurgeReport>("purgeApply"),
  purgeEverything: () => call<PurgeEverythingResult>("purgeEverything", { confirm: true }),
  getRetention: () => call<Retention>("getRetention"),
  setRetention: (months: number) => call<Retention>("setRetention", { months }),
  listKeys: () => call<KeyStatus[]>("listKeys"),
  saveKey: (name: KeyName, value: string) => call<KeyStatus>("saveKey", { name, value }),
  removeKey: (name: KeyName) => call<KeyStatus>("removeKey", { name }),
  getSettings: () => call<Settings>("getSettings"),
  setSettings: (patch: SettingsPatch) => call<Settings>("setSettings", { patch }),
  about: () => call<About>("about"),
};
