import { ArrowUpRight, CheckCircle2, Circle, Copy, TrendingDown, TrendingUp, Users } from "lucide-react";
import { useState } from "react";
import { fmtInt, type InsightCard } from "../lib/api";
import { useChecklist } from "../lib/state";
import { LevelBadge } from "./ui";

const HZ: Record<string, string> = { drought: "Drought", flood: "Heavy rain", cyclone: "Cyclone" };

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked */
        }
      }}
    >
      <Copy size={16} aria-hidden /> {done ? "Copied" : label}
    </button>
  );
}

/** What is happening -> what's next -> who is exposed -> what to do. */
export function InsightPanel({ card, compact = false }: { card: InsightCard; compact?: boolean }) {
  const { done, toggle } = useChecklist(card.county);
  const [showAll, setShowAll] = useState(!compact);
  const acts = showAll ? card.actions : card.actions.slice(0, 4);
  const doneN = card.actions.filter((a) => done[a.id]).length;
  const fc = card.next.forecast;
  const ol = card.next.outlook;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <LevelBadge level={card.overall_level} />
        <span className="chip num">Priority #{card.priority_rank}</span>
        {card.rising && (
          <span className="chip" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            <TrendingUp size={14} aria-hidden /> Rising
          </span>
        )}
      </div>
      <p className="text-lg font-semibold">{card.headline}</p>

      <div className="grid gap-3 sm:grid-cols-3">
        {(["drought", "flood", "cyclone"] as const).map((h) => (
          <div key={h} className="rounded-2xl p-3" style={{ background: "var(--surface)" }}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="subtle font-semibold">{HZ[h]}</span>
              <LevelBadge level={card.hazard_levels[h]} size="sm" />
            </div>
            <p className="text-sm">{card.drivers.find((d) => d.hazard === h)?.text ?? "Not in season / no recorded exposure"}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl p-3" style={{ background: "var(--surface)" }}>
          <p className="subtle font-semibold">Next 7 days</p>
          {fc ? (
            <p className="text-sm">
              Up to <b className="num">{fc.max_3day_mm} mm</b> in 3 days ({fc.window}); county 1-in-100-day level is{" "}
              <span className="num">{fc.p99_3day_mm} mm</span>.
              {fc.gale_gusts ? ` Gale-force gusts to ${fc.max_gust_kmh} km/h.` : ""}
              {fc.hot_days ? ` ${fc.hot_days} unusually hot day(s).` : ""}
            </p>
          ) : (
            <p className="text-sm muted">Forecast unavailable.</p>
          )}
        </div>
        <div className="rounded-2xl p-3" style={{ background: "var(--surface)" }}>
          <p className="subtle font-semibold">Next 3 months</p>
          <p className="text-sm">{ol?.message ?? "Seasonal outlook unavailable."}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span className="flex items-center gap-2">
          <Users size={16} aria-hidden /> <b className="num">{fmtInt(card.exposure.population_2020)}</b> people (
          {card.exposure.share_of_region_pct}% of the 14 counties)
        </span>
        {card.trend && (
          <span className="flex items-center gap-2">
            {(card.trend.slope_mm_per_decade ?? 0) < 0 ? <TrendingDown size={16} aria-hidden /> : <TrendingUp size={16} aria-hidden />}
            Annual rain {card.trend.slope_mm_per_decade! > 0 ? "+" : ""}
            {card.trend.slope_mm_per_decade} mm/decade ({card.trend.significant ? "significant" : "not significant"}, p=
            {card.trend.p_value})
          </span>
        )}
      </div>

      <div className="grid gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3>What to do</h3>
          {card.actions.length > 0 && (
            <span className="subtle num">
              {doneN}/{card.actions.length} started on this device
            </span>
          )}
        </div>
        {card.actions.length === 0 ? (
          <p className="muted text-sm">No hazard actions are triggered. Keep routine monitoring and follow KMD forecasts.</p>
        ) : (
          <ul className="grid gap-1.5">
            {acts.map((a) => {
              const on = !!done[a.id];
              return (
                <li key={a.id}>
                  <button
                    onClick={() => toggle(a.id)}
                    aria-pressed={on}
                    className="flex w-full items-start gap-3 rounded-xl p-2.5 text-left"
                    style={{ background: on ? "var(--accent-soft)" : "var(--surface)", minHeight: 44, transition: "background 150ms" }}
                  >
                    {on ? <CheckCircle2 size={20} className="shrink-0" style={{ color: "var(--accent)" }} /> : <Circle size={20} className="shrink-0 muted" />}
                    <span className="grid min-w-0 gap-0.5">
                      <span className={on ? "line-through opacity-70" : ""}>{a.action}</span>
                      <span className="subtle">
                        <span className="num font-semibold">{a.id}</span> · {HZ[a.hazard]} {a.level} · {a.timeframe}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {card.actions.length > 4 && compact && (
          <button className="btn justify-self-start" onClick={() => setShowAll((s) => !s)}>
            {showAll ? "Show fewer" : `Show all ${card.actions.length} actions`}
          </button>
        )}
        {card.actions.length > 0 && (
          <p className="subtle">
            Actions come only from the cited playbook ({card.actions[0].source}
            {card.actions[0].source_url && (
              <>
                {" "}
                <a href={card.actions[0].source_url} target="_blank" rel="noreferrer">
                  source <ArrowUpRight size={12} className="inline" />
                </a>
              </>
            )}
            ).
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <CopyButton text={card.public.sms} label="Copy SMS" />
        <span className="subtle num">{card.public.sms.length}/160 · “{card.public.sms}”</span>
      </div>
    </div>
  );
}
