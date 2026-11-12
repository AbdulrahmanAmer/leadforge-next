/**
 * The report-first flow of Forget, kept out of the screen so Node tests it.
 *
 *   check(value)  -> the engine's dry run (`dry_run: true`): nothing is deleted;
 *                    "report" when it holds something, "nothing" when it holds nothing, "report-failed" when the dry run failed;
 *   confirm()     -> the ONE place the real call (`dry_run: false`) is made, and only from a state that shows a report;
 *                    "done" holds the engine's real result, "delete-failed" its error (the report stays, confirm can be tried again).
 *
 * A check that was overtaken by a newer one (another target chosen) is dropped: its answer never reaches the state.
 */
import type { Engine, ForgetResult } from "./engine.ts";

export type ForgetStep =
  | { step: "idle" }
  | { step: "checking"; value: string }
  | { step: "report"; value: string; report: ForgetResult }
  | { step: "nothing"; value: string; report: ForgetResult }
  | { step: "report-failed"; value: string; error: unknown }
  | { step: "deleting"; value: string; report: ForgetResult }
  | { step: "delete-failed"; value: string; report: ForgetResult; error: unknown }
  | { step: "done"; value: string; result: ForgetResult };

/** The engine holds nothing for the value: no rows and no file to remove or edit. */
export function holdsNothing(r: ForgetResult): boolean {
  return r.rows === 0 && r.filesRemoved === 0 && r.filesEdited === 0;
}

/** The sentence that says what a report holds, in the engine's own numbers. */
export function reportLines(r: ForgetResult): string[] {
  const rows = r.rows.toLocaleString("en-GB");
  return [
    `${rows} database ${r.rows === 1 ? "row" : "rows"}`,
    `${r.filesRemoved} ${r.filesRemoved === 1 ? "file" : "files"} that would be removed`,
    `${r.filesEdited} ${r.filesEdited === 1 ? "file" : "files"} that would be edited (lines taken out)`,
  ];
}

export class ForgetFlow {
  private current: ForgetStep = { step: "idle" };
  private turn = 0;
  private readonly engine: Engine;
  private readonly onChange: (s: ForgetStep) => void;

  constructor(engine: Engine, onChange: (s: ForgetStep) => void = () => {}) {
    this.engine = engine;
    this.onChange = onChange;
  }

  get state(): ForgetStep {
    return this.current;
  }

  private set(s: ForgetStep): void {
    this.current = s;
    this.onChange(s);
  }

  /** Back to the start; any answer still on its way is dropped. */
  reset(): void {
    this.turn++;
    this.set({ step: "idle" });
  }

  /** The dry run. Never deletes. */
  async check(value: string): Promise<void> {
    const mine = ++this.turn;
    this.set({ step: "checking", value });
    try {
      const report = await this.engine.forgetPerson(value, true);
      if (this.turn !== mine) return;
      this.set({ step: holdsNothing(report) ? "nothing" : "report", value, report });
    } catch (error) {
      if (this.turn !== mine) return;
      this.set({ step: "report-failed", value, error });
    }
  }

  /** The real call: only from a state that shows a report of what it will delete. Anything else is a no-op. */
  async confirm(): Promise<ForgetResult | null> {
    const s = this.current;
    if (s.step !== "report" && s.step !== "delete-failed") return null;
    const mine = ++this.turn;
    this.set({ step: "deleting", value: s.value, report: s.report });
    try {
      const result = await this.engine.forgetPerson(s.value, false);
      if (this.turn !== mine) return null;
      this.set({ step: "done", value: s.value, result });
      return result;
    } catch (error) {
      if (this.turn !== mine) return null;
      this.set({ step: "delete-failed", value: s.value, report: s.report, error });
      return null;
    }
  }
}
