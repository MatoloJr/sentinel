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
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-2xl p-1" style={{ background: "var(--surface-3)" }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className="rounded-xl px-3 text-sm font-semibold"
            style={{
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
