/**
 * The window's components. Structure, class names (`ds-` + BEM) and roles are the design farm's
 * (D:\design-farm\ui): Button, Card, Badge, StatusBanner, ReadoutGroup, KeyValueList, ProgressBar,
 * SegmentedControl, SearchInput, SideRail. Ported, not imported: the farm is not a published package.
 * CSS reads only --ds-* roles. No `style` attribute anywhere: the window runs under a strict policy.
 */
import { useEffect, useId, useRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { EngineError } from "../engine.ts";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ----------------------------------------------------------------- Button */
type ButtonVariant = "primary" | "soft" | "surface" | "ghost" | "danger" | "danger-soft";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  leadingIcon?: IconName;
  busy?: boolean;
}

export function Button({ variant = "soft", size = "md", leadingIcon, busy, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      className={cx("ds-btn", `ds-btn--${variant}`, `ds-btn--${size}`, className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {leadingIcon && <Icon name={leadingIcon} size={size === "sm" ? 14 : 16} />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------- Card */
export interface CardProps {
  elevation?: 0 | 1 | 2;
  padding?: "none" | "md" | "lg";
  tone?: "surface" | "sunken";
  as?: "section" | "div" | "article";
  className?: string;
  children: ReactNode;
  label?: string;
}

export function Card({ elevation = 0, padding = "lg", tone = "surface", as: Tag = "section", className, children, label }: CardProps) {
  return (
    <Tag aria-label={label} className={cx("ds-card", `ds-card--${tone}`, `ds-card--e${elevation}`, `ds-card--p-${padding}`, className)}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, detail, actions }: { title: string; detail?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ds-card-header">
      <div className="ds-card-header__title">
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {actions && <div className="ds-card-header__actions">{actions}</div>}
    </header>
  );
}

/* ------------------------------------------------------------------ Badge */
export type Tone = "accent" | "success" | "danger" | "warn" | "neutral";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("ds-badge", "ds-badge--sm", "ds-badge--soft", `ds-badge--${tone}`)}>{children}</span>;
}

/* ----------------------------------------------------------- StatusBanner */
const STATUS_ICON: Record<Tone, IconName> = { success: "check", danger: "alert", warn: "alert", accent: "info", neutral: "info" };

export function StatusBanner({ tone, title, detail, icon, action, compact }: {
  tone: Tone; title: string; detail?: ReactNode; icon?: IconName; action?: ReactNode; compact?: boolean;
}) {
  return (
    <div className={cx("ds-status", `ds-status--${tone}`, compact && "ds-status--compact")} role={tone === "danger" ? "alert" : "status"}>
      <span className="ds-status__disc"><Icon name={icon ?? STATUS_ICON[tone]} size={compact ? 16 : 22} /></span>
      <div className="ds-status__text">
        <p className="ds-status__title">{title}</p>
        {detail && <div className="ds-status__detail">{detail}</div>}
      </div>
      {action && <div className="ds-status__action">{action}</div>}
    </div>
  );
}

/** An engine failure in the engine's own words: what happened, its details, what it suggests next. */
export function ErrorBanner({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const e = error instanceof EngineError ? error : null;
  return (
    <StatusBanner
      tone="danger"
      compact={compact}
      title={e ? e.message : "Something went wrong in the window."}
      detail={
        <>
          {e?.details.map((d) => <p key={d}>{d}</p>)}
          {e?.next && <p className="ds-status__next">{e.next}</p>}
        </>
      }
      action={onRetry && <Button variant="surface" size="sm" leadingIcon="refresh" onClick={onRetry}>Try again</Button>}
    />
  );
}

/* ---------------------------------------------------------------- Readout */
export function ReadoutGroup({ children, divided }: { children: ReactNode; divided?: boolean }) {
  return <dl className={cx("ds-readouts", "ds-readouts--light", divided && "ds-readouts--divided")}>{children}</dl>;
}

export function Readout({ label, value, unit }: { label: string; value: ReactNode; unit?: string }) {
  return (
    <div className="ds-readout">
      <dt className="ds-readout__label">{label}</dt>
      <dd className="ds-readout__value">{value}{unit && <span className="ds-readout__unit">{unit}</span>}</dd>
    </div>
  );
}

/* ----------------------------------------------------------- KeyValueList */
export function KeyValueList({ rows }: { rows: [label: string, value: ReactNode][] }) {
  return (
    <dl className="ds-kv">
      {rows.map(([label, value]) => (
        <div className="ds-kv__row" key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------ ProgressBar */
export function ProgressBar({ value, max, label, tone = "accent" }: { value: number; max: number | null; label: string; tone?: "accent" | "success" | "neutral" }) {
  // the native element: its width needs no style attribute
  return max === null
    ? <progress className={cx("ds-progress", `ds-progress--${tone}`)} aria-label={label} />
    : <progress className={cx("ds-progress", `ds-progress--${tone}`)} aria-label={label} value={value} max={Math.max(max, 1)} />;
}

/* ------------------------------------------------------- SegmentedControl */
export function SegmentedControl<T extends string>({ label, options, value, onChange }: {
  label: string; options: readonly { id: T; label: string; icon?: IconName }[]; value: T; onChange: (id: T) => void;
}) {
  return (
    <div className="ds-seg ds-seg--filled ds-seg--md" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={o.id === value}
          className={cx("ds-seg__item", o.id === value && "is-active")} onClick={() => onChange(o.id)}>
          {o.icon && <Icon name={o.icon} size={14} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ Inputs */
export function SearchInput({ label, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="ds-search">
      <Icon name="search" size={16} />
      <span className="ds-visually-hidden">{label}</span>
      <input type="search" {...rest} />
    </label>
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: (id: string, describedBy: string | undefined) => ReactNode }) {
  const id = useId();
  const noteId = `${id}-note`;
  return (
    <div className={cx("ds-field", error && "is-invalid")}>
      <label className="ds-field__label" htmlFor={id}>{label}</label>
      {children(id, hint || error ? noteId : undefined)}
      {(error || hint) && <p className="ds-field__note" id={noteId}>{error ?? hint}</p>}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="ds-input" type="text" autoComplete="off" spellCheck={false} {...props} />;
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (next: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className={cx("ds-switch", checked && "is-on")} onClick={() => onChange(!checked)}>
      <span className="ds-switch__knob" />
    </button>
  );
}

/* ----------------------------------------------------------------- Dialog */
export function Dialog({ open, title, onClose, children, actions }: { open: boolean; title: string; onClose: () => void; children: ReactNode; actions: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog ref={ref} className="ds-dialog" aria-labelledby={titleId} onClose={onClose} onCancel={onClose}>
      {open && (
        <>
          <h2 id={titleId} className="ds-dialog__title">{title}</h2>
          <div className="ds-dialog__body">{children}</div>
          <div className="ds-dialog__actions">{actions}</div>
        </>
      )}
    </dialog>
  );
}

/* --------------------------------------------------------------- Skeleton */
export function Skeleton({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div className="ds-skeleton" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => <span key={i} className={cx("ds-skeleton__line", `ds-skeleton__line--${i % 3}`)} />)}
    </div>
  );
}

export function EmptyState({ icon, title, detail, action }: { icon: IconName; title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="ds-empty">
      <span className="ds-empty__disc"><Icon name={icon} size={24} /></span>
      <p className="ds-empty__title">{title}</p>
      <p className="ds-empty__detail">{detail}</p>
      {action}
    </div>
  );
}

/* --------------------------------------------------------------- SideRail */
export interface RailItem<T extends string> {
  id: T;
  icon: IconName;
  label: string;
  dot?: "online" | "attention";
}

/** Wave cap in a 100 x 150 box: the farm's silhouette. The caps keep their ratio; only the body stretches. */
const RAIL_CAP_PATH = "M0 0 C0 50 26 62 56 74 C88 88 100 108 100 150 L0 150 Z";

export function SideRail<T extends string>({ items, active, onSelect }: { items: readonly RailItem<T>[]; active: T; onSelect: (id: T) => void }) {
  return (
    <nav aria-label="Sections" className="ds-rail">
      <div className="ds-rail__shape" aria-hidden="true">
        <svg className="ds-rail__cap" viewBox="0 0 100 150" preserveAspectRatio="none"><path d={RAIL_CAP_PATH} /></svg>
        <div className="ds-rail__body" />
        <svg className="ds-rail__cap ds-rail__cap--end" viewBox="0 0 100 150" preserveAspectRatio="none"><path d={RAIL_CAP_PATH} /></svg>
      </div>
      <ul className="ds-rail__list">
        {items.map((it) => (
          <li key={it.id}>
            <button type="button" className={cx("ds-rail__item", it.id === active && "is-active")}
              aria-current={it.id === active ? "page" : undefined} onClick={() => onSelect(it.id)}>
              <Icon name={it.icon} size={20} />
              <span className="ds-rail__label">{it.label}</span>
              {it.dot && <span className={cx("ds-dot", `ds-dot--${it.dot}`, "ds-rail__dot")} />}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
