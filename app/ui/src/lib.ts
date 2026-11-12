import { useCallback, useEffect, useRef, useState } from "react";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "3 Nov 2026": the same on every computer, whatever its region settings. */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
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
