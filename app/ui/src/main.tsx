import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/components.css";
import "./styles/app.css";
import { App, SCREENS, type Scenario, type ScreenId } from "./App";
import type { AccentSetting, Engine } from "./engine.ts";
import { createMockEngine, type MockOptions } from "./engine.mock.ts";
import { tauriEngine } from "./engine.tauri.ts";

/**
 * Inside the shell the screens get tauriEngine. Anywhere else (the Vite dev server, a render of the
 * build) they get the mock, and the address may ask for a state to look at:
 *   ?screen=people&theme=dark&accent=brass&mock=done|empty|loading|error&run=mid|done|fail&plan=1&dialog=forget
 */
function pick(): { engine: Engine; scenario: Scenario | null } {
  if ("__TAURI_INTERNALS__" in window) return { engine: tauriEngine, scenario: null };

  const q = new URLSearchParams(window.location.search);
  const asked = q.size > 0;
  const mock = q.get("mock") ?? "done";
  const runMode = q.get("run");
  const options: MockOptions = {
    speed: asked ? 0 : 1,
    empty: mock === "empty",
    fail: mock === "error" ? "all" : undefined,
    hang: mock === "loading" ? "all" : undefined,
    runFreezesAfter: runMode === "mid" ? 21 : undefined,
    runFails: runMode === "fail",
  };
  const screen = q.get("screen") as ScreenId | null;
  const theme = q.get("theme");
  const accent = q.get("accent") as AccentSetting | null;
  const scenario: Scenario = {
    screen: screen && SCREENS.includes(screen) ? screen : "campaign",
    theme: theme === "light" || theme === "dark" ? theme : null,
    accent: accent && ["cobalt", "brass", "celadon", "ember"].includes(accent) ? accent : null,
    run: runMode !== null,
    plan: q.get("plan") === "1",
    dialog: q.get("dialog"),
  };
  return { engine: createMockEngine(options), scenario: asked ? scenario : null };
}

const { engine, scenario } = pick();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App engine={engine} scenario={scenario} />
  </StrictMode>,
);
