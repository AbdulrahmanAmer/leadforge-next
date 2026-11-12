/**
 * What the screens show for the two rulings made after the engine's window commands were merged (2026-11-12),
 * kept out of the screens so Node tests it. The screens must work with today's engine (0.9.0) and with its
 * follow-up (slice/L11a-follow); each "TIGHTEN LATER" line goes once the follow-up is on master.
 */
import type { About, CampaignPlan, KeyStatus, SourceId } from "./engine.ts";

/** The plan card's figures. `counted: false`: the register is not counted before the run. */
export type PlanFigures =
  | { counted: true; businesses: number; sites: number; minutes: number }
  | { counted: false; upTo: number; line: string };

const REGISTERS: readonly SourceId[] = ["dvsa", "companies_house"];

/**
 * Ruling 15: an estimate of null means "not estimated". TIGHTEN LATER: today's engine answers 0 for all three on a
 * register campaign; until the follow-up lands, a register campaign whose three estimates are all 0 reads the same.
 */
export function planFigures(plan: CampaignPlan, source: SourceId, cap: number): PlanFigures {
  const b = plan.estimatedBusinesses, s = plan.estimatedSites, m = plan.estimatedMinutes;
  const notEstimated = b === null || s === null || m === null
    || (REGISTERS.includes(source) && b === 0 && s === 0 && m === 0);
  if (notEstimated) {
    return { counted: false, upTo: cap, line: `Up to ${cap} businesses; this register is not counted before the run.` };
  }
  return { counted: true, businesses: b, sites: s, minutes: m };
}

/** Where a workspace says whether the engine reads the keyring. */
export const KEYRING_SWITCH = "registry.keyring";

/** Ruling 16. TIGHTEN LATER: `inUse` missing (today's engine) reads as true. */
export function keyInUse(k: KeyStatus): boolean {
  return k.saved && k.inUse !== false;
}

export type KeyBadge = { tone: "success" | "warn" | "neutral"; text: string; note: string | null };

export function keyBadge(k: KeyStatus): KeyBadge {
  if (!k.saved) return { tone: "neutral", text: "Not set", note: null };
  if (keyInUse(k)) return { tone: "success", text: "Saved", note: null };
  return {
    tone: "warn",
    text: "Saved, not in use",
    note: `Saved, but this workspace is set not to read the keyring: ${KEYRING_SWITCH} in the workspace's leadforge.yaml.`,
  };
}

/** A `key_save` refusal that belongs on the key field: kind `input` naming `registry.keyring`. */
export function keyFieldProblem(error: unknown): string | null {
  const e = error as { kind?: string; message?: string; details?: string[] } | null;
  if (!e || e.kind !== "input") return null;
  const said = [e.message ?? "", ...(e.details ?? [])];
  if (!said.some((t) => t.includes(KEYRING_SWITCH))) return null;
  return said.filter(Boolean).join(" ");
}

/** About: the project's licence line, or what to say when the notices were not found. */
export function licenceLine(about: About): string {
  return about.licence ?? "The licence notices were not found in this installation.";
}
