import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { Disclaimer, ErrorState, LevelBadge, PageSkeleton, RTable, Section, Segmented, Stat } from "../components/ui";
import { api, num, pct, type Row } from "../lib/api";
import { tooltipStyle, useChartColors } from "../lib/chartColors";
import { useBreakpoint } from "../lib/useMedia";

type Tab = "outlook" | "watch" | "skill";
const box = (h: number, hsm: number) => ({ "--chart-h": `${h}px`, "--chart-h-sm": `${hsm}px` }) as CSSProperties;
const countyLink = (c: string) => <Link to={`/county/${encodeURIComponent(c)}`} viewTransition>{c}</Link>;

export function Outlook() {
  const [tab, setTab] = useState<Tab>("outlook");
  const q = useQuery({ queryKey: ["outlook"], queryFn: api.outlook });
  const w = useQuery({ queryKey: ["watch"], queryFn: api.watch });
  if (q.isPending) return <PageSkeleton />;
  if (q.isError) return <div className="page"><ErrorState error={q.error} retry={() => q.refetch()} /></div>;
  const o = q.data;
  return (
    <div className="page grid gap-6">
      <header className="grid gap-3">
        <h1>What's likely next</h1>
        <p className="muted max-w-[70ch]">
          The 7-day watch compares the forecast with each county's own extremes. The 3-month outlook gives the chance
          of below-normal rain, and it is only trusted where it beat climatology in an 8-year test it never trained on.
        </p>
        <Segmented
          label="View"
          value={tab}
          onChange={setTab}
          options={[
            { value: "outlook", label: "3-month outlook" },
            { value: "watch", label: "7-day watch" },
            { value: "skill", label: "How good is it?" },
          ]}
        />
      </header>
      <div key={tab} className="rise grid gap-6">
        {tab === "outlook" && <LiveOutlook live={o.live} />}
        {tab === "watch" && (w.isError ? <ErrorState error={w.error} /> : <Watch rows={w.data ?? []} />)}
        {tab === "skill" && <Skill o={o} />}
      </div>
      <Disclaimer text="Seasonal forecasts are probabilities, not certainties. KMD's official seasonal outlook takes priority." />
    </div>
  );
}

