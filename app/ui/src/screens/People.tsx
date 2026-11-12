import { useEffect, useMemo, useState } from "react";
import { ForgetFlow, reportLines } from "../forget.ts";
import type { ForgetStep } from "../forget.ts";
import type { Engine, ForgetResult, Person, SuppressResult } from "../engine.ts";
import type { ScreenId } from "../App";
import { Badge, Button, Card, Dialog, EmptyState, ErrorBanner, SearchInput, SegmentedControl, Skeleton, StatusBanner, TextInput } from "../components/ui";
import { Icon } from "../components/Icon";
import { NOT_RECORDED, formatCount, formatDate, formatDateOrNot, useAction, useLoad } from "../lib";

type Target = { value: string; label: string };
type Ask = { kind: "forget" | "suppress"; person: Person | null; typed: string };

export function People({ engine, go, openDialog }: { engine: Engine; go: (s: ScreenId) => void; openDialog: string | null }) {
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [ask, setAsk] = useState<Ask | null>(null);
  const [done, setDone] = useState<{ forget: ForgetResult | null; suppress: SuppressResult | null }>({ forget: null, suppress: null });
  const page = useLoad(() => engine.listPeople({ search, limit: 50 }), [engine, search]);

  // a render may ask for one confirmation to be open
  useEffect(() => {
    if (page.state === "done" && (openDialog === "forget" || openDialog === "suppress") && !ask && page.data.people[0]) {
      setAsk({ kind: openDialog, person: page.data.people[0], typed: "" });
    }
  }, [page.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const finished = (result: { forget?: ForgetResult; suppress?: SuppressResult }) => {
    setAsk(null);
    setTyped("");
    setDone({ forget: result.forget ?? null, suppress: result.suppress ?? null });
    page.reload();
  };

  return (
    <div className="lf-screen">
      <header className="lf-screen__head">
        <div><h1>People</h1><p>The named people the campaigns found, with an email address or phone number only where one was recorded as theirs, and where and when it was found.</p></div>
      </header>

      <Card padding="md" className="lf-request" label="A request from a person">
        <div className="lf-request__text">
          <h2>Someone asked to be removed</h2>
          <p>Forget and Suppress act on any email address or domain you enter, whether or not it is listed below. This list holds named people only.</p>
        </div>
        <TextInput aria-label="Email address, domain or name" placeholder="name@business.example" value={typed} onChange={(e) => setTyped(e.target.value)} />
        <Button variant="danger-soft" leadingIcon="forget" disabled={!typed.trim()} onClick={() => setAsk({ kind: "forget", person: null, typed: typed.trim() })}>Forget</Button>
        <Button variant="surface" leadingIcon="suppress" disabled={!typed.trim()} onClick={() => setAsk({ kind: "suppress", person: null, typed: typed.trim() })}>Suppress</Button>
      </Card>

      {done.forget && (
        <StatusBanner compact tone="success" title={`Forgotten: ${done.forget.value}`}
          detail={<><p>{formatCount(done.forget.rows)} database rows, {done.forget.filesRemoved} files deleted, {done.forget.filesEdited} files with lines taken out. A new run skips them.</p>{done.forget.warnings.map((w) => <p key={w}>{w}</p>)}</>} />
      )}
      {done.suppress && (
        <StatusBanner compact tone="success" title={`Suppressed: ${done.suppress.value}`}
          detail={`It leaves every sheet from the next export on and is not collected again. The list holds ${formatCount(done.suppress.suppressed)} entries.`} />
      )}

      <Card padding="none" className="lf-people" label="Named people">
        <div className="lf-people__bar">
          <SearchInput label="Search the named people" placeholder="Search by name, address, business or domain" value={search} onChange={(e) => setSearch(e.target.value)} />
          {page.state === "done" && page.data.total > 0 && <p className="lf-caption">{search ? `${formatCount(page.data.matching)} of ${formatCount(page.data.total)}` : `${formatCount(page.data.total)} named people`}</p>}
        </div>

        {page.state === "loading" && <div className="lf-people__pad"><Skeleton lines={6} label="Loading the named people" /></div>}
        {page.state === "error" && <div className="lf-people__pad"><ErrorBanner error={page.error} onRetry={page.reload} /></div>}
        {page.state === "done" && page.data.total === 0 && (
          <EmptyState icon="people" title="No named people yet" detail="When a run has read the websites, the people it named are listed here with the page each detail came from."
            action={<Button variant="primary" leadingIcon="campaign" onClick={() => go("campaign")}>New campaign</Button>} />
        )}
        {page.state === "done" && page.data.total > 0 && page.data.matching === 0 && (
          <EmptyState icon="search" title="Nobody matches that" detail="An address or domain that is not listed can still be forgotten or suppressed with the box above." />
        )}
        {page.state === "done" && page.data.people.length > 0 && (
          <table className="lf-table">
            <thead>
              <tr><th scope="col">Person</th><th scope="col">Their details</th><th scope="col">Found</th><th scope="col"><span className="ds-visually-hidden">Actions</span></th></tr>
            </thead>
            <tbody>
              {page.data.people.map((p) => (
                <tr key={p.id}>
                  <th scope="row">
                    <span className="lf-table__name">{p.name}{p.suppressed && <Badge tone="neutral">Suppressed</Badge>}</span>
                    <span className="lf-table__sub">{p.role}, {p.business}</span>
                  </th>
                  <td>
                    <span className="lf-table__line">{p.email ? <>{p.email.split("@")[0]}<wbr />@{p.email.split("@")[1]}</> : "No email recorded"}</span>
                    <span className="lf-table__sub">{p.phone ?? "No phone recorded"}</span>
                  </td>
                  <td>
                    {/* a null source, date or campaign is said in words: never an empty cell, a dash, or "Invalid Date" */}
                    {p.source !== null && p.source.trim() !== ""
                      ? <span className="lf-table__line lf-source"><Icon name="source" size={14} /><span>{p.source.split("/")[0]}<wbr />/{p.source.split("/").slice(1).join("/")}</span></span>
                      : <span className="lf-table__line lf-source lf-source--none"><span>Source {NOT_RECORDED}</span></span>}
                    <span className="lf-table__sub">
                      {p.foundAt !== null && formatDateOrNot(p.foundAt) !== NOT_RECORDED ? formatDate(p.foundAt) : `Date ${NOT_RECORDED}`}
                      {" · "}
                      {p.campaign !== null && p.campaign.trim() !== "" ? p.campaign : `Campaign ${NOT_RECORDED}`}
                    </span>
                  </td>
                  <td>
                    <div className="lf-table__actions">
                      <Button variant="ghost" size="sm" disabled={p.suppressed} onClick={() => setAsk({ kind: "suppress", person: p, typed: "" })}>Suppress</Button>
                      <Button variant="danger-soft" size="sm" onClick={() => setAsk({ kind: "forget", person: p, typed: "" })}>Forget</Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Confirm ask={ask} engine={engine} onClose={() => setAsk(null)} onDone={finished} />
    </div>
  );
}

function targetsFor(ask: Ask): Target[] {
  if (!ask.person) return [{ value: ask.typed, label: ask.typed }];
  const p = ask.person;
  const out: Target[] = [];
  if (p.email) out.push({ value: p.email, label: "This address" });
  if (ask.kind === "forget") out.push({ value: p.name, label: "This name" });
  out.push({ value: p.domain, label: "The whole domain" });
  return out;
}

function Confirm({ ask, engine, onClose, onDone }: {
  ask: Ask | null; engine: Engine; onClose: () => void; onDone: (r: { forget?: ForgetResult; suppress?: SuppressResult }) => void;
}) {
  const [index, setIndex] = useState(0);
  const [step, setStep] = useState<ForgetStep>({ step: "idle" });
  const flow = useMemo(() => new ForgetFlow(engine, setStep), [engine]);
  const suppress = useAction((value: string) => engine.suppressAddress(value));
  useEffect(() => { setIndex(0); flow.reset(); suppress.clear(); }, [ask]); // eslint-disable-line react-hooks/exhaustive-deps

  const targets = ask ? targetsFor(ask) : [];
  const target = targets.length ? targets[Math.min(index, targets.length - 1)]! : null;
  const isForget = ask?.kind === "forget";
  // Forget is report-first: choosing what to act on runs the engine's dry run for it, and nothing is deleted by that
  useEffect(() => {
    if (isForget && target) void flow.check(target.value);
  }, [ask, index]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!ask || !target) return <Dialog open={false} title="" onClose={onClose} actions={null}>{null}</Dialog>;

  const deleting = step.step === "deleting";
  const confirmable = step.step === "report" || step.step === "deleting" || step.step === "delete-failed";
  const confirm = async () => {
    if (isForget) { const r = await flow.confirm(); if (r) onDone({ forget: r }); }
    else { const r = await suppress.call(target.value); if (r) onDone({ suppress: r }); }
  };
  const busy = isForget ? deleting : suppress.busy;

  return (
    <Dialog open title={isForget ? `Forget ${ask.person?.name ?? ask.typed}?` : `Suppress ${ask.person?.email ?? ask.person?.domain ?? ask.typed}?`} onClose={onClose}
      actions={
        <>
          <Button variant="ghost" size="lg" onClick={onClose} disabled={busy}>{isForget && step.step === "nothing" ? "Close" : "Cancel"}</Button>
          {(!isForget || confirmable) && (
            <Button variant={isForget ? "danger" : "primary"} size="lg" busy={busy} onClick={() => void confirm()}>
              {busy ? (isForget ? "Deleting" : "Adding") : isForget ? "Delete and keep them out" : "Suppress"}
            </Button>
          )}
        </>
      }>
      {targets.length > 1 && (
        <SegmentedControl label="What to act on" options={targets.map((t, i) => ({ id: String(i), label: t.label }))} value={String(Math.min(index, targets.length - 1))} onChange={(id) => setIndex(Number(id))} />
      )}
      <p className="lf-confirm__target lf-mono">{target.value}</p>
      {isForget ? <ForgetReport step={step} onRetry={() => void flow.check(target.value)} /> : (
        <>
          <p>The address leaves every sheet and every tab from the next export on, and a new run does not collect it again.</p>
          <p>Nothing is deleted from the workspace. To delete as well, use Forget. A suppression cannot be lifted from this window.</p>
        </>
      )}
      {!isForget && suppress.error !== null && <ErrorBanner compact error={suppress.error} />}
    </Dialog>
  );
}

/** What the Forget confirmation says in each step of the flow: the engine's own numbers and words. */
function ForgetReport({ step, onRetry }: { step: ForgetStep; onRetry: () => void }) {
  if (step.step === "idle" || step.step === "checking") return <Skeleton lines={3} label="Checking what the workspace holds" />;
  if (step.step === "report-failed") {
    return (
      <>
        <p>The check did not finish, so nothing was deleted and nothing can be deleted from here yet.</p>
        <ErrorBanner compact error={step.error} onRetry={onRetry} />
      </>
    );
  }
  if (step.step === "nothing") {
    return <p>Nothing is held for this value: no database rows and no files. There is nothing to delete. To keep it out of new runs, use Suppress.</p>;
  }
  if (step.step === "done") return null;
  return (
    <>
      <p>The workspace holds this. Deleting it removes:</p>
      <ul className="lf-confirm__list">{reportLines(step.report).map((line) => <li key={line}>{line}</li>)}</ul>
      {step.report.warnings.map((w) => <p key={w} className="lf-note lf-note--warn"><Icon name="alert" size={16} />{w}</p>)}
      <p>They also go on the suppression list, so a new run does not collect them again. It cannot be undone.</p>
      {step.step === "delete-failed" && <ErrorBanner compact error={step.error} />}
    </>
  );
}
