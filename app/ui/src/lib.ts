import { useCallback, useEffect, useRef, useState } from "react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "3 Nov 2026": the same on every computer, whatever its region settings. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** What the screens say for a value the engine did not record: never an empty cell, a dash, or "Invalid Date". */
export const NOT_RECORDED = "not recorded";

/** A date, or "not recorded" for null, empty or anything that is not a date. */
export function formatDateOrNot(iso: string | null): string {
  if (iso === null || iso.trim() === "" || Number.isNaN(new Date(iso).getTime())) return NOT_RECORDED;
  return formatDate(iso);
}

/** A text the engine may not have recorded: the text, or "not recorded" for null or blank. */
export function textOrNot(value: string | null): string {
  return value === null || value.trim() === "" ? NOT_RECORDED : value;
}

/** The clean-up counts of a run, each only when the engine counted it; no line at all when it counted neither. */
export function cleanUpLine(counts: { purged: number | null; expiringIn30Days: number | null }): string | null {
  const parts: string[] = [];
  if (counts.purged !== null) parts.push(`${formatCount(counts.purged)} ${counts.purged === 1 ? "record" : "records"} deleted at the start`);
  if (counts.expiringIn30Days !== null) parts.push(`${formatCount(counts.expiringIn30Days)} ${counts.expiringIn30Days === 1 ? "expires" : "expire"} in the next 30 days`);
  return parts.length ? `Clean-up: ${parts.join(", ")}.` : null;
}

/** What names a run: the engine's campaign name, or the run id when the engine has none (null). */
export function runTitle(status: { campaign: string | null; runId: string }): string {
  return status.campaign !== null && status.campaign.trim() !== "" ? status.campaign : status.runId;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "not known yet";
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`;
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

export function formatCount(n: number): string {
  return n.toLocaleString("en-GB");
}

export type Loaded<T> =
  | { state: "loading"; data: null; error: null }
  | { state: "error"; data: null; error: unknown }
  | { state: "done"; data: T; error: null };

/** Runs one engine read and keeps its three states. `reload` runs it again; `set` replaces the data. */
export function useLoad<T>(read: () => Promise<T>, deps: readonly unknown[]): Loaded<T> & { reload: () => void; set: (data: T) => void } {
  const [value, setValue] = useState<Loaded<T>>({ state: "loading", data: null, error: null });
  const [turn, setTurn] = useState(0);
  const latest = useRef(0);
  useEffect(() => {
    const mine = ++latest.current;
    setValue({ state: "loading", data: null, error: null });
    read().then(
      (data) => { if (latest.current === mine) setValue({ state: "done", data, error: null }); },
      (error: unknown) => { if (latest.current === mine) setValue({ state: "error", data: null, error }); },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, turn]);
  const reload = useCallback(() => setTurn((t) => t + 1), []);
  const set = useCallback((data: T) => setValue({ state: "done", data, error: null }), []);
  return { ...value, reload, set };
}

/** One engine write and its states, for a button. */
export function useAction<A extends unknown[], R>(run: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<R | null>(null);
  const call = useCallback(async (...args: A): Promise<R | null> => {
    setBusy(true); setError(null);
    try {
      const r = await run(...args);
      setResult(r);
      return r;
    } catch (e) {
      setError(e);
      return null;
    } finally {
      setBusy(false);
    }
  }, [run]);
  const clear = useCallback(() => { setError(null); setResult(null); }, []);
  return { busy, error, result, call, clear };
}