function LiveOutlook({ live }: { live: Row[] }) {
  const c = useChartColors();
  const { mobile } = useBreakpoint();
  const data = live
    .filter((r) => r.prob_below_normal != null)
    .map((r) => ({ county: r.county as string, p: 100 * Number(r.prob_below_normal), skilful: !String(r.backtest_verdict).startsWith("No skill") }))
    .sort((a, b) => b.p - a.p);
  const target = live[0]?.target_months as string | undefined;
  return (
    <>
      <Section title={`Chance that ${target ?? "the next 3 months"} is in the driest third`}>
        <div className="card" style={{ height: Math.max(260, data.length * (mobile ? 26 : 30) + 40) }}>
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" margin={{ top: 4, right: mobile ? 8 : 24, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={c.grid} horizontal={false} />
              <XAxis type="number" domain={[0, 100]} unit="%" stroke={c.ink3} fontSize={mobile ? 11 : 12} />
              <YAxis type="category" dataKey="county" stroke={c.ink3} fontSize={mobile ? 11 : 12} width={mobile ? 72 : 84} />
              <Tooltip {...tooltipStyle(c)} formatter={(v: any, n: any) => [`${Math.round(Number(v))}%`, n]} />
              <ReferenceLine x={33.3} stroke={c.ink2} strokeDasharray="4 3" label={{ value: mobile ? "33%" : "normal odds 33%", fill: c.ink2, fontSize: 11, position: "top" }} />
              <Bar dataKey="p" name="Published probability" radius={[0, 4, 4, 0]}>
                {data.map((d) => <Cell key={d.county} fill={d.skilful ? c.accent : c.grid} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="subtle">Teal bars: model with tested skill. Grey bars: no tested skill, so the normal 33% is published instead.</p>
      </Section>
      <RTable
        rows={live}
        rowKey={(r) => String(r.county)}
        cols={[
          { key: "c", header: "County", primary: true, cell: (r) => countyLink(String(r.county)) },
          { key: "t", header: "Target", cell: (r) => String(r.target_months) },
          { key: "p", header: "Published", className: "num font-semibold", cell: (r) => (r.prob_below_normal == null ? "not issued" : pct(Number(r.prob_below_normal))) },
          { key: "m", header: "Model raw", className: "num muted", cell: (r) => pct(Number(r.model_raw_prob)), hideOnMobile: true },
          { key: "b", header: "Basis", className: "text-sm", cell: (r) => String(r.basis) },
          { key: "th", header: "Below normal if under", className: "num", cell: (r) => (r.below_normal_threshold_mm == null ? "–" : `${r.below_normal_threshold_mm} mm`) },
          { key: "n", header: "Normal", className: "num", cell: (r) => (r.normal_mm == null ? "–" : `${r.normal_mm} mm`), hideOnMobile: true },
        ]}
      />
    </>
  );
}

type WatchKey = "ratio" | "max_3day_total_mm" | "forecast_7day_total_mm" | "county";

function Watch({ rows }: { rows: Row[] }) {
  const [sort, setSort] = useState<WatchKey>("ratio");
  const sorted = useMemo(() => {
    const r = rows.map((x) => ({ ...x, ratio: Number(x.max_3day_total_mm) / Number(x.p99_3day_mm) })) as (Row & { ratio: number })[];
    return r.sort((a, b) => (sort === "county" ? String(a.county).localeCompare(String(b.county)) : Number(b[sort]) - Number(a[sort])));
  }, [rows, sort]);
  if (!rows.length) return <div className="card muted">No live forecast in this build (run the pipeline without --skip-forecast).</div>;
  return (
    <Section
      title={`Forecast ${String(rows[0].forecast_from)} to ${String(rows[0].forecast_to)}`}
      aside={
        <Segmented
          label="Sort by"
          value={sort}
          onChange={setSort}
          options={[
            { value: "ratio", label: "Closest to p99" },
            { value: "max_3day_total_mm", label: "Wettest 3 days" },
            { value: "forecast_7day_total_mm", label: "7-day total" },
            { value: "county", label: "A–Z" },
          ]}
        />
      }
    >
      <RTable
        rows={sorted}
        rowKey={(r) => String(r.county)}
        cols={[
          { key: "c", header: "County", primary: true, cell: (r) => <span className="flex flex-wrap items-center gap-2">{countyLink(String(r.county))}<span className="sm:hidden"><LevelBadge level={String(r.heavy_rain_level)} size="sm" /></span></span> },
          { key: "l", header: "Level", cell: (r) => <LevelBadge level={String(r.heavy_rain_level)} size="sm" />, hideOnMobile: true },
          { key: "w", header: "Wettest 3 days", className: "num", cell: (r) => <>{String(r.max_3day_total_mm)} mm <span className="subtle">({String(r.max_3day_window)})</span></> },
          {
            key: "r", header: "vs p99", cell: (r) => (
              <span className="inline-flex items-center gap-2">
                <span className="h-2 w-16 overflow-hidden rounded-full sm:w-24" style={{ background: "var(--surface-3)" }} aria-hidden>
                  <span className="block h-full rounded-full" style={{ width: `${Math.min(100, 100 * r.ratio)}%`, background: r.ratio >= 1 ? "var(--lvl-warning)" : "var(--accent)" }} />
                </span>
                <span className="num">{pct(r.ratio)}</span>
              </span>
            ),
          },
          { key: "t", header: "7-day total", className: "num", cell: (r) => `${String(r.forecast_7day_total_mm)} mm` },
          { key: "g", header: "Gusts", className: "num", cell: (r) => (r.max_gust_kmh == null ? "–" : `${r.max_gust_kmh} km/h${r.gale_gust_flag ? " gale" : ""}`) },
          { key: "h", header: "Hot days", className: "num", cell: (r) => String(r.hot_days_forecast ?? "–") },
        ]}
      />
      <p className="subtle">p99 = the 3-day total exceeded on about 1 day in 100 at this location (1991–2020). Watch ≥ p95, Warning ≥ p99, Emergency ≥ p99.9.</p>
    </Section>
  );
}

function Skill({ o }: { o: Awaited<ReturnType<typeof api.outlook>> }) {
  const c = useChartColors();
  const { mobile } = useBreakpoint();
  const fs = mobile ? 11 : 12;
  const v = o.verification;
  const perCounty = o.metrics
    .filter((m) => m.county !== "ALL (pooled)")
    .map((m) => {
      const b = Number(m.bss_model_vs_clim);
      return { county: m.county as string, bss: b, err: [b - Number(m.bss_90ci_lo), Number(m.bss_90ci_hi) - b], verdict: m.verdict as string };
    })
    .sort((a, b) => b.bss - a.bss);
  const valueData = (v?.relative_value ?? []).map((r, i) => ({ cl: r.cost_loss, model: Math.max(-0.5, r.value), persistence: Math.max(-0.5, v?.relative_value_persistence?.[i]?.value ?? NaN) }));
  return (
    <>
      <p className="card flex items-start gap-2 text-sm">
        <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
        <span>
          Model in this build: <b>{String(o.info.model_source ?? "inline selection")}</b>. Test period from {o.info.split?.test_start}; every statistic and
          threshold was learnt from earlier years only. Metric definitions are on the <Link to="/evidence" viewTransition>Evidence page</Link>.
        </span>
      </p>
      {v && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Brier skill vs climatology" value={num(v.bss, 3)} hint=">0 beats normal odds" tone={v.bss > 0 ? "var(--accent)" : "var(--lvl-warning)"} />
          <Stat label="ROC AUC" value={num(v.roc_auc, 2)} hint="0.5 = coin flip" />
          <Stat label="Calibration error" value={num(v.ece, 3)} hint="ECE · 0 = probabilities honest" />
          <Stat label="Peirce skill" value={num(v.categorical.pss, 2)} hint={`POD ${pct(v.categorical.pod)} · FAR ${pct(v.categorical.far)}`} />
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Reliability: does 60% mean 60%?">
          <div className="card chart-box" style={box(300, 260)}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 8, right: 12, left: mobile ? -16 : -8, bottom: 8 }}>
                <CartesianGrid stroke={c.grid} />
                <XAxis type="number" dataKey="mean_forecast" name="Forecast probability" domain={[0, 1]} stroke={c.ink3} fontSize={fs} tickFormatter={(x) => `${Math.round(x * 100)}%`} />
                <YAxis type="number" dataKey="observed_freq" name="Observed frequency" domain={[0, 1]} stroke={c.ink3} fontSize={fs} tickFormatter={(x) => `${Math.round(x * 100)}%`} />
                <ZAxis type="number" dataKey="n" range={mobile ? [30, 250] : [40, 400]} name="Forecasts" />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={c.ink3} strokeDasharray="4 4" />
                <ReferenceLine y={1 / 3} stroke={c.warning} strokeDasharray="2 4" />
                <Tooltip {...tooltipStyle(c)} formatter={(val: any, n: any) => [n === "Forecasts" ? val : `${Math.round(Number(val) * 100)}%`, n]} />
                <Scatter data={v?.reliability ?? []} fill={c.accent} line={{ stroke: c.accent }} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <p className="subtle">Points on the diagonal = reliable. Bubble size = number of forecasts.</p>
        </Section>
        <Section title="Is it worth acting on?">
          <div className="card chart-box" style={box(300, 260)}>
            <ResponsiveContainer>
              <LineChart data={valueData} margin={{ top: 8, right: 12, left: mobile ? -16 : -8, bottom: 14 }}>
                <CartesianGrid stroke={c.grid} />
                <XAxis dataKey="cl" stroke={c.ink3} fontSize={fs} tickFormatter={(x) => x.toFixed(1)} label={{ value: "cost of acting ÷ loss avoided", fill: c.ink3, fontSize: 11, position: "insideBottom", offset: -10 }} />
                <YAxis domain={[-0.5, 1]} stroke={c.ink3} fontSize={fs} />
                <ReferenceLine y={0} stroke={c.ink3} />
                <Tooltip {...tooltipStyle(c)} formatter={(x: any) => num(Number(x), 2)} />
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: fs }} />
                <Line dataKey="model" name="Model" stroke={c.accent} strokeWidth={2} dot={false} />
                <Line dataKey="persistence" name="Persistence" stroke={c.ink2} strokeDasharray="5 3" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="subtle">Relative economic value: above 0, acting on the forecast saves money compared with always or never preparing; 1 = as good as perfect foresight.</p>
        </Section>
      </div>
      <Section title="Skill by county (90% bootstrap interval)">
        <div className="card" style={{ height: Math.max(280, perCounty.length * (mobile ? 24 : 28) + 40) }}>
          <ResponsiveContainer>
            <BarChart data={perCounty} layout="vertical" margin={{ top: 4, right: mobile ? 8 : 24, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={c.grid} horizontal={false} />
              <XAxis type="number" stroke={c.ink3} fontSize={fs} domain={[-0.4, 0.4]} allowDataOverflow />
              <YAxis type="category" dataKey="county" stroke={c.ink3} fontSize={fs} width={mobile ? 72 : 84} />
              <ReferenceLine x={0} stroke={c.ink2} />
              <Tooltip {...tooltipStyle(c)} formatter={(x: any, _n: any, p: any) => [`${num(Number(x), 3)} · ${p.payload.verdict}`, "BSS"]} />
              <Bar dataKey="bss" name="BSS vs climatology">
                {perCounty.map((d) => <Cell key={d.county} fill={d.bss > 0 ? c.accent : c.grid} />)}
                <ErrorBar dataKey="err" width={4} stroke={c.ink2} direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Section>
      {o.by_season.length > 0 && (
        <Section title="By season">
          <RTable
            rows={o.by_season}
            rowKey={(s) => String(s.target_season)}
            cols={[
              { key: "s", header: "Season", primary: true, cell: (s) => String(s.target_season) },
              { key: "n", header: "Tests", className: "num", cell: (s) => String(s.n_test) },
              { key: "b", header: "BSS model", className: "num", cell: (s) => num(Number(s.bss_model), 3) },
              { key: "ci", header: "90% CI", className: "num", cell: (s) => String(s.bss_90ci) },
              { key: "p", header: "BSS persistence", className: "num", cell: (s) => num(Number(s.bss_persistence), 3) },
              { key: "f", header: "F1 model", className: "num", cell: (s) => num(Number(s.model_f1), 2) },
            ]}
          />
        </Section>
      )}
    </>
  );
}
