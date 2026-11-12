import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, GitCompare, MessageSquareText, Printer } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Area, Bar, Brush, CartesianGrid, ComposedChart, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { InsightPanel } from "../components/InsightPanel";
import { Disclaimer, Empty, ErrorState, LevelBadge, levelColor, PageSkeleton, RTable, Section, Segmented } from "../components/ui";
import { api, COUNTIES, fmtInt, num, type CountyDetail } from "../lib/api";
import { tooltipStyle, useChartColors } from "../lib/chartColors";
import { store, useApp } from "../lib/state";
import { useBreakpoint } from "../lib/useMedia";

const box = (h: number, hsm: number) => ({ "--chart-h": `${h}px`, "--chart-h-sm": `${hsm}px` }) as CSSProperties;

export function County() {
  const { name } = useParams();
  if (!name) return <CountyPicker />;
  return <CountyView name={decodeURIComponent(name)} />;
}

function CountyPicker() {
  const ins = useQuery({ queryKey: ["insights"], queryFn: api.insights });
  const last = store.get<string>("cs.lastCounty", "");
  const levels = Object.fromEntries((ins.data?.counties ?? []).map((c) => [c.county, c.overall_level]));
  return (
    <div className="page grid gap-6">
      <header className="grid gap-2">
        <h1>Choose a county</h1>
        <p className="muted">14 counties across the arid north-east, Lake Victoria basin, central highlands and coast.</p>
      </header>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {COUNTIES.map((c) => (
          <Link
            key={c}
            to={`/county/${encodeURIComponent(c)}`}
            className="card flex items-center justify-between gap-2"
            style={{ textDecoration: "none", color: "inherit", borderLeft: `6px solid ${levelColor(levels[c])}`, outline: c === last ? "2px solid var(--accent)" : undefined }}
          >
            <b>{c}</b>
            {levels[c] && <LevelBadge level={levels[c]} size="sm" />}
          </Link>
        ))}
      </div>
    </div>
  );
}

const RANGE = [
  { value: "24", label: "2 years" },
  { value: "60", label: "5 years" },
  { value: "180", label: "15 years" },
  { value: "480", label: "All" },
] as const;

