import { useState } from "react";
import type { Engine, KeyName, KeyStatus } from "../engine.ts";
import { EngineError } from "../engine.ts";
import { Badge, Button, Card, ErrorBanner, Skeleton, StatusBanner } from "../components/ui";
import { formatDate, useAction, useLoad } from "../lib";

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
          {/* the engine cannot do the key commands yet (kind `missing`): the page does not promise a keyring it cannot reach */}
          <p>{keys.error instanceof EngineError && keys.error.kind === "missing"
            ? "Saving a key needs a command this version of the engine does not have yet. Nothing is stored."
            : "Kept in the Windows keyring of your account. Once saved, a key is never shown again."}</p>
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
        {status.saved ? <Badge tone="success">Saved {status.savedAt ? formatDate(status.savedAt) : ""}</Badge> : <Badge tone="neutral">Not set</Badge>}
      </div>
      {showField ? (
        <form className="lf-key__form" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
          <input className="ds-input" type="password" autoComplete="off" spellCheck={false} aria-label={`${title}: paste the key`} placeholder="Paste the key" value={value} onChange={(e) => setValue(e.target.value)} />
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
      {(save.error !== null || remove.error !== null) && <ErrorBanner compact error={save.error ?? remove.error} />}
    </Card>
  );
}
