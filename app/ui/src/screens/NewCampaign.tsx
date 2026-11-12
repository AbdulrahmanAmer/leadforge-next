import { useEffect, useRef, useState } from "react";
import type { CampaignDraft, CampaignPlan, Engine, SourceId } from "../engine.ts";
import { EngineError } from "../engine.ts";
import type { RunView, ScreenId } from "../App";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Field, KeyValueList, Readout, ReadoutGroup, SegmentedControl, Skeleton, StatusBanner, TextArea, TextInput, cx } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatCount, formatDuration, useAction, useLoad } from "../lib";

const SOURCES: Record<SourceId, { name: string }> = {
  dvsa: { name: "MOT test stations" },
  companies_house: { name: "Companies House" },
};

/** Said when `settings_get` lists no register. The engine's own `next` text is not part of that answer (see the slice file). */
const NO_SOURCE_NEXT = "Registers are switched on in the file leadforge.yaml in this workspace's folder: list one under discovery, providers (dvsa or companies_house), then open New campaign again.";

const EXAMPLE = {
  kinds: "MOT garage", places: "Bristol", offer: "Online booking for MOT tests and services, so a garage stops losing the calls it cannot take.",
  sic: "45200, 45111",
};

/** Renders only (`?draft=`): how the form is pre-filled, and whether the plan is asked for at once. */
const SCENES: Record<string, { source: SourceId | null; offer: boolean; sic: boolean; check: boolean }> = {
  "no-offer": { source: null, offer: false, sic: false, check: true },
  "ch": { source: "companies_house", offer: true, sic: true, check: false },
  "ch-no-sic": { source: "companies_house", offer: true, sic: false, check: true },
  "stale-source": { source: "companies_house", offer: true, sic: true, check: true },
};

/** The fields the engine names in a refusal; their problems are shown on the field, not twice in the banner. */
const FIELD_KEYS = ["target.categories", "target.geography.areas", "target.geography.country", "caps.max_leads", "offer", "sicCodes", "source"];

