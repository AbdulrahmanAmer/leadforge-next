import { useEffect, useState } from "react";
import type { Campaign, Engine, RunState } from "../engine.ts";
import type { ScreenId } from "../App";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorBanner, KeyValueList, Skeleton, type Tone, cx } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatCount, formatDate, useAction, useLoad } from "../lib";

const STATE: Record<RunState, [label: string, tone: Tone]> = {
  finished: ["Finished", "success"],
  running: ["Running", "accent"],
  stopped: ["Stopped", "warn"],
  failed: ["Failed", "danger"],
};

const SOURCE = { dvsa: "MOT test stations", companies_house: "Companies House" } as const;
const FILE = { xlsx: "The sheet (Excel)", csv: "The same rows as CSV", report: "The run report (JSON)" } as const;

export function Results({ engine, go }: { engine: Engine; go: (s: ScreenId) => void }) {
  const campaigns = useLoad(() => engine.listCampaigns(), [engine]);
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    if (campaigns.state === "done" && !picked && campaigns.data[0]) setPicked(campaigns.data[0].runId);
  }, [campaigns.state, campaigns.data, picked]);
  const current = campaigns.data?.find((c) => c.runId === picked) ?? null;

  return (
    <div className="lf-screen">
      <header className="lf-screen__head">
        <div><h1>Results</h1><p>Every campaign of this workspace and the sheet it wrote.</p></div>
        <Button variant="surface" size="lg" leadingIcon="campaign" onClick={() => go("campaign")}>New campaign</Button>
      </header>

      {campaigns.state === "loading" && <Card><Skeleton lines={6} label="Loading the campaigns" /></Card>}
      {campaigns.state === "error" && <Card><ErrorBanner error={campaigns.error} onRetry={campaigns.reload} /></Card>}
      {campaigns.state === "done" && campaigns.data.length === 0 && (
        <Card>
          <EmptyState icon="results" title="No campaigns yet" detail="When a run finishes, its sheet is listed here with the day its records will be deleted." />
        </Card>
      )}
      {campaigns.state === "done" && campaigns.data.length > 0 && (
        <div className="lf-grid lf-grid--results">
          <ul className="lf-list" aria-label="Campaigns">
            {campaigns.data.map((c) => (
              <li key={c.runId}>
                <button type="button" className={cx("lf-row", c.runId === picked && "is-active")} aria-pressed={c.runId === picked} onClick={() => setPicked(c.runId)}>
                  <span className="lf-row__main">
                    <span className="lf-row__title">{c.kinds.join(", ")} in {c.places.join(", ")}</span>
                    <span className="lf-row__meta">{formatDate(c.startedAt)} · {SOURCE[c.source]}</span>
                  </span>
                  <span className="lf-row__figure">{formatCount(c.businesses)}<span>businesses</span></span>
                  <Badge tone={STATE[c.state][1]}>{STATE[c.state][0]}</Badge>
                </button>
              </li>
            ))}
          </ul>
          {current && <Detail key={current.runId} campaign={current} engine={engine} onChanged={campaigns.reload} />}
        </div>
      )}
    </div>
  );
}

function Detail({ campaign, engine, onChanged }: { campaign: Campaign; engine: Engine; onChanged: () => void }) {
  const write = useAction((runId: string) => engine.exportSheet(runId));
  const open = useAction((path: string) => engine.openSheet(path));
  const sheet = write.result ?? campaign.sheet;
  const xlsx = sheet?.files.find((f) => f.kind === "xlsx") ?? sheet?.files[0];

  return (
    <Card className="lf-detail" label="The sheet">
      <CardHeader title={campaign.kinds.join(", ") + " in " + campaign.places.join(", ")} detail={<span className="lf-mono">{campaign.name}</span>} />
      {sheet && xlsx && (
        <div className="lf-detail__actions">
          <Button variant="primary" size="lg" leadingIcon="sheet" busy={open.busy} onClick={() => void open.call(xlsx.path)}>Open the sheet</Button>
          <Button variant="surface" size="lg" leadingIcon="refresh" busy={write.busy} onClick={() => void write.call(campaign.runId).then((s) => { if (s) onChanged(); })}>
            {write.busy ? "Writing" : "Write it again"}
          </Button>
        </div>
      )}
      <KeyValueList rows={[
        ["Businesses", formatCount(campaign.businesses)],
        ["With an email address", formatCount(campaign.withEmail)],
        ["With a phone number", formatCount(campaign.withPhone)],
        ...(campaign.state === "finished" ? [["Strong, fair, weak", `${campaign.tiers.a} · ${campaign.tiers.b} · ${campaign.tiers.c}`] as [string, string]] : []),
        ["Kept until", formatDate(campaign.keptUntil)],
      ]} />

      {(write.error !== null || open.error !== null) && <ErrorBanner compact error={write.error ?? open.error} />}

      {sheet && xlsx ? (
        <>
          <ul className="lf-files" aria-label="Files of the sheet">
            {sheet.files.map((f) => (
              <li key={f.path}>
                <Icon name={f.kind === "report" ? "info" : "sheet"} size={16} />
                <span>{FILE[f.kind]}</span>
                <span className="lf-mono lf-files__path">{f.path}</span>
              </li>
            ))}
          </ul>
          <p className="lf-caption">Tabs: {sheet.tabs.map((t) => `${t.name} ${formatCount(t.rows)}`).join(" · ")}. Written {formatDate(sheet.writtenAt)}.</p>
        </>
      ) : (
        <p className="lf-note"><Icon name="info" size={16} />This run stopped before the sheet was written, so it has no sheet yet. What it found is kept.</p>
      )}
    </Card>
  );
}
