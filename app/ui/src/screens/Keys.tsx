import { useState } from "react";
import type { Engine, KeyName, KeyStatus } from "../engine.ts";
import { EngineError } from "../engine.ts";
import { Badge, Button, Card, ErrorBanner, Skeleton, StatusBanner, cx } from "../components/ui";
import { Icon } from "../components/Icon";
import { formatDate, useAction, useLoad } from "../lib";
import { keyBadge, keyFieldProblem, keysHeadline } from "../follow.ts";

const KEYS: Record<KeyName, [title: string, detail: string]> = {
  companies_house_key: ["Companies House API key", "Needed to search Companies House. Free from the Companies House developer hub."],
  opencorporates_token: ["OpenCorporates token", "Optional. Adds company officers where Companies House has none."],
};

export function Keys({ engine }: { engine: Engine }) {
  const keys = useLoad(() => engine.listKeys(), [engine]);
  const replace = (next: KeyStatus) => { if (keys.data) keys.set(keys.data.map((k) => (k.name === next.name ? next : k))); };

  return (
    <div className="lf-screen lf-screen--narrow">
      <header className="lf-screen__head">
        <div>
          <h1>Keys</h1>
          {/* the page does not promise a keyring the engine cannot reach (kinds `missing` and `environment`) */}
          <p>{keysHeadline(keys.error instanceof EngineError ? keys.error : null)}</p>
        </div>
      </header>
      {keys.state === "loading" && <Card><Skeleton lines={4} label="Asking the keyring" /></Card>}
      {keys.state === "error" && <Card><ErrorBanner error={keys.error} onRetry={keys.reload} /></Card>}
      {keys.state === "done" && !keys.data.some((k) => k.saved) && (
        <StatusBanner compact tone="neutral" title="No key is saved yet" detail="The MOT test stations register needs none. Companies House needs its key." />
      )}
      {keys.state === "done" && keys.data.map((k) => <KeyCard key={k.name} status={k} engine={engine} onChange={replace} />)}
    </div>
  );
}

function KeyCard({ status, engine, onChange }: { status: KeyStatus; engine: Engine; onChange: (k: KeyStatus) => void }) {
  const [value, setValue] = useState("");
  const [editing, setEditing] = useState(false);
  const save = useAction((v: string) => engine.saveKey(status.name, v));
  const remove = useAction(() => engine.removeKey(status.name));
  const [title, detail] = KEYS[status.name];
  const showField = !status.saved || editing;
  const badge = keyBadge(status);
  // a save the workspace refuses (`registry.keyring` off): shown on the field, not as a banner
  const fieldProblem = keyFieldProblem(save.error);
  const submit = async () => {
    const next = await save.call(value);
    // the typed key leaves the page whether or not it was stored
    setValue("");
    if (next) { setEditing(false); onChange(next); }
  };

  return (
    <Card className="lf-key" label={title}>
      <div className="lf-key__head">
        <div>
          <h2>{title}</h2>
          <p>{detail}</p>
        </div>
        <Badge tone={badge.tone}>{badge.text}{status.saved && status.savedAt ? ` ${formatDate(status.savedAt)}` : ""}</Badge>
      </div>
      {badge.note && <p className="lf-note lf-note--warn"><Icon name="info" size={16} />{badge.note}</p>}
      {showField ? (
        <form className="lf-key__form" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <div className={cx("ds-field", fieldProblem && "is-invalid")}>
            <input className="ds-input" type="password" autoComplete="off" spellCheck={false} aria-label={`${title}: paste the key`} aria-invalid={fieldProblem ? true : undefined} placeholder="Paste the key" value={value} onChange={(e) => setValue(e.target.value)} />
            {fieldProblem && <p className="ds-field__note" role="alert">{fieldProblem}</p>}
          </div>
          <Button type="submit" variant="primary" busy={save.busy} disabled={!value.trim()}>{save.busy ? "Saving" : "Save in the keyring"}</Button>
          {editing && <Button variant="ghost" onClick={() => { setEditing(false); setValue(""); }}>Cancel</Button>}
        </form>
      ) : (
        <div className="lf-key__form">
          <p className="lf-key__hidden" aria-label="The key is saved and hidden">••••••••••••••••</p>
          <Button variant="surface" onClick={() => setEditing(true)}>Replace</Button>
          <Button variant="danger-soft" busy={remove.busy} onClick={() => void remove.call().then((next) => { if (next) onChange(next); })}>Remove</Button>
        </div>
      )}
      {((save.error !== null && !fieldProblem) || remove.error !== null) && <ErrorBanner compact error={remove.error ?? save.error} />}
    </Card>
  );
}
