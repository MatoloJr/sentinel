import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Disclaimer, ErrorState, PageSkeleton, Section, Skeleton, Stat } from "../components/ui";
import { api } from "../lib/api";
import { tooltipStyle, useChartColors } from "../lib/chartColors";

const CycloneMap = lazy(() => import("../components/CycloneMap"));

export function Cyclones() {
  const c = useChartColors();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["cyclones"], queryFn: api.cyclones });
  const geo = useQuery({ queryKey: ["geo"], queryFn: api.counties });
  const seasons = q.data?.tracks.map((t) => t.season) ?? [];
  const minS = seasons.length ? Math.min(...seasons) : 1981;
  const maxS = seasons.length ? Math.max(...seasons) : 2026;
  const [from, setFrom] = useState<number | null>(null);
  const [minWind, setMinWind] = useState(34);
  const start = from ?? minS;
  const tracks = useMemo(
    () => (q.data?.tracks ?? []).filter((t) => t.season >= start && (t.max_wind_kt ?? 0) >= minWind),
    [q.data, start, minWind],
  );
  const decades = useMemo(() => {
    const m = new Map<string, Record<string, number | string>>();
    for (const r of q.data?.per_decade ?? []) {
      const k = String(r.decade_label);
      const row = m.get(k) ?? { decade: k };
      row[String(r.county)] = Number(r.storms);
      m.set(k, row);
    }
    return [...m.values()];
  }, [q.data]);
  const coastal = ["Lamu", "Kilifi", "Mombasa", "Kwale"];

  if (q.isPending) return <PageSkeleton />;
  if (q.isError) return <div className="page"><ErrorState error={q.error} retry={() => q.refetch()} /></div>;
  const d = q.data;
  const exposed = d.ranking.filter((r) => Number(r.tropical_storms_300km) > 0);

  return (
    <div className="page grid gap-6">
      <header className="grid gap-2">
        <h1>Cyclone exposure</h1>
        <p className="muted max-w-[70ch]">
          Tropical storms (≥34 kt) in the IBTrACS record whose track came within {d.radius_km} km of a county since 1981.
          This is history, not a forecast: this tool never predicts a storm's path.
        </p>
      </header>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Storms shown" value={tracks.length} hint={`${start}–${maxS}`} />
        <Stat label="Counties ever within 300 km" value={exposed.length} hint="of 14" />
        <Stat label="Closest approach" value={`${Math.min(...d.ranking.map((r) => Number(r.closest_approach_km) || Infinity)).toFixed(0)} km`} />
        <Stat label="Season" value="Nov–Apr" hint="South-West Indian Ocean" />
      </div>
      <div className="card grid gap-3" style={{ padding: 12 }}>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-1">
          <label className="grid gap-1 text-sm">
            <span className="subtle font-semibold">From season: {start}</span>
            <input type="range" min={minS} max={maxS} value={start} onChange={(e) => setFrom(Number(e.target.value))} style={{ accentColor: "var(--accent)", minWidth: 180 }} />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="subtle font-semibold">Minimum peak wind: {minWind} kt</span>
            <input type="range" min={34} max={120} step={2} value={minWind} onChange={(e) => setMinWind(Number(e.target.value))} style={{ accentColor: "var(--accent)", minWidth: 180 }} />
          </label>
        </div>
        <div className="overflow-hidden rounded-2xl" style={{ height: "min(60vh, 520px)", minHeight: 320 }}>
          {geo.data ? (
            <Suspense fallback={<Skeleton h="100%" />}>
              <CycloneMap counties={geo.data} tracks={tracks} onSelect={(c) => navigate(`/county/${encodeURIComponent(c)}`)} />
            </Suspense>
          ) : (
            <Skeleton h="100%" />
          )}
        </div>
        <p className="subtle px-1">Line colour and width grow with peak wind. Zoom out to see storms further south.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Ranking">
          <div className="card scroll-x">
            <table className="table">
              <thead><tr><th>#</th><th>County</th><th>Storms ≤300 km</th><th>Per decade</th><th>Closest</th><th>Named</th></tr></thead>
              <tbody>
                {d.ranking.map((r) => (
                  <tr key={String(r.county)}>
                    <td className="num">{String(r.exposure_rank)}</td>
                    <td><Link to={`/county/${encodeURIComponent(String(r.county))}`}>{String(r.county)}</Link></td>
                    <td className="num">{String(r.tropical_storms_300km)}</td>
                    <td className="num">{String(r.storms_per_decade)}</td>
                    <td className="num">{r.closest_approach_km == null ? "–" : `${r.closest_approach_km} km`}</td>
                    <td className="text-sm">{String(r.storms_listed ?? "") || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
        <Section title="Coastal storms per decade">
          <div className="card" style={{ height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={decades} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="decade" stroke={c.ink3} fontSize={12} />
                <YAxis allowDecimals={false} stroke={c.ink3} fontSize={12} />
                <Tooltip {...tooltipStyle(c)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {coastal.map((k, i) => (
                  <Bar key={k} dataKey={k} fill={[c.accent, c.ink2, c.watch, c.ink3][i]} radius={[3, 3, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Section>
      </div>
      <Disclaimer text={d.note} />
    </div>
  );
}
