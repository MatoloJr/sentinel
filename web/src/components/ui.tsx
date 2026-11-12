import { AlertTriangle, CircleCheck, Eye, OctagonAlert, Siren, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import type { Level } from "../lib/api";

export const LEVEL_VAR: Record<string, string> = {
  Normal: "var(--lvl-normal)",
  Watch: "var(--lvl-watch)",
  Warning: "var(--lvl-warning)",
  Emergency: "var(--lvl-emergency)",
};
export const levelColor = (lvl?: string | null) => LEVEL_VAR[lvl ?? ""] ?? "var(--lvl-none)";

const ICON: Record<string, typeof Eye> = { Normal: CircleCheck, Watch: Eye, Warning: TriangleAlert, Emergency: Siren };

/** Level is always shown as colour + icon + text (never colour alone). */
export function LevelBadge({ level, size = "md" }: { level?: Level | string | null; size?: "sm" | "md" }) {
  const lv = level ?? "Not assessed";
  const Icon = ICON[lv] ?? OctagonAlert;
  const strong = lv === "Warning" || lv === "Emergency";
  return (
    <span
      className="chip num"
      style={{
        background: lv in LEVEL_VAR ? `color-mix(in oklab, ${levelColor(lv)} ${strong ? 100 : 30}%, transparent)` : undefined,
        color: strong ? "#fff" : "var(--ink)",
        fontSize: size === "sm" ? "0.72rem" : undefined,
        padding: size === "sm" ? "2px 8px" : undefined,
      }}
    >
      <Icon size={size === "sm" ? 12 : 14} aria-hidden />
      {lv}
    </span>
  );
}

export function Skeleton({ h = 20, w = "100%", className = "" }: { h?: number | string; w?: number | string; className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height: h, width: w }} aria-hidden />;
}

export function PageSkeleton() {
  return (
    <div className="page grid gap-4" aria-busy="true" aria-label="Loading">
      <Skeleton h={36} w="40%" />
      <div className="grid gap-4 sm:grid-cols-3">
        <Skeleton h={96} />
        <Skeleton h={96} />
        <Skeleton h={96} />
      </div>
      <Skeleton h={320} />
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  const notBuilt = /run_all/.test(msg);
  return (
    <div className="card flex flex-col items-start gap-3" role="alert">
      <div className="flex items-center gap-2 font-semibold">
        <AlertTriangle size={18} aria-hidden /> {notBuilt ? "Data not built yet" : "Could not load this view"}
      </div>
      <p className="muted">{notBuilt ? "Run python run_all.py (or the pipeline container), then reload." : msg}</p>
      {retry && (
        <button className="btn" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="card muted text-center py-8">{children}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <div className="card flex flex-col gap-1 rise">
      <span className="subtle">{label}</span>
      <span className="num text-2xl font-semibold" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {hint && <span className="subtle">{hint}</span>}
    </div>
  );
}

export function Section({ title, aside, children, id }: { title: ReactNode; aside?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className="grid gap-3" id={id}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Segmented control (radio group semantics). */
export function Segmented<T extends string>({
  value, options, onChange, label,
}: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="no-scrollbar inline-flex max-w-full gap-1 overflow-x-auto rounded-2xl p-1"
      style={{ background: "var(--surface-3)", scrollSnapType: "x proximity" }}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={on}
            onClick={(e) => {
              onChange(o.value);
              e.currentTarget.scrollIntoView?.({ inline: "nearest", block: "nearest", behavior: "smooth" });
            }}
            className="shrink-0 whitespace-nowrap rounded-xl px-3 text-sm font-semibold"
            style={{
              scrollSnapAlign: "start",
              minHeight: 36,
              background: on ? "var(--surface)" : "transparent",
              color: on ? "var(--ink)" : "var(--ink-2)",
              boxShadow: on ? "0 1px 3px rgb(0 0 0 / .12)" : undefined,
              transition: "background 150ms",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Disclaimer({ text }: { text: string }) {
  return (
    <p className="subtle flex items-start gap-2">
      <TriangleAlert size={14} className="mt-1 shrink-0" aria-hidden /> {text}
    </p>
  );
}

export interface Col<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** shown as the card title on phones */
  primary?: boolean;
  /** leave out of the phone card */
  hideOnMobile?: boolean;
  className?: string;
}

/**
 * Responsive table: a real <table> from 640px up, stacked label/value cards on phones,
 * so nothing ever scrolls sideways.
 */
export function RTable<T>({ cols, rows, rowKey, empty = "Nothing to show.", stack = false }: { cols: Col<T>[]; rows: T[]; rowKey: (r: T, i: number) => string; empty?: ReactNode; /** phone cards: label above value (for long text) */ stack?: boolean }) {
  if (!rows.length) return <Empty>{empty}</Empty>;
  const primary = cols.find((c) => c.primary) ?? cols[0];
  const rest = cols.filter((c) => c !== primary && !c.hideOnMobile);
  return (
    <>
      <div className="card scroll-x hidden sm:block">
        <table className="table">
          <thead>
            <tr>{cols.map((c) => <th key={c.key}>{c.header}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={rowKey(r, i)}>{cols.map((c) => <td key={c.key} className={c.className}>{c.cell(r)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="grid gap-2 sm:hidden">
        {rows.map((r, i) => (
          <li key={rowKey(r, i)} className="card grid gap-2" style={{ padding: 14 }}>
            <div className="font-semibold">{primary.cell(r)}</div>
            {stack ? (
              <dl className="grid gap-2 text-sm">
                {rest.map((c) => (
                  <div key={c.key} className="grid gap-0.5">
                    {c.header && <dt className="subtle font-semibold">{c.header}</dt>}
                    <dd className="m-0 min-w-0 break-words">{c.cell(r)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
                {rest.map((c) => (
                  <div key={c.key} className="contents">
                    <dt className="muted">{c.header}</dt>
                    <dd className="num m-0 min-w-0 text-right break-words">{c.cell(r)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
