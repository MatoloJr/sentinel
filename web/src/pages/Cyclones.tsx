import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useState, type CSSProperties } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Disclaimer, ErrorState, PageSkeleton, RTable, Section, Skeleton, Stat } from "../components/ui";
import { EnlargeButton, KeyList, MapFullscreen, MapKey } from "../components/MapFullscreen";
import { LAYER_KEYS, TRACK_KEY } from "../lib/mapLegends";
import type { CyclonesView, Track } from "../lib/api";
import { ArrowRight } from "lucide-react";
import { api } from "../lib/api";
import { tooltipStyle, useChartColors } from "../lib/chartColors";
import { useBreakpoint } from "../lib/useMedia";

const CycloneMap = lazy(() => import("../components/CycloneMap"));

export function Cyclones() {
  const c = useChartColors();
  const { mobile } = useBreakpoint();
  const navigate = useNavigate();
  const q = useQuery({ queryKey: ["cyclones"], queryFn: api.cyclones });
  const geo = useQuery({ queryKey: ["geo"], queryFn: api.counties });
  const seasons = q.data?.tracks.map((t) => t.season) ?? [];
  const minS = seasons.length ? Math.min(...seasons) : 1981;
  const maxS = seasons.length ? Math.max(...seasons) : 2026;
  const [from, setFrom] = useState<number | null>(null);
  const [minWind, setMinWind] = useState(34);
  const [fs, setFs] = useState(false);
  const [fsCounty, setFsCounty] = useState<string | null>(null);
  const [fsTrack, setFsTrack] = useState<string | null>(null);
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
  const filters = (
    <div className="grid gap-x-6 gap-y-3 px-1 sm:flex sm:flex-wrap sm:items-center">
      <label className="grid gap-1 text-sm">
        <span className="subtle font-semibold">From season: {start}</span>
        <input type="range" min={minS} max={maxS} value={start} onChange={(e) => setFrom(Number(e.target.value))} className="w-full sm:w-56" style={{ accentColor: "var(--accent)", minHeight: 32 }} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="subtle font-semibold">Minimum peak wind: {minWind} kt</span>
        <input type="range" min={34} max={120} step={2} value={minWind} onChange={(e) => setMinWind(Number(e.target.value))} className="w-full sm:w-56" style={{ accentColor: "var(--accent)", minHeight: 32 }} />
      </label>
    </div>
  );
  const track = d.tracks.find((t) => t.sid === fsTrack);
  const rankRow = d.ranking.find((r) => r.county === fsCounty);

  return (
    <div className="page grid gap-6">
      <header className="grid gap-2">
        <h1>Cyclone exposure</h1>
        <p className="muted max-w-[70ch]">
          Tropical storms (≥34 kt) in the IBTrACS record whose track came within {d.radius_km} km of a county since 1981.
          This is history, not a forecast: this tool never predicts a storm's path.
        </p>
      </header>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Storms shown" value={tracks.length} hint={`${start}–${maxS}`} />
        <Stat label="Counties ever within 300 km" value={exposed.length} hint="of 14" />
        <Stat label="Closest approach" value={`${Math.min(...d.ranking.map((r) => Number(r.closest_approach_km) || Infinity)).toFixed(0)} km`} />
        <Stat label="Season" value="Nov–Apr" hint="South-West Indian Ocean" />
      </div>
      <div className="card grid gap-3" style={{ padding: 12 }}>
        {filters}
        <div className="relative overflow-hidden rounded-2xl" style={{ height: "clamp(300px, 56dvh, 600px)" }}>
          {geo.data && <EnlargeButton onClick={() => setFs(true)} />}
          {geo.data ? (
            <Suspense fallback={<Skeleton h="100%" />}>
              <CycloneMap counties={geo.data} tracks={tracks} onSelect={(c) => navigate(`/county/${encodeURIComponent(c)}`)} onTrack={(sid) => { setFsCounty(null); setFsTrack(sid); setFs(true); }} />
            </Suspense>
          ) : (
            <Skeleton h="100%" />
          )}
        </div>
        <p className="subtle px-1">Line colour and width grow with peak wind. Zoom out to see storms further south.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Ranking">
          <RTable
            rows={d.ranking}
            rowKey={(r) => String(r.county)}
            cols={[
              { key: "c", header: "County", primary: true, cell: (r) => <span><span className="num muted">#{String(r.exposure_rank)} </span><Link to={`/county/${encodeURIComponent(String(r.county))}`} viewTransition>{String(r.county)}</Link></span> },
              { key: "s", header: "Storms within 300 km", className: "num", cell: (r) => String(r.tropical_storms_300km) },
              { key: "d", header: "Per decade", className: "num", cell: (r) => String(r.storms_per_decade) },
              { key: "a", header: "Closest", className: "num", cell: (r) => (r.closest_approach_km == null ? "–" : `${r.closest_approach_km} km`) },
              { key: "n", header: "Named", className: "text-sm", cell: (r) => String(r.storms_listed ?? "") || "–" },
            ]}
          />
        </Section>
        <Section title="Coastal storms per decade">
          <div className="card chart-box" style={{ "--chart-h": "300px", "--chart-h-sm": "240px" } as CSSProperties}>
            <ResponsiveContainer>
              <BarChart data={decades} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid stroke={c.grid} vertical={false} />
                <XAxis dataKey="decade" stroke={c.ink3} fontSize={mobile ? 11 : 12} />
                <YAxis allowDecimals={false} stroke={c.ink3} fontSize={mobile ? 11 : 12} width={mobile ? 28 : 40} />
                <Tooltip {...tooltipStyle(c)} />
                <Legend wrapperStyle={{ fontSize: mobile ? 11 : 12 }} />
                {coastal.map((k, i) => (
                  <Bar key={k} dataKey={k} fill={[c.accent, c.ink2, c.watch, c.ink3][i]} radius={[3, 3, 0, 0]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Section>
      </div>
      <Disclaimer text={d.note} />

      {geo.data && (
        <MapFullscreen
          open={fs}
          onClose={() => setFs(false)}
          title="Cyclone tracks"
          subtitle={`${tracks.length} storms shown · seasons ${start}–${maxS} · peak wind ≥ ${minWind} kt`}
          toolbar={filters}
          panel={
            <MapKey
              k={LAYER_KEYS.cyclone}
              asOf={`seasons ${minS}–${maxS}`}
              extra={
                <div className="grid gap-2">
                  <p className="subtle font-semibold">Storm tracks (line colour and width = peak wind)</p>
                  <KeyList items={TRACK_KEY} line />
                  <p className="subtle">
                    Only storms passing within {d.radius_km} km of a covered county are drawn. Tap a track for its name, season and
                    the counties it came close to. The selected track is drawn thicker on top.
                  </p>
                  <p className="subtle">{d.note}</p>
                </div>
              }
            />
          }
          selection={
            track ? <TrackDetails t={track} ranking={d.ranking} />
            : rankRow ? (
              <CountyExposure
                r={rankRow}
                onOpen={() => { setFs(false); navigate(`/county/${encodeURIComponent(String(rankRow.county))}`, { viewTransition: true }); }}
              />
            ) : null
          }
          onClearSelection={() => { setFsTrack(null); setFsCounty(null); }}
        >
          <Suspense fallback={<Skeleton h="100%" />}>
            <CycloneMap
              expanded
              counties={geo.data}
              tracks={tracks}
              selectedCounty={fsCounty}
              selectedTrack={fsTrack}
              onSelect={(c) => { setFsTrack(null); setFsCounty(c); }}
              onTrack={(sid) => { setFsCounty(null); setFsTrack(sid); }}
            />
          </Suspense>
        </MapFullscreen>
      )}
    </div>
  );
}

const category = (kt: number | null) =>
  kt == null ? "Unknown" : kt >= 100 ? "Intense tropical cyclone" : kt >= 64 ? "Tropical cyclone" : "Tropical storm";

function TrackDetails({ t, ranking }: { t: Track; ranking: CyclonesView["ranking"] }) {
  const tag = `${t.name} (${t.season})`;
  const near = ranking.filter((r) => String(r.storms_listed ?? "").includes(tag)).map((r) => String(r.county));
  return (
    <div className="grid gap-2 pr-6">
      <h3 className="text-lg">{t.name === "NOT_NAMED" ? "Unnamed storm" : t.name} · {t.season}</h3>
      <p className="text-sm"><b>{category(t.max_wind_kt)}</b>, peak wind {t.max_wind_kt == null ? "unknown" : `${Math.round(t.max_wind_kt)} kt (${Math.round(t.max_wind_kt * 1.852)} km/h)`}</p>
      <p className="text-sm">Basin: {t.basin === "SI" ? "South Indian Ocean" : t.basin === "NI" ? "North Indian Ocean" : t.basin}</p>
      <p className="text-sm">Came within 300 km of: {near.length ? near.join(", ") : "no covered county as a tropical storm"}</p>
      <p className="subtle">IBTrACS id {t.sid}. Historical track only, not a forecast.</p>
    </div>
  );
}

function CountyExposure({ r, onOpen }: { r: CyclonesView["ranking"][number]; onOpen: () => void }) {
  return (
    <div className="grid gap-2 pr-6">
      <h3 className="text-lg">{String(r.county)}</h3>
      <p className="text-sm"><b>{String(r.exposure_class)}</b> exposure · rank #{String(r.exposure_rank)} of 14</p>
      <p className="text-sm">{String(r.tropical_storms_300km)} tropical storm(s) within 300 km ({String(r.storms_per_decade)} per decade)</p>
      <p className="text-sm">Closest approach: {r.closest_approach_km == null ? "none recorded" : `${r.closest_approach_km} km`}</p>
      <p className="text-sm">Named storms: {String(r.storms_listed ?? "") || "none"}</p>
      <p className="subtle">Any system within 600 km (context only): {String(r.any_system_600km_context ?? "–")}</p>
      <button className="btn btn-accent justify-self-start" onClick={onOpen}>Open county <ArrowRight size={16} /></button>
    </div>
  );
}
