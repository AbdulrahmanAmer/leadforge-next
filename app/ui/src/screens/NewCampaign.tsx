import { useEffect, useState } from "react";
import type { CampaignDraft, CampaignPlan, Engine, SourceId } from "../engine.ts";
import { EngineError } from "../engine.ts";
import type { RunView, ScreenId } from "../App";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Field, KeyValueList, Readout, ReadoutGroup, Skeleton, StatusBanner, TextInput, cx } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatCount, formatDuration, useAction } from "../lib";

const SOURCES: { id: SourceId; name: string; detail: string }[] = [
  { id: "dvsa", name: "MOT test stations", detail: "The DVSA register of active test stations. Garages only, Great Britain." },
  { id: "companies_house", name: "Companies House", detail: "Registered companies by kind of business. Needs your API key." },
];

const EXAMPLE: CampaignDraft = { kinds: ["MOT garage"], places: ["Bristol"], country: "GB", source: "dvsa", maxLeads: 250 };

function split(text: string): string[] {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

export function NewCampaign({ engine, run, onStart, go, autoPlan }: {
  engine: Engine; run: RunView; onStart: (campaign: string) => void; go: (s: ScreenId) => void; autoPlan: boolean;
}) {
  const [kinds, setKinds] = useState(autoPlan ? EXAMPLE.kinds.join(", ") : "");
  const [places, setPlaces] = useState(autoPlan ? EXAMPLE.places.join(", ") : "");
  const [country, setCountry] = useState("GB");
  const [source, setSource] = useState<SourceId>("dvsa");
  const [maxLeads, setMaxLeads] = useState("250");
  const plan = useAction((draft: CampaignDraft) => engine.createCampaign(draft));
  const running = run.phase === "running" || run.phase === "starting";

  const draft: CampaignDraft = { kinds: split(kinds), places: split(places), country: country.trim().toUpperCase(), source, maxLeads: Number(maxLeads) };
  const check = () => { void plan.call(draft); };
  useEffect(() => { if (autoPlan) check(); /* once, for a render */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const problems = plan.error instanceof EngineError ? plan.error.details : [];
  const problem = (key: string) => problems.find((p) => p.startsWith(key))?.split(": ")[1] ?? null;
  const edited = () => { if (plan.result || plan.error) plan.clear(); };

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
          <form className="lf-form" onSubmit={(e) => { e.preventDefault(); check(); }}>
            <Field label="Kind of business" hint="Separate several with commas." error={problem("target.categories")}>
              {(id, note) => <TextInput id={id} aria-describedby={note} placeholder="MOT garage" value={kinds} onChange={(e) => { setKinds(e.target.value); edited(); }} />}
            </Field>
            <div className="lf-form__row">
              <Field label="Place" hint="Towns, counties or postcode areas." error={problem("target.geography.areas")}>
                {(id, note) => <TextInput id={id} aria-describedby={note} placeholder="Bristol" value={places} onChange={(e) => { setPlaces(e.target.value); edited(); }} />}
              </Field>
              <Field label="Country" hint="Two letters." error={problem("target.geography.country")}>
                {(id, note) => <TextInput id={id} aria-describedby={note} className="ds-input lf-input--short" maxLength={2} value={country} onChange={(e) => { setCountry(e.target.value); edited(); }} />}
              </Field>
            </div>

            <fieldset className="lf-choice">
              <legend className="ds-field__label">Where to look</legend>
              {SOURCES.map((s) => (
                <label key={s.id} className={cx("lf-choice__item", source === s.id && "is-active")}>
                  <input type="radio" name="source" className="ds-visually-hidden" checked={source === s.id} onChange={() => { setSource(s.id); edited(); }} />
                  <span className="lf-choice__mark" aria-hidden="true" />
                  <span>
                    <span className="lf-choice__name">{s.name}</span>
                    <span className="lf-choice__detail">{s.detail}</span>
                  </span>
                </label>
              ))}
            </fieldset>

            <Field label="Stop after" hint="Businesses. The run ends when it has this many." error={problem("caps.max_leads")}>
              {(id, note) => <TextInput id={id} aria-describedby={note} className="ds-input lf-input--short" inputMode="numeric" value={maxLeads} onChange={(e) => { setMaxLeads(e.target.value.replace(/\D/g, "")); edited(); }} />}
            </Field>

            <div className="lf-form__actions">
              <Button type="submit" variant={plan.result ? "soft" : "primary"} size="lg" busy={plan.busy}>{plan.busy ? "Checking the plan" : "Check the plan"}</Button>
            </div>
          </form>
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
              <ErrorBanner error={plan.error} onRetry={problems.length ? undefined : check} />
            </>
          )}
          {!plan.busy && !plan.error && !plan.result && (
            <EmptyState icon="campaign" title="The plan appears here" detail="How many searches, about how long, and how many businesses at most. Nothing is collected until you start the run." />
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