function split(text: string): string[] {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

export function NewCampaign({ engine, run, onStart, go, autoPlan, draft: sceneName }: {
  engine: Engine; run: RunView; onStart: (campaign: string) => void; go: (s: ScreenId) => void; autoPlan: boolean; draft: string | null;
}) {
  const scene = sceneName ? SCENES[sceneName] ?? null : null;
  const prefilled = autoPlan || scene !== null;
  const [kinds, setKinds] = useState(prefilled ? EXAMPLE.kinds : "");
  const [places, setPlaces] = useState(prefilled ? EXAMPLE.places : "");
  const [country, setCountry] = useState("GB");
  const [offer, setOffer] = useState(prefilled && (scene === null || scene.offer) ? EXAMPLE.offer : "");
  const [picked, setPicked] = useState<SourceId | null>(scene?.source ?? null);
  const [sic, setSic] = useState(scene?.sic ? EXAMPLE.sic : "");
  const [maxLeads, setMaxLeads] = useState("250");
  const settings = useLoad(() => engine.getSettings(), [engine]);
  const plan = useAction((d: CampaignDraft) => engine.createCampaign(d));
  const running = run.phase === "running" || run.phase === "starting";

  // the registers this workspace is configured for; the form offers those and no others
  const sources = settings.data?.sources ?? null;
  const source: SourceId | null = sources === null ? null : picked !== null && sources.includes(picked) ? picked : sources[0] ?? null;
  const askSic = source === "companies_house";

  const draft: CampaignDraft = {
    kinds: split(kinds), places: split(places), country: country.trim().toUpperCase(),
    source: source ?? "dvsa", offer: offer.trim(), sicCodes: askSic ? split(sic) : [], maxLeads: Number(maxLeads),
  };
  const check = () => { void plan.call(draft); };

  const asked = useRef(false);
  useEffect(() => {
    // once, for a render, as soon as the registers are known
    if ((autoPlan || scene?.check) && sources !== null && sources.length > 0 && !asked.current) { asked.current = true; check(); }
  }, [sources]); // eslint-disable-line react-hooks/exhaustive-deps

  const found = plan.error instanceof EngineError ? plan.error : null;
  const problems = found ? found.details : [];
  const problem = (key: string) => {
    const line = problems.find((p) => p.startsWith(`${key}:`));
    return line ? line.slice(line.indexOf(":") + 1).trim() : null;
  };
  const onFields = problems.filter((p) => FIELD_KEYS.some((key) => p.startsWith(`${key}:`)));
  // a refused register: the engine's reason and its `next` (which names the configured one) go on the field
  const sourceDetail = problem("source");
  const sourceNote = sourceDetail ? [sourceDetail, found?.next ? found.next.charAt(0).toUpperCase() + found.next.slice(1) : null].filter(Boolean).join(". ") : null;
  const banner = found && sourceDetail ? new EngineError(found.action, found.kind, found.message, found.details, null) : plan.error;
  const edited = () => { if (plan.result || plan.error) plan.clear(); };

  const none = settings.state === "done" && sources !== null && sources.length === 0;
  const canCheck = settings.state === "done" && !none;

  return (
    <div className="lf-screen">
      <header className="lf-screen__head">
        <div>
          <h1>New campaign</h1>
          <p>Name a kind of business and a place. You see the plan before anything is collected.</p>
        </div>
      </header>

      <div className="lf-grid lf-grid--form">
        <Card>
          {none ? (
            <EmptyState icon="info" title="No register is switched on" detail={`No register is switched on for this workspace. ${NO_SOURCE_NEXT}`} />
          ) : (
            <form className="lf-form" onSubmit={(e) => { e.preventDefault(); if (canCheck) check(); }}>
              <div className="lf-form__row">
                <Field inline label="Kind of business" hint="several: use commas" error={problem("target.categories")}>
                  {(id, note) => <TextInput id={id} aria-describedby={note} placeholder="MOT garage" value={kinds} onChange={(e) => { setKinds(e.target.value); edited(); }} />}
                </Field>
                <Field inline label="Stop after" hint="businesses" error={problem("caps.max_leads")}>
                  {(id, note) => <TextInput id={id} aria-describedby={note} className="ds-input lf-input--short" inputMode="numeric" value={maxLeads} onChange={(e) => { setMaxLeads(e.target.value.replace(/\D/g, "")); edited(); }} />}
                </Field>
              </div>
              <div className="lf-form__row">
                <Field inline label="Place" hint="towns, counties, postcodes" error={problem("target.geography.areas")}>
                  {(id, note) => <TextInput id={id} aria-describedby={note} placeholder="Bristol" value={places} onChange={(e) => { setPlaces(e.target.value); edited(); }} />}
                </Field>
                <Field inline label="Country" hint="two letters" error={problem("target.geography.country")}>
                  {(id, note) => <TextInput id={id} aria-describedby={note} className="ds-input lf-input--short" maxLength={2} value={country} onChange={(e) => { setCountry(e.target.value); edited(); }} />}
                </Field>
              </div>

              <Field inline label="What you offer" hint="to these businesses, in one or two lines" error={problem("offer")}>
                {(id, note) => <TextArea id={id} aria-describedby={note} placeholder="Online booking for MOT tests" value={offer} onChange={(e) => { setOffer(e.target.value); edited(); }} />}
              </Field>

              {settings.state === "loading" && <Skeleton lines={2} label="Reading which registers are switched on" />}
              {settings.state === "error" && <ErrorBanner compact error={settings.error} onRetry={settings.reload} />}
              {sources !== null && sources.length >= 1 && source !== null && (
                <div className={cx("lf-where", sourceNote && "is-invalid")}>
                  <div className="lf-where__row">
                    <span className="ds-field__label" id="lf-where-label">Where to look</span>
                    {sources.length === 1
                      /* one configured register is fixed text, not a picker */
                      ? <span className="lf-where__fixed" aria-labelledby="lf-where-label">{SOURCES[source].name}</span>
                      : <SegmentedControl label="Where to look" value={source} onChange={(id) => { setPicked(id); edited(); }} options={sources.map((id) => ({ id, label: SOURCES[id].name }))} />}
                  </div>
                  {sourceNote && <p className="ds-field__note" role="alert">{sourceNote}</p>}
                </div>
              )}

              {askSic && (
                <Field inline label="SIC codes" hint="several: use commas" error={problem("sicCodes")}>
                  {(id, note) => <TextInput id={id} aria-describedby={note} placeholder="45200, 45111" inputMode="numeric" value={sic} onChange={(e) => { setSic(e.target.value); edited(); }} />}
                </Field>
              )}

              <div className="lf-form__actions">
                <Button type="submit" variant={plan.result ? "soft" : "primary"} size="lg" busy={plan.busy} disabled={!canCheck}>{plan.busy ? "Checking the plan" : "Check the plan"}</Button>
              </div>
            </form>
          )}
        </Card>

        <Card className="lf-plan" label="The plan">
          {plan.busy && (
            <>
              <CardHeader title="The plan" detail="Asking the engine. Nothing is collected yet." />
              <Skeleton lines={5} label="Checking the plan" />
            </>
          )}
          {!plan.busy && plan.error !== null && (
            <>
              <CardHeader title="The plan" />
              <ErrorBanner error={banner} onRetry={onFields.length ? undefined : check} hide={onFields} />
            </>
          )}
          {!plan.busy && !plan.error && !plan.result && (
            <EmptyState icon="search" title="The plan appears here" detail="How many searches, about how long, and how many businesses at most. Nothing is collected until you start the run." />
          )}
          {!plan.busy && plan.result && <Plan plan={plan.result} running={running} onStart={() => onStart(plan.result!.campaign)} go={go} />}
        </Card>
      </div>
    </div>
  );
}

function Plan({ plan, running, onStart, go }: { plan: CampaignPlan; running: boolean; onStart: () => void; go: (s: ScreenId) => void }) {
  return (
    <>
      <CardHeader title="The plan" detail={<span className="lf-mono">{plan.campaign}</span>} />
      <ReadoutGroup>
        <Readout label="Businesses, at most" value={formatCount(plan.estimatedBusinesses)} />
        <Readout label="About" value={formatDuration(plan.estimatedMinutes * 60).replace(" min", "")} unit="min" />
      </ReadoutGroup>
      <KeyValueList rows={[
        ["Searches in the register", formatCount(plan.searches)],
        ["Websites to read", formatCount(plan.estimatedSites)],
        ["Kept for", `${plan.retentionMonths} months, then deleted`],
      ]} />
      {plan.warnings.map((w) => (
        <p key={w} className="lf-note lf-note--warn"><Icon name="info" size={16} />{w}</p>
      ))}
      <div className="lf-plan__actions">
        <Button variant="primary" size="lg" leadingIcon="play" onClick={onStart} disabled={running}>Start the run</Button>
        <Button variant="ghost" size="lg" onClick={() => go("data")}>Change how long it is kept</Button>
      </div>
      {running && <StatusBanner compact tone="neutral" title="A run is in progress" detail="One run at a time. Start this one when it has finished." />}
    </>
  );
}
