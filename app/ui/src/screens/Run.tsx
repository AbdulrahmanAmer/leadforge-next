import { STAGES, type StageId } from "../engine.ts";
import type { RunView, ScreenId } from "../App";
import { Button, Card, EmptyState, ErrorBanner, ProgressBar, Readout, ReadoutGroup, Skeleton, StatusBanner, cx } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatCount, formatDuration } from "../lib";

const STAGE_NAME: Record<StageId, [name: string, doing: string]> = {
  discover: ["Find the businesses", "Searching the register"],
  enrich: ["Read their websites", "Reading websites for contact details"],
  label: ["Name who to contact", "Picking the person to contact"],
  score: ["Score each business", "Scoring"],
  draft: ["Write the draft notes", "Writing draft notes for the sheet"],
  export: ["Write the sheet", "Writing the sheet"],
};

export function Run({ run, onStop, onResume, go }: { run: RunView; onStop: () => void; onResume: () => void; go: (s: ScreenId) => void }) {
  if (run.phase === "idle") {
    return (
      <div className="lf-screen">
        <header className="lf-screen__head"><div><h1>Run</h1><p>The progress of the campaign that is running, stage by stage.</p></div></header>
        <Card>
          <EmptyState icon="run" title="Nothing is running" detail="Start a campaign and its progress shows here, one stage after the other."
            action={<Button variant="primary" leadingIcon="campaign" onClick={() => go("campaign")}>New campaign</Button>} />
        </Card>
      </div>
    );
  }

  const live = run.phase === "running" || run.phase === "starting";
  const currentIndex = run.current ? STAGES.indexOf(run.current) : run.phase === "finished" ? STAGES.length : -1;
  const counts = run.status?.counts;
  const now = run.current ? run.stages[run.current] : null;

  return (
    <div className="lf-screen">
      <header className="lf-screen__head">
        <div>
          <h1>Run</h1>
          <p className="lf-mono">{run.campaign}</p>
        </div>
        {live && (
          <Button variant="danger-soft" size="lg" leadingIcon="stop" onClick={onStop} busy={run.stopping} disabled={run.phase === "starting"}>
            {run.stopping ? "Stopping" : "Stop the run"}
          </Button>
        )}
        {(run.phase === "stopped" || run.phase === "failed") && run.runId && (
          <Button variant="primary" size="lg" leadingIcon="play" onClick={onResume}>Continue the run</Button>
        )}
        {run.phase === "finished" && <Button variant="primary" size="lg" leadingIcon="results" onClick={() => go("results")}>Open the results</Button>}
      </header>

      <div className="lf-grid lf-grid--run">
        <Card padding="none" className="lf-stages" label="Stages">
          {run.phase === "starting" && <div className="lf-stages__starting"><Skeleton lines={6} label="Starting the engine" /></div>}
          {run.phase !== "starting" && (
            <ol className="lf-stages__list">
              {STAGES.map((id, i) => {
                const s = run.stages[id];
                const state = s.summary ? "done" : i === currentIndex ? (live ? "now" : "held") : i < currentIndex ? "done" : "next";
                return (
                  <li key={id} className={cx("lf-stage", `is-${state}`)} aria-current={state === "now" ? "step" : undefined}>
                    <span className="lf-stage__mark" aria-hidden="true">{state === "done" ? <Icon name="check" size={14} /> : i + 1}</span>
                    <div className="lf-stage__text">
                      <p className="lf-stage__name">{STAGE_NAME[id][0]}</p>
                      <p className="lf-stage__detail">
                        {state === "done" && (s.summary ?? "Done")}
                        {state === "now" && (s.message || STAGE_NAME[id][1])}
                        {state === "held" && (run.phase === "failed" ? "Stopped here by an error. What was found is kept." : "Stopped here. What was found is kept.")}
                        {state === "next" && "Not started"}
                      </p>
                    </div>
                    {(state === "now" || state === "held") && (
                      <div className="lf-stage__meter">
                        <span className="lf-stage__count">{formatCount(s.done)}{s.total !== null && ` of ${formatCount(s.total)}`}</span>
                        <ProgressBar value={s.done} max={s.total} label={STAGE_NAME[id][0]} tone={state === "held" ? "neutral" : "accent"} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </Card>

        <div className="lf-stack">
          <Card>
            {run.phase === "starting" && <StatusBanner tone="accent" icon="clock" title="Starting the engine" detail="The first progress line follows in a moment." />}
            {run.phase === "running" && <StatusBanner tone="accent" icon="play" title={run.current ? STAGE_NAME[run.current][1] : "Running"} detail={`About ${formatDuration(run.etaSeconds)} left in this stage.`} />}
            {run.phase === "finished" && <StatusBanner tone="success" title="The run finished" detail="The sheet is written. Open the results to see it." />}
            {run.phase === "stopped" && <StatusBanner tone="neutral" icon="stop" title="You stopped the run" detail="Nothing found so far was lost. Continue it whenever you like." />}
            {run.phase === "failed" && <ErrorBanner error={run.error} />}
            {run.phase === "running" && now && (
              <ReadoutGroup divided>
                <Readout label="Done in this stage" value={formatCount(now.done)} unit={now.total !== null ? `of ${formatCount(now.total)}` : undefined} />
                <Readout label="Time left" value={run.etaSeconds === null ? "–" : formatDuration(run.etaSeconds).split(" ")[0]} unit={run.etaSeconds === null ? undefined : formatDuration(run.etaSeconds).split(" ").slice(1).join(" ")} />
              </ReadoutGroup>
            )}
            {counts && run.phase !== "running" && (
              <ReadoutGroup divided>
                <Readout label="Businesses" value={formatCount(counts.businesses)} />
                <Readout label="Contact details" value={formatCount(counts.contacts)} />
              </ReadoutGroup>
            )}
          </Card>
          {run.notices.length > 0 && (
            <Card padding="md" className="lf-notice">
              <Icon name="data" size={18} />
              <div>
                {run.notices.map((n) => <p key={n}>{n}</p>)}
                <button type="button" className="lf-link" onClick={() => go("data")}>Data and retention</button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
