import { useEffect, useState } from "react";
import type { Engine, PurgeReport } from "../engine.ts";
import type { ScreenId } from "../App";
import { Button, Card, CardHeader, Dialog, EmptyState, ErrorBanner, Readout, ReadoutGroup, Skeleton, StatusBanner } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatCount, useAction, useLoad } from "../lib";

export function Data({ engine, go, openDialog }: { engine: Engine; go: (s: ScreenId) => void; openDialog: string | null }) {
  const report = useLoad(() => engine.purgeReport(), [engine]);
  const retention = useLoad(() => engine.getRetention(), [engine]);
  const [months, setMonths] = useState<number | null>(null);
  const [ask, setAsk] = useState<"purge" | "everything" | null>(openDialog === "purge" || openDialog === "everything" ? openDialog : null);
  const save = useAction((m: number) => engine.setRetention(m));
  const purge = useAction(() => engine.purgeApply());
  const wipe = useAction(() => engine.purgeEverything());

  useEffect(() => { if (retention.state === "done" && months === null) setMonths(retention.data.months); }, [retention.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const r: PurgeReport | null = purge.result ?? report.data;
  const saved = save.result?.months ?? retention.data?.months ?? null;
  const limits = retention.data;
  const noWorkspace = r?.state === "no_workspace";

  return (
    <div className="lf-screen">
      <header className="lf-screen__head">
        <div><h1>Data and retention</h1><p>How long records are kept, what the next clean-up deletes, and how to delete everything.</p></div>
      </header>

      <div className="lf-grid lf-grid--data">
        <Card label="Retention period">
          <CardHeader title="Keep records for" />
          {retention.state === "loading" && <Skeleton lines={3} label="Reading the retention period" />}
          {retention.state === "error" && <ErrorBanner compact error={retention.error} onRetry={retention.reload} />}
          {limits && months !== null && (
            <>
              <div className="lf-stepper">
                <Button variant="soft" aria-label="One month less" disabled={months <= limits.min} onClick={() => setMonths(months - 1)}><Icon name="minus" size={16} /></Button>
                <p className="lf-stepper__value" aria-live="polite"><span>{months}</span> {months === 1 ? "month" : "months"}</p>
                <Button variant="soft" aria-label="One month more" disabled={months >= limits.max} onClick={() => setMonths(months + 1)}><Icon name="plus" size={16} /></Button>
              </div>
              <p className="lf-caption">Counted from the day a business first entered the workspace. Finding it again does not extend it. {limits.max} months is the longest the engine allows.</p>
              {save.error !== null && <ErrorBanner compact error={save.error} />}
              <div className="lf-card__actions">
                {months === saved ? (
                  <p className="lf-saved"><Icon name="check" size={16} />This is the saved period</p>
                ) : (
                  <>
                    <Button variant="primary" busy={save.busy} onClick={() => void save.call(months).then((x) => { if (x) report.reload(); })}>
                      {save.busy ? "Saving" : `Save ${months} ${months === 1 ? "month" : "months"}`}
                    </Button>
                    <Button variant="ghost" disabled={save.busy} onClick={() => setMonths(saved)}>Keep {saved}</Button>
                  </>
                )}
              </div>
            </>
          )}
        </Card>

        <Card label="Next clean-up">
          <CardHeader title="The next clean-up" detail="A report first. Nothing is deleted by looking." actions={<Button variant="ghost" size="sm" leadingIcon="refresh" onClick={() => { purge.clear(); report.reload(); }}>Check again</Button>} />
          {report.state === "loading" && <Skeleton lines={4} label="Making the report" />}
          {report.state === "error" && <ErrorBanner compact error={report.error} onRetry={report.reload} />}
          {r && noWorkspace && <EmptyState icon="data" title="Nothing is stored here yet" detail="This workspace has no database. After the first run, this page shows what is due to be deleted." action={<Button variant="primary" leadingIcon="campaign" onClick={() => go("campaign")}>New campaign</Button>} />}
          {r && !noWorkspace && (
            <>
              {r.state === "purged" && <StatusBanner compact tone="success" title={`Deleted ${formatCount(r.deleted)} businesses and everything attached to them`} />}
              <ReadoutGroup>
                <Readout label={`Past ${r.months} months`} value={formatCount(r.expired)} unit={`of ${formatCount(r.total)}`} />
                <Readout label="Due in 30 days" value={formatCount(r.expiringIn30Days)} />
              </ReadoutGroup>
              {!r.armed && <p className="lf-note"><Icon name="info" size={16} />This workspace has not had its first check yet: the next run only reports.</p>}
              <p className="lf-caption">Every run starts with this clean-up. It stops instead of deleting when more than half the workspace would go, which is what a wrong clock looks like.</p>
              {purge.error !== null && <ErrorBanner compact error={purge.error} />}
              <div className="lf-card__actions">
                <Button variant="danger-soft" leadingIcon="forget" disabled={r.expired === 0} onClick={() => setAsk("purge")}>
                  {r.expired === 0 ? "Nothing to delete" : `Delete the ${formatCount(r.expired)} now`}
                </Button>
              </div>
            </>
          )}
        </Card>

        <Card label="Requests and suppression" padding="md" className="lf-data__strip">
          <Icon name="suppress" size={20} />
          <div>
            <h2>{r && !noWorkspace ? `${formatCount(r.suppressed)} addresses and domains are suppressed` : "Suppression list"}</h2>
            <p>They are left out of every sheet and never collected again. Forget or suppress someone on the People page.</p>
          </div>
          <Button variant="surface" leadingIcon="people" onClick={() => go("people")}>Open People</Button>
        </Card>

        <Card label="Delete everything" padding="md" className="lf-data__strip">
          <Icon name="forget" size={20} />
          <div>
            <h2>Delete everything in this workspace</h2>
            <p>The database, the cache, the sheets in the exports folder, the logs and the hand-off and draft files. Works on a workspace of any age.</p>
            {wipe.result && <p className="lf-data__done">Deleted {formatCount(wipe.result.filesRemoved)} files.</p>}
          </div>
          <Button variant="danger-soft" onClick={() => setAsk("everything")}>Delete everything</Button>
        </Card>
      </div>

      <Dialog open={ask === "purge"} title={`Delete ${formatCount(r?.expired ?? 0)} businesses past the limit?`} onClose={() => setAsk(null)}
        actions={<>
          <Button variant="ghost" size="lg" onClick={() => setAsk(null)} disabled={purge.busy}>Cancel</Button>
          <Button variant="danger" size="lg" busy={purge.busy} onClick={() => void purge.call().then((x) => { if (x) setAsk(null); })}>{purge.busy ? "Deleting" : "Delete them"}</Button>
        </>}>
        <p>Each business that entered the workspace more than {r?.months ?? 12} months ago is deleted with everything attached to it: its contacts, the pages read from its website, its scores and its draft notes.</p>
        <p className="lf-note lf-note--warn"><Icon name="alert" size={16} />Sheets you already gave to someone are not reached. It cannot be undone.</p>
        {purge.error !== null && <ErrorBanner compact error={purge.error} />}
      </Dialog>

      <Dialog open={ask === "everything"} title="Delete everything in this workspace?" onClose={() => setAsk(null)}
        actions={<>
          <Button variant="ghost" size="lg" onClick={() => setAsk(null)} disabled={wipe.busy}>Cancel</Button>
          <Button variant="danger" size="lg" busy={wipe.busy} onClick={() => void wipe.call().then((x) => { if (x) { setAsk(null); report.reload(); } })}>{wipe.busy ? "Deleting" : "Delete everything"}</Button>
        </>}>
        <p>This deletes the contents of the data folder and the campaign files beside it:</p>
        <ul className="lf-confirm__list">
          <li>the database, with every business, contact and run</li>
          <li>the cache of pages read, and the logs</li>
          <li>the sheets in the exports folder</li>
          <li>the hand-off and draft files</li>
        </ul>
        <p className="lf-note lf-note--warn"><Icon name="alert" size={16} />Your keys and the settings of this window stay. Sheets you already gave to someone are not reached. It cannot be undone.</p>
        {wipe.error !== null && <ErrorBanner compact error={wipe.error} />}
      </Dialog>
    </div>
  );
}