function CountyView({ name }: { name: string }) {
  const { mode } = useApp();
  const navigate = useNavigate();
  const c = useChartColors();
  const { mobile } = useBreakpoint();
  const yW = mobile ? 40 : 60;
  const fs = mobile ? 11 : 12;
  const [months, setMonths] = useState<(typeof RANGE)[number]["value"]>("60");
  const [compare, setCompare] = useState<string>("");
  const q = useQuery({ queryKey: ["county", name, months], queryFn: () => api.county(name, Number(months)), placeholderData: (p) => p });
  const cmp = useQuery({ queryKey: ["county", compare, months], queryFn: () => api.county(compare, Number(months)), enabled: !!compare });

  useEffect(() => {
    if (q.data) store.set("cs.lastCounty", q.data.county);
  }, [q.data]);

  if (q.isPending) return <PageSkeleton />;
  if (q.isError) return <div className="page"><ErrorState error={q.error} retry={() => q.refetch()} /></div>;
  const d = q.data;
  const card = d.insight;

  return (
    <div className="page grid gap-8">
      <header className="grid gap-3">
        <button className="btn no-print justify-self-start" onClick={() => navigate("/county")}>
          <ArrowLeft size={16} /> All counties
        </button>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid gap-1">
            <p className="subtle">
              {d.meta.zone} · point at {d.meta.town} ({d.meta.lat.toFixed(2)}, {d.meta.lon.toFixed(2)})
              {d.season?.rainy_seasons ? ` · rains: ${d.season.rainy_seasons}` : ""}
            </p>
            <h1>{d.county}</h1>
          </div>
          <div className="no-print flex w-full flex-wrap gap-2 sm:w-auto">
            <label className="flex w-full items-center gap-2 sm:w-auto">
              <GitCompare size={16} aria-hidden />
              <span className="sr-only">Compare with</span>
              <select className="input sm:w-auto" value={compare} onChange={(e) => setCompare(e.target.value)}>
                <option value="">Compare with…</option>
                {COUNTIES.filter((x) => x !== d.county).map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </label>
            {mode === "manager" && (
              <Link className="btn" to={`/advisory?q=${encodeURIComponent(`Prepare an advisory for ${d.county} county.`)}`}>
                <MessageSquareText size={16} /> Draft advisory
              </Link>
            )}
            <button className="btn" onClick={() => window.print()}>
              <Printer size={16} /> Print
            </button>
          </div>
        </div>
      </header>

      {card && (
        <div className="card">
          {mode === "manager" ? (
            <InsightPanel card={card} />
          ) : (
            <div className="grid gap-2">
              <LevelBadge level={card.overall_level} />
              <p className="text-lg">{card.public.summary}</p>
              <p className="subtle">SMS: {card.public.sms}</p>
            </div>
          )}
        </div>
      )}

      {compare && cmp.data && <CompareTable a={d} b={cmp.data} />}

      <Section
        title="Monthly rainfall vs normal"
        aside={<Segmented label="Time range" value={months} onChange={setMonths} options={RANGE.map((r) => ({ ...r }))} />}
      >
        <div className="card chart-box" style={box(340, 260)}>
          <ResponsiveContainer>
            <ComposedChart data={d.monthly} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid stroke={c.grid} vertical={false} />
              <XAxis dataKey="date" stroke={c.ink3} fontSize={fs} minTickGap={mobile ? 36 : 24} />
              <YAxis stroke={c.ink3} fontSize={fs} unit={mobile ? "" : " mm"} width={yW} />
              <Tooltip {...tooltipStyle(c)} formatter={(v: any) => `${num(Number(v), 1)} mm`} />
              {!mobile && <Legend wrapperStyle={{ fontSize: 12 }} />}
              <Area dataKey="precip_p67" name="Normal range (upper third)" stroke="none" fill={c.accent} fillOpacity={0.12} isAnimationActive={false} />
              <Bar dataKey="precip" name="Observed" fill={c.accent} radius={[3, 3, 0, 0]} />
              <Line dataKey="precip_mean" name="Normal (1991–2020)" stroke={c.ink} dot={false} strokeWidth={2} />
              <Line dataKey="precip_p33" name="Below-normal line (driest third)" stroke={c.warning} dot={false} strokeDasharray="4 4" />
              {!mobile && d.monthly.length > 24 && <Brush dataKey="date" height={22} stroke={c.accent} fill={c.surface2} travellerWidth={8} />}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Section>

      {mobile && <p className="subtle -mt-6">Bars: observed · dark line: normal · dashed: below-normal line · band: normal range.</p>}

      <DroughtChart d={d} other={compare ? cmp.data : undefined} />

      <Section title="Last 90 days: 3-day rain vs the county's 1-in-100-day level">
        {d.daily_recent.length ? (
          <div className="card chart-box" style={box(260, 220)}>
            <ResponsiveContainer>
              <ComposedChart data={d.daily_recent} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="date" stroke={c.ink3} fontSize={fs} minTickGap={mobile ? 44 : 30} />
                <YAxis stroke={c.ink3} fontSize={fs} unit={mobile ? "" : " mm"} width={yW} />
                <Tooltip {...tooltipStyle(c)} formatter={(v: any) => `${num(Number(v), 1)} mm`} />
                <Bar dataKey="precip" name="Daily rain" fill={c.ink3} />
                <Line dataKey="rain_3d_mm" name="3-day total" stroke={c.accent} dot={false} strokeWidth={2} />
                <Line dataKey="p99_3day_mm" name="p99 (Warning)" stroke={c.warning} dot={false} strokeDasharray="5 4" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <Empty>No recent daily data.</Empty>
        )}
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Long-term trends (Mann–Kendall + Sen's slope)">
          <RTable
            rows={[...d.trends, ...d.extremes_trends]}
            rowKey={(_, i) => String(i)}
            cols={[
              { key: "v", header: "Variable", primary: true, cell: (t) => String(t.variable).replaceAll("_", " ") },
              { key: "s", header: "Change / decade", className: "num", cell: (t) => `${num(t.sen_slope_per_decade as number, 2)} ${String(t.unit ?? "")}` },
              { key: "p", header: "p-value", className: "num", cell: (t) => num(t.p_value as number, 3) },
              { key: "g", header: "Significant", cell: (t) => (String(t.significant_5pct) === "true" ? "Yes" : "No") },
            ]}
          />
        </Section>
        <Section title="Worst events on record">
          <div className="card grid gap-2">
            {d.worst_events.length ? (
              d.worst_events.map((w, i) => (
                <div key={i} className="flex items-center justify-between gap-3 text-sm">
                  <span className="capitalize">{String(w.hazard).replace("_", " ")} · {String(w.when)}</span>
                  <span className="num muted">{String(w.value)}</span>
                </div>
              ))
            ) : (
              <p className="muted">No events listed.</p>
            )}
            <hr style={{ borderColor: "var(--surface-3)" }} />
            <KeyVals
              rows={[
                ["Population (2020)", fmtInt(d.population?.population_2020 as number)],
                ["Census 2019 check", fmtInt(d.population?.census_2019 as number)],
                ["Heavy rain p95 / p99 / p99.9 (3-day)", `${num(d.heavy_thresholds?.p95_3day_mm as number, 0)} / ${num(d.heavy_thresholds?.p99_3day_mm as number, 0)} / ${num(d.heavy_thresholds?.["p99.9_3day_mm"] as number, 0)} mm`],
                ["Hot-day threshold (apparent Tmax p95)", d.heat_threshold_c != null ? `${d.heat_threshold_c.toFixed(1)} °C` : "–"],
                ["Tropical storms within 300 km since 1981", String(d.cyclone?.tropical_storms_300km ?? "–")],
              ]}
            />
          </div>
        </Section>
      </div>
      <Disclaimer text="Rainfall is the ERA5 reanalysis at the county HQ point (a model estimate, not a rain gauge). Official KMD warnings take priority." />
    </div>
  );
}

function KeyVals({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid gap-1.5 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-3">
          <dt className="muted">{k}</dt>
          <dd className="num m-0 text-right font-semibold">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function DroughtChart({ d, other }: { d: CountyDetail; other?: CountyDetail }) {
  const c = useChartColors();
  const { mobile } = useBreakpoint();
  const data = useMemo(() => {
    const o = new Map((other?.drought ?? []).map((r) => [r.date, r.pct_of_normal]));
    return d.drought.slice(-Math.max(d.monthly.length, 24)).map((r) => ({ date: r.date, pct: r.pct_of_normal, other: o.get(r.date) ?? null }));
  }, [d, other]);
  return (
    <Section title="Drought indicator: 3-month rain as % of normal">
      <div className="card chart-box" style={box(300, 240)}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <ReferenceArea y1={0} y2={25} fill={c.emergency} fillOpacity={0.14} />
            <ReferenceArea y1={25} y2={50} fill={c.warning} fillOpacity={0.14} />
            <ReferenceArea y1={50} y2={75} fill={c.watch} fillOpacity={0.14} />
            <ReferenceLine y={100} stroke={c.ink3} strokeDasharray="3 3" label={{ value: "normal", fill: c.ink3, fontSize: 11, position: "insideTopRight" }} />
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis dataKey="date" stroke={c.ink3} fontSize={mobile ? 11 : 12} minTickGap={mobile ? 36 : 24} />
            <YAxis stroke={c.ink3} fontSize={mobile ? 11 : 12} unit="%" domain={[0, (max: number) => Math.min(300, Math.max(150, max))]} allowDataOverflow width={mobile ? 44 : 56} />
            <Tooltip {...tooltipStyle(c)} formatter={(v: any) => (v == null ? "dry season" : `${Math.round(Number(v))}%`)} />
            {(other || !mobile) && <Legend wrapperStyle={{ fontSize: mobile ? 11 : 12 }} />}
            <Line dataKey="pct" name={d.county} stroke={c.accent} dot={false} strokeWidth={2} connectNulls={false} />
            {other && <Line dataKey="other" name={other.county} stroke={c.ink2} dot={false} strokeWidth={1.5} strokeDasharray="5 3" />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="subtle">Bands: Watch 50–75%, Warning 25–50%, Emergency below 25%. Gaps are dry seasons, where drought is not judged.</p>
    </Section>
  );
}

function CompareTable({ a, b }: { a: CountyDetail; b: CountyDetail }) {
  const rows: [string, (x: CountyDetail) => string][] = [
    ["Overall level", (x) => x.insight?.overall_level ?? "–"],
    ["Drought (3-month % of normal)", (x) => (x.status?.pct_of_normal != null ? `${x.status.pct_of_normal}%` : "dry season")],
    ["Heavy rain observed", (x) => String(x.status?.observed_heavy_level ?? "–")],
    ["Heavy rain forecast", (x) => String(x.status?.forecast_heavy_level ?? "–")],
    ["Seasonal outlook", (x) => (x.outlook?.prob_below_normal != null ? `${Math.round(100 * Number(x.outlook.prob_below_normal))}% below-normal (${x.outlook.backtest_verdict})` : "–")],
    ["People", (x) => fmtInt(x.population?.population_2020 as number)],
    ["Priority rank", (x) => String(x.insight?.priority_rank ?? "–")],
  ];
  return (
    <Section title={`${a.county} vs ${b.county}`}>
      <RTable
        rows={rows}
        rowKey={([k]) => k}
        cols={[
          { key: "k", header: "", primary: true, cell: ([k]) => k },
          { key: "a", header: a.county, className: "num", cell: ([, f]) => f(a) },
          { key: "b", header: b.county, className: "num", cell: ([, f]) => f(b) },
        ]}
      />
    </Section>
  );
}

