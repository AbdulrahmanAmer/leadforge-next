import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/components.css";
import "./styles/app.css";
import { App, SCREENS, type Scenario, type ScreenId } from "./App";
import type { Engine, SourceId } from "./engine.ts";
import { ACCENT_IDS, type AccentSetting } from "./prefs.ts";
import { createMockEngine, type MockOptions } from "./engine.mock.ts";
import { tauriEngine } from "./engine.tauri.ts";

/**
 * Inside the shell the screens get tauriEngine. Anywhere else (the Vite dev server, a render of the
 * build) they get the mock, and the address may ask for a state to look at:
 *   ?screen=people&theme=dark&accent=brass&mock=done|empty|loading|error&run=mid|done|fail&plan=1&dialog=forget
 *   (the made-up workspace always holds a person and a campaign whose nullable fields are all null)
 *   &runnull=1              a run whose end status has null campaign, done and counts (also: the campaign name "unnamed-run")
 *   &sources=dvsa,companies_house|dvsa|none   the registers `settings_get` lists
 *   &configured=dvsa        the registers the engine really accepts (differs from `sources`: a refused register)
 *   &draft=no-offer|ch|ch-no-sic|stale-source   the New campaign form pre-filled for a render
 *   &missing=keys           the key commands answer kind `missing`
 *   &estimates=zero         the plan's estimates are 0, 0, 0 (today's engine; the default is null: ruling 15)
 *   &keyring=off            the workspace does not read the keyring: a saved key is not in use, saving is refused (ruling 16)
 *   &inuse=missing          key statuses carry no `inUse` (today's engine)
 *   &licence=none           `about` found no notices file (`licence` null)
 */
function pick(): { engine: Engine; scenario: Scenario | null } {
  if ("__TAURI_INTERNALS__" in window) return { engine: tauriEngine, scenario: null };

  const q = new URLSearchParams(window.location.search);
  const asked = q.size > 0;
  const mock = q.get("mock") ?? "done";
  const runMode = q.get("run");
  const registers = (name: string): SourceId[] | undefined => {
    const v = q.get(name);
    if (v === null) return undefined;
    return v === "none" ? [] : v.split(",").filter((s): s is SourceId => s === "dvsa" || s === "companies_house");
  };
  // &run=stopping: the run is stopped at once and its end never comes (the stopping state);
  // &run=dies: the stream closes without an end event after 21 events (the "stopped without saying why" state)
  const options: MockOptions = {
    speed: asked ? 0 : 1,
    empty: mock === "empty",
    fail: mock === "error" ? "all" : undefined,
    hang: mock === "loading" ? "all" : undefined,
    missing: q.get("missing") === "keys" ? ["listKeys", "saveKey", "removeKey"] : undefined,
    sources: registers("sources"),
    configured: registers("configured"),
    runFreezesAfter: runMode === "mid" || runMode === "stopping" ? 21 : undefined,
    runFails: runMode === "fail",
    stopTakesMs: runMode === "stopping" ? null : undefined,
    runDiesAfter: runMode === "dies" ? 21 : undefined,
    runEndsNull: q.get("runnull") === "1",
    estimates: q.get("estimates") === "zero" ? "zero" : undefined,
    keyringOff: q.get("keyring") === "off",
    inUseMissing: q.get("inuse") === "missing",
    noLicence: q.get("licence") === "none",
  };
  const screen = q.get("screen") as ScreenId | null;
  const theme = q.get("theme");
  const accent = q.get("accent") as AccentSetting | null;
  const scenario: Scenario = {
    screen: screen && SCREENS.includes(screen) ? screen : "campaign",
    theme: theme === "light" || theme === "dark" ? theme : null,
    accent: accent && ACCENT_IDS.includes(accent) ? accent : null,
    run: runMode !== null,
    plan: q.get("plan") === "1",
    dialog: q.get("dialog"),
    draft: q.get("draft"),
  };
  return { engine: createMockEngine(options), scenario: asked ? scenario : null };
}

const { engine, scenario } = pick();
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App engine={engine} scenario={scenario} />
  </StrictMode>,
);
