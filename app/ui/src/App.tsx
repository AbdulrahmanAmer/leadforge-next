import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import type { Engine } from "./engine.ts";
import { IDLE, isLive, reduceRun } from "./run.ts";
import { readLook, writeLook, type AccentSetting, type ThemeSetting } from "./prefs.ts";
import { Logo } from "./components/Logo";
import { SideRail, type RailItem } from "./components/ui";
import { Wall } from "./components/Wall";
import { NewCampaign } from "./screens/NewCampaign";
import { Run } from "./screens/Run";
import { Results } from "./screens/Results";
import { People } from "./screens/People";
import { Data } from "./screens/Data";
import { Keys } from "./screens/Keys";
import { SettingsScreen } from "./screens/Settings";

export type ScreenId = "campaign" | "run" | "results" | "people" | "data" | "keys" | "settings";
export const SCREENS: readonly ScreenId[] = ["campaign", "run", "results", "people", "data", "keys", "settings"];

/** What a render or a development session asks for at start. Never set inside the shell. */
export interface Scenario {
  screen: ScreenId;
  theme: "light" | "dark" | null;
  accent: AccentSetting | null;
  /** Starts a run at once, so the Run screen can be seen in each of its states. */
  run: boolean;
  /** Asks for the plan at once, with the form filled in. */
  plan: boolean;
  /** Opens one confirmation: forget, suppress, purge, everything. */
  dialog: string | null;
  /** Renders only: how the New campaign form is pre-filled (see main.tsx). */
  draft: string | null;
}

/* ------------------------------------------------------------- the run view (run.ts) */
export type { RunView, StageView } from "./run.ts";

const RAIL: readonly RailItem<ScreenId>[] = [
  { id: "campaign", icon: "campaign", label: "Campaign" },
  { id: "run", icon: "run", label: "Run" },
  { id: "results", icon: "results", label: "Results" },
  { id: "people", icon: "people", label: "People" },
  { id: "data", icon: "data", label: "Data" },
  { id: "keys", icon: "key", label: "Keys" },
  { id: "settings", icon: "settings", label: "Settings" },
];

function systemTheme(): "light" | "dark" {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function App({ engine, scenario }: { engine: Engine; scenario: Scenario | null }) {
  const [screen, setScreen] = useState<ScreenId>(scenario?.screen ?? "campaign");
  // the window's own look (prefs.ts: browser storage, defaults when it throws), unless a render asked for one
  const [theme, setTheme] = useState<ThemeSetting>(() => scenario?.theme ?? readLook().theme);
  const [accent, setAccent] = useState<AccentSetting>(() => scenario?.accent ?? readLook().accent);
  const [run, dispatch] = useReducer(reduceRun, IDLE);

  const changeTheme = useCallback((next: ThemeSetting) => { setTheme(next); writeLook({ theme: next, accent }); }, [accent]);
  const changeAccent = useCallback((next: AccentSetting) => { setAccent(next); writeLook({ theme, accent: next }); }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme === "system" ? systemTheme() : theme;
    root.dataset.accent = accent;
  }, [theme, accent]);

  const startRun = useCallback((campaign: string, resume: boolean) => {
    dispatch({ type: "starting", campaign });
    setScreen("run");
    engine.startRun({ campaign, resume }, (event) => dispatch({ type: "event", event })).then(
      (handle) => dispatch({ type: "started", runId: handle.runId }),
      (error: unknown) => dispatch({ type: "refused", error }),
    );
  }, [engine]);

  const stopRun = useCallback(() => {
    if (!run.runId) return;
    dispatch({ type: "stopping" });
    engine.stopRun(run.runId).then(
      (status) => dispatch({ type: "stopped", status }),
      (error: unknown) => dispatch({ type: "stop-refused", error }),
    );
  }, [engine, run.runId]);

  // the stream closed without an end event: ask the engine once how the run stands, then show what it says
  const closedRunId = run.closed && run.runId ? run.runId : null;
  useEffect(() => {
    if (!closedRunId) return;
    engine.runStatus(closedRunId).then(
      (status) => dispatch({ type: "status-after-close", status }),
      () => dispatch({ type: "status-after-close", status: null }),
    );
  }, [engine, closedRunId]);

  useEffect(() => {
    if (scenario?.run) startRun("bristol-mot-garages", false);
  }, [scenario, startRun]);

  const rail = useMemo(
    () => RAIL.map((item) => (item.id === "run" && isLive(run.phase) ? { ...item, dot: "online" as const } : item)),
    [run.phase],
  );

  return (
    <div className="lf-app">
      <Wall />
      <aside className="lf-app__side">
        <div className="lf-app__brand"><Logo size={36} tile /></div>
        <SideRail items={rail} active={screen} onSelect={setScreen} />
      </aside>
      <main className="lf-app__main" data-screen={screen}>
        {screen === "campaign" && <NewCampaign engine={engine} run={run} onStart={(campaign) => startRun(campaign, false)} go={setScreen} autoPlan={scenario?.plan ?? false} draft={scenario?.draft ?? null} />}
        {screen === "run" && <Run run={run} onStop={stopRun} onResume={() => run.campaign && startRun(run.campaign, true)} onRetry={() => run.campaign && startRun(run.campaign, false)} go={setScreen} />}
        {screen === "results" && <Results engine={engine} go={setScreen} />}
        {screen === "people" && <People engine={engine} go={setScreen} openDialog={scenario?.dialog ?? null} />}
        {screen === "data" && <Data engine={engine} go={setScreen} openDialog={scenario?.dialog ?? null} />}
        {screen === "keys" && <Keys engine={engine} />}
        {screen === "settings" && <SettingsScreen engine={engine} theme={theme} accent={accent} onTheme={changeTheme} onAccent={changeAccent} initialTab={scenario?.dialog === "about" ? "about" : "settings"} />}
      </main>
    </div>
  );
}
