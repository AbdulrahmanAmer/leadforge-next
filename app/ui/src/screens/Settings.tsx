import { useState } from "react";
import type { Engine, Settings, SettingsPatch, SourceId } from "../engine.ts";
import type { AccentSetting, ThemeSetting } from "../prefs.ts";
import { WINDOW_VERSION } from "../version.ts";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, KeyValueList, Skeleton, SegmentedControl, Switch, cx } from "../components/ui";
import { Logo } from "../components/Logo";
import { useAction, useLoad } from "../lib";
import { licenceLine } from "../follow.ts";

const SOURCE_NAME: Record<SourceId, string> = { dvsa: "MOT test stations", companies_house: "Companies House" };

const ACCENTS: { id: AccentSetting; label: string }[] = [
  { id: "cobalt", label: "Cobalt" }, { id: "brass", label: "Brass" }, { id: "celadon", label: "Celadon" }, { id: "ember", label: "Ember" },
];

export function SettingsScreen({ engine, theme, accent, onTheme, onAccent, initialTab }: {
  engine: Engine; theme: ThemeSetting; accent: AccentSetting; onTheme: (t: ThemeSetting) => void; onAccent: (a: AccentSetting) => void;
  initialTab: "settings" | "about";
}) {
  const [tab, setTab] = useState<"settings" | "about">(initialTab);
  const settings = useLoad(() => engine.getSettings(), [engine]);
  const about = useLoad(() => engine.about(), [engine]);
  const save = useAction((patch: SettingsPatch) => engine.setSettings(patch));
  const [open, setOpen] = useState<string | null>(null);

  // theme and accent are the window's own (App keeps them in prefs.ts); only the engine's settings go to the engine
  const change = async (patch: SettingsPatch) => {
    const next = await save.call(patch);
    if (next) settings.set(next);
  };
  const s: Settings | null = settings.data;

  return (
    <div className="lf-screen lf-screen--narrow">
      <header className="lf-screen__head">
        <div><h1>Settings</h1><p>How the window looks, where the workspace is, and what LeadForge is built from.</p></div>
        <SegmentedControl label="Section" options={[{ id: "settings", label: "Settings" }, { id: "about", label: "About and licences" }]} value={tab} onChange={setTab} />
      </header>

      {tab === "settings" && (
        <>
          <Card label="Appearance">
            <CardHeader title="Appearance" />
            <div className="lf-setting">
              <div><h3>Theme</h3><p>System follows Windows.</p></div>
              <SegmentedControl label="Theme" value={theme} onChange={onTheme}
                options={[{ id: "light", label: "Light", icon: "sun" }, { id: "dark", label: "Dark", icon: "moon" }, { id: "system", label: "System" }]} />
            </div>
            <div className="lf-setting">
              <div><h3>Accent</h3><p>The one colour used for the main action and the current page.</p></div>
              <div className="lf-swatches" role="radiogroup" aria-label="Accent">
                {ACCENTS.map((a) => (
                  <button key={a.id} type="button" role="radio" aria-checked={accent === a.id} className={cx("lf-swatch", `lf-swatch--${a.id}`, accent === a.id && "is-active")} onClick={() => onAccent(a.id)}>
                    <span className="lf-swatch__dot" aria-hidden="true" />{a.label}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          <Card label="Workspace and sheet">
            <CardHeader title="Workspace and sheet" />
            {settings.state === "loading" && <Skeleton lines={4} label="Reading the settings" />}
            {settings.state === "error" && <ErrorBanner compact error={settings.error} onRetry={settings.reload} />}
            {s && (
              <>
                <div className="lf-setting">
                  <div><h3>Workspace folder</h3><p className="lf-mono">{s.workspace}</p></div>
                </div>
                <div className="lf-setting">
                  <div><h3>Registers switched on</h3><p>{s.sources.length ? s.sources.map((id) => SOURCE_NAME[id]).join(", ") : "None. No register is switched on for this workspace."}</p></div>
                </div>
                <div className="lf-setting">
                  <div><h3>Also write a CSV copy</h3><p>The same rows as the Excel sheet, for other programs.</p></div>
                  <Switch label="Also write a CSV copy" checked={s.sheetFormats.includes("csv")} onChange={(on) => void change({ sheetFormats: on ? ["xlsx", "csv"] : ["xlsx"] })} />
                </div>
                <div className="lf-setting">
                  <div><h3>Open the sheet when a run finishes</h3><p>In the program Windows uses for Excel files.</p></div>
                  <Switch label="Open the sheet when a run finishes" checked={s.openSheetWhenDone} onChange={(on) => void change({ openSheetWhenDone: on })} />
                </div>
                {save.error !== null && <ErrorBanner compact error={save.error} />}
              </>
            )}
          </Card>
        </>
      )}

      {tab === "about" && (
        <>
          <Card label="About" className="lf-about">
            <Logo size={64} tile />
            <div className="lf-about__text">
              <h2>LeadForge</h2>
              <p>Finds businesses in public registers, reads their own websites for contact details, and writes a sheet. The data stays on this computer.</p>
              {about.state === "error" && <ErrorBanner compact error={about.error} onRetry={about.reload} />}
              {/* the window's version is the build's own constant: it shows even when the engine does not answer */}
              <KeyValueList rows={[["Window", WINDOW_VERSION], ["Engine", about.data ? about.data.engineVersion : about.state === "loading" ? "asking the engine" : "not answered"], ...(about.data ? [["Licence", licenceLine(about.data)] as [string, string]] : [])]} />
            </div>
          </Card>
          <Card label="Licences" padding="none">
            <div className="lf-people__pad"><CardHeader title="Licences" detail="The software that ships inside LeadForge, with the notice each one asks for." /></div>
            {about.state === "loading" && <div className="lf-people__pad"><Skeleton lines={4} label="Loading the licences" /></div>}
            {about.data && about.data.licences.length === 0 && (about.data.licence === null
              ? <EmptyState icon="info" title="The licence notices were not found" detail="The engine did not find the notices file in this installation. The installer carries it; reinstalling LeadForge puts it back." />
              : <EmptyState icon="info" title="No notices in this build" detail="The installer adds the notices file. A development build has none." />)}
            {about.data && about.data.licences.length > 0 && (
              <ul className="lf-licences">
                {about.data.licences.map((l) => (
                  <li key={l.name}>
                    <div className="lf-licences__row">
                      <span className="lf-licences__name">{l.name} <span>{l.version}</span></span>
                      <span className="lf-licences__kind">{l.licence}</span>
                      <Button variant="ghost" size="sm" aria-expanded={open === l.name} onClick={() => setOpen(open === l.name ? null : l.name)}>{open === l.name ? "Hide the notice" : "Show the notice"}</Button>
                    </div>
                    {open === l.name && <p className="lf-licences__notice">{l.notice}</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
