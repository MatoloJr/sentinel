import { useQuery } from "@tanstack/react-query";
import { ArrowRight, TrendingUp } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";
import type { FeatureCollection } from "geojson";
import { Link, useNavigate } from "react-router-dom";
import { InsightPanel } from "../components/InsightPanel";
import { EnlargeButton, KeyList, MapFullscreen, MapKey } from "../components/MapFullscreen";
import { LAYER_KEYS } from "../lib/mapLegends";
import type { InsightCard } from "../lib/api";
import { Sheet } from "../components/Sheet";
import { Disclaimer, ErrorState, LevelBadge, levelColor, PageSkeleton, Segmented, Skeleton, Stat } from "../components/ui";
import { api, fmtPeople, LEVEL_RANK } from "../lib/api";
import { store, useApp } from "../lib/state";
import { useBreakpoint } from "../lib/useMedia";
import { LAYER_LABEL, type MapLayerMode } from "../lib/mapModes";

const KenyaMap = lazy(() => import("../components/KenyaMap").then((m) => ({ default: m.KenyaMap })));

const LEGEND: Record<MapLayerMode, [string, string][]> = {
  priority: [["Normal", "Low"], ["Watch", ""], ["Warning", ""], ["Emergency", "Highest"]],
  drought: [["Normal", "≥75% of normal"], ["Watch", "50–75%"], ["Warning", "25–50%"], ["Emergency", "<25%"]],
  observed: [["Normal", "<p95"], ["Watch", "≥p95"], ["Warning", "≥p99"], ["Emergency", "≥p99.9"]],
  forecast: [["Normal", "<p95"], ["Watch", "≥p95"], ["Warning", "≥p99"], ["Emergency", "≥p99.9"]],
  cyclone: [["Normal", "None recorded"], ["Watch", "Low"], ["Warning", "Moderate"], ["Emergency", "High"]],
};

export function Overview() {
  const { mode } = useApp();
  return mode === "public" ? <PublicOverview /> : <ManagerOverview />;
}

function ManagerOverview() {
  const { hovered, setHovered } = useApp();
  const navigate = useNavigate();
  const [layer, setLayerState] = useState<MapLayerMode>(() => store.get("cs.layer", "priority"));
  const setLayer = (l: MapLayerMode) => {
    setLayerState(l);
    store.set("cs.layer", l);
  };
  const [selected, setSelected] = useState<string | null>(null);
  const [fs, setFs] = useState(false);
  const [fsSel, setFsSel] = useState<string | null>(null);
  const { lg } = useBreakpoint();
  const [pane, setPane] = useState<"map" | "list">("map");
  const showMap = lg || pane === "map";
  const showList = lg || pane === "list";
  const ins = useQuery({ queryKey: ["insights"], queryFn: api.insights });
  const geo = useQuery({ queryKey: ["geo"], queryFn: api.counties });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  if (ins.isPending) return <PageSkeleton />;
  if (ins.isError) return <div className="page"><ErrorState error={ins.error} retry={() => ins.refetch()} /></div>;
  const d = ins.data;
  const card = d.counties.find((c) => c.county === selected) ?? null;

  return (
    <div className="page grid gap-6">
      <header className="grid gap-2">
        <p className="subtle">
          Climate Sentinel Kenya · data to {health.data?.daily_range?.[1] ?? "…"} · forecast{" "}
          {health.data?.forecast_fetched_utc ? new Date(health.data.forecast_fetched_utc).toLocaleString() : "…"}
        </p>
        <h1>{d.region.counties_at_warning_or_above > 0 ? `${d.region.counties_at_warning_or_above} counties need action now` : "No county at Warning"}</h1>
        <p className="muted max-w-[70ch]">
          Ranked by hazard severity × people exposed. Hover a county in the list or on the map, open it for the
          drivers, what's next and the playbook actions to start.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Counties at Warning+" value={d.region.counties_at_warning_or_above} hint="of 14 covered" tone={d.region.counties_at_warning_or_above ? "var(--lvl-warning)" : undefined} />
        <Stat label="People at Warning+" value={fmtPeople(d.region.people_at_warning_or_above)} hint="WorldPop 2020" />
        <Stat label="Counties at Watch+" value={d.region.counties_at_watch_or_above} hint={`${fmtPeople(d.region.people_at_watch_or_above)} people`} />
        <Stat label="Risk rising" value={d.region.rising.length} hint={d.region.rising.slice(0, 3).join(", ") || "none"} />
      </div>

      {!lg && (
        <Segmented
          label="Show"
          value={pane}
          onChange={setPane}
          options={[{ value: "map", label: "Map" }, { value: "list", label: `Needs attention (${d.counties.filter((c) => c.overall_level !== "Normal").length})` }]}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {showMap && <div className="card grid gap-3 p-3" style={{ padding: 12 }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Segmented
              label="Map layer"
              value={layer}
              onChange={setLayer}
              options={(Object.keys(LAYER_LABEL) as MapLayerMode[]).map((k) => ({ value: k, label: LAYER_LABEL[k] }))}
            />
          </div>
          <div className="relative overflow-hidden rounded-2xl" style={{ height: "clamp(300px, 58dvh, 620px)" }}>
            {geo.data && <EnlargeButton onClick={() => { setFsSel(selected); setFs(true); }} />}
            {geo.data ? (
              <Suspense fallback={<Skeleton h="100%" />}>
                <KenyaMap
                  data={geo.data}
                  mode={layer}
                  highlighted={hovered}
                  selected={selected}
                  onHover={setHovered}
                  onSelect={setSelected}
                  tooltip={(p) => (
                    <div className="grid gap-1 text-sm">
                      <b>{p.county}</b>
                      <span>Overall: {p.overall_level} · priority #{p.priority_rank}</span>
                      <span>Drought: {p.drought_level}{p.pct_of_normal != null ? ` (${Math.round(p.pct_of_normal)}% of normal)` : ""}</span>
                      <span>Rain next 7 days: {p.forecast_heavy_level ?? "–"}</span>
                      <span className="subtle">Click for actions</span>
                    </div>
                  )}
                />
              </Suspense>
            ) : geo.isError ? (
              <ErrorState error={geo.error} />
            ) : (
              <Skeleton h="100%" />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3 px-1 text-xs" aria-label="Legend">
            {LEGEND[layer].map(([lv, label]) => (
              <span key={lv} className="flex items-center gap-1.5">
                <span className="inline-block h-3 w-3 rounded" style={{ background: levelColor(lv) }} />
                {layer === "priority" || layer === "cyclone" ? label || lv : `${lv} ${label}`}
              </span>
            ))}
          </div>
        </div>}

        {showList && <div className="grid content-start gap-3 lg:max-h-[calc(58dvh+130px)] lg:min-h-0 lg:overflow-hidden">
          <h2>Needs attention first</h2>
          <ol className="grid gap-2 lg:overflow-y-auto lg:pr-1" onMouseLeave={() => setHovered(null)}>
            {d.counties.map((c) => (
              <li key={c.county}>
                <button
                  onClick={() => setSelected(c.county)}
                  onMouseEnter={() => setHovered(c.county)}
                  onFocus={() => setHovered(c.county)}
                  className="card flex w-full items-start gap-3 text-left"
                  style={{
                    padding: 12,
                    outline: hovered === c.county ? "2px solid var(--accent)" : "none",
                    borderLeft: `6px solid ${levelColor(c.overall_level)}`,
                    transition: "outline-color 120ms",
                  }}
                >
                  <span className="num w-6 shrink-0 pt-0.5 text-right font-semibold muted">{c.priority_rank}</span>
                  <span className="grid min-w-0 flex-1 gap-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <b>{c.county}</b>
                      <LevelBadge level={c.overall_level} size="sm" />
                      {c.rising && <TrendingUp size={14} aria-label="rising" style={{ color: "var(--accent)" }} />}
                    </span>
                    <span className="text-sm muted">{c.headline}</span>
                    <span className="subtle num">
                      {fmtPeople(c.exposure.population_2020)} people · {c.actions.length} actions · score {c.priority_score}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>}
      </div>

      <Disclaimer text={d.note} />

      {geo.data && (
        <MapFullscreen
          open={fs}
          onClose={() => setFs(false)}
          title="Kenya hazard map"
          subtitle={`${LAYER_KEYS[layer].title} · weather data to ${health.data?.daily_range?.[1] ?? "…"}`}
          toolbar={
            <Segmented
              label="Map layer"
              value={layer}
              onChange={setLayer}
              options={(Object.keys(LAYER_LABEL) as MapLayerMode[]).map((k) => ({ value: k, label: LAYER_LABEL[k] }))}
            />
          }
          panel={
            <MapKey
              k={LAYER_KEYS[layer]}
              asOf={layer === "forecast" && health.data?.forecast_fetched_utc ? `forecast from ${new Date(health.data.forecast_fetched_utc).toLocaleString()}` : `data to ${health.data?.daily_range?.[1] ?? "…"}`}
              extra={<LevelCounts geo={geo.data} layer={layer} />}
            />
          }
          selection={fsSel ? (
            <FsCountyDetails
              card={d.counties.find((c) => c.county === fsSel)}
              props={geo.data.features.find((f) => f.properties?.county === fsSel)?.properties ?? {}}
              layer={layer}
              onOpen={() => { setFs(false); navigate(`/county/${encodeURIComponent(fsSel)}`, { viewTransition: true }); }}
              onActions={() => { setFs(false); setSelected(fsSel); }}
            />
          ) : null}
          onClearSelection={() => setFsSel(null)}
        >
          <Suspense fallback={<Skeleton h="100%" />}>
            <KenyaMap
              expanded
              data={geo.data}
              mode={layer}
              highlighted={hovered}
              selected={fsSel}
              onHover={setHovered}
              onSelect={setFsSel}
              tooltip={(p) => (
                <div className="grid gap-0.5 text-sm">
                  <b>{p.county}</b>
                  <span>{layerValue(layer, p)}</span>
                  <span className="subtle">Tap for details</span>
                </div>
              )}
            />
          </Suspense>
        </MapFullscreen>
      )}

      <Sheet open={!!card} onClose={() => setSelected(null)} title={card?.county ?? ""}>
        {card && (
          <div className="grid gap-4">
            <InsightPanel card={card} compact />
            <div className="flex flex-wrap gap-2">
              <button className="btn btn-accent" onClick={() => navigate(`/county/${encodeURIComponent(card.county)}`, { viewTransition: true })}>
                Open county dashboard <ArrowRight size={16} />
              </button>
              <Link className="btn" to={`/advisory?q=${encodeURIComponent(`Prepare an advisory for ${card.county} county.`)}`}>
                Draft advisory
              </Link>
            </div>
          </div>
        )}
      </Sheet>
    </div>
  );
}

function PublicOverview() {
  const q = useQuery({ queryKey: ["public"], queryFn: api.publicInsights });
  const [mine, setMineState] = useState<string>(() => store.get("cs.mine", ""));
  const setMine = (c: string) => {
    setMineState(c);
    store.set("cs.mine", c);
  };
  if (q.isPending) return <PageSkeleton />;
  if (q.isError) return <div className="page"><ErrorState error={q.error} retry={() => q.refetch()} /></div>;
  const list = [...q.data.counties].sort((a, b) => LEVEL_RANK[b.level] - LEVEL_RANK[a.level] || a.county.localeCompare(b.county));
  const my = list.find((c) => c.county === mine);
  return (
    <div className="page grid gap-6">
      <header className="grid gap-3">
        <h1>What the weather means for your area</h1>
        <p className="muted max-w-[65ch]">
          Plain-language climate alerts for 14 Kenyan counties, compared with what is normal for each place.
          Always follow the Kenya Meteorological Department and your county government.
        </p>
        <label className="grid max-w-sm gap-1">
          <span className="subtle font-semibold">Choose your county</span>
          <select className="input" value={mine} onChange={(e) => setMine(e.target.value)}>
            <option value="">Select…</option>
            {[...q.data.counties].sort((a, b) => a.county.localeCompare(b.county)).map((c) => (
              <option key={c.county}>{c.county}</option>
            ))}
          </select>
        </label>
      </header>
      {my && (
        <div className="card rise grid gap-3" style={{ borderLeft: `8px solid ${levelColor(my.level)}` }}>
          <div className="flex flex-wrap items-center gap-2">
            <h2>{my.county}</h2>
            <LevelBadge level={my.level} />
          </div>
          <p className="text-lg">{my.summary}</p>
          {my.rainy_seasons && <p className="subtle">Usual rainy seasons: {my.rainy_seasons}</p>}
          <p className="rounded-xl p-3 text-sm" style={{ background: "var(--surface)" }}>
            <b>SMS:</b> {my.sms}
          </p>
          <Link to={`/county/${encodeURIComponent(my.county)}`} className="btn justify-self-start">
            See rainfall vs normal <ArrowRight size={16} />
          </Link>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c) => (
          <button key={c.county} onClick={() => setMine(c.county)} className="card grid gap-2 text-left" style={{ borderTop: `5px solid ${levelColor(c.level)}` }}>
            <span className="flex items-center justify-between gap-2">
              <b>{c.county}</b> <LevelBadge level={c.level} size="sm" />
            </span>
            <span className="text-sm muted">{c.summary}</span>
          </button>
        ))}
      </div>
      <Disclaimer text={q.data.note} />
    </div>
  );
}

// ------------------------------------------------------------------ full-screen helpers
const LEVEL_PROP: Partial<Record<MapLayerMode, string>> = {
  drought: "drought_level", observed: "observed_heavy_level", forecast: "forecast_heavy_level",
};

/** One line describing the county's value on the active layer. */
function layerValue(layer: MapLayerMode, p: Record<string, any>): string {
  switch (layer) {
    case "priority":
      return `Priority #${p.priority_rank ?? "–"} · score ${p.priority_score ?? "–"} · ${p.overall_level ?? "–"}`;
    case "drought":
      return p.pct_of_normal == null
        ? `Drought: ${p.drought_level ?? "not assessed"} (dry season)`
        : `Drought ${p.drought_level}: ${Math.round(p.pct_of_normal)}% of normal rain (3 months to ${p.drought_window_end})`;
    case "observed":
      return `Last 7 days ${p.observed_heavy_level}: wettest 3 days ${p.observed_max_3day_mm_last7d} mm (${Math.round(100 * (p.observed_ratio_to_p99 ?? 0))}% of its 1-in-100-day level)`;
    case "forecast":
      return p.forecast_max_3day_mm == null ? "No forecast in this build" : `Next 7 days ${p.forecast_heavy_level}: up to ${p.forecast_max_3day_mm} mm in 3 days`;
    case "cyclone":
      return `${p.cyclone_exposure_class}: ${p.cyclone_storms_300km ?? 0} tropical storm(s) within 300 km since 1981`;
  }
}

/** "How many counties are in each class right now" for the active layer. */
function LevelCounts({ geo, layer }: { geo: FeatureCollection; layer: MapLayerMode }) {
  const rows = useMemo(() => {
    const counts = new Map<string, string[]>();
    for (const f of geo.features) {
      const p = f.properties ?? {};
      let k: string;
      if (layer === "priority") k = p.overall_level ?? "Normal";
      else if (layer === "cyclone") k = p.cyclone_exposure_class ?? "None recorded";
      else k = p[LEVEL_PROP[layer]!] ?? "Not assessed";
      counts.set(k, [...(counts.get(k) ?? []), p.county]);
    }
    const order = layer === "cyclone" ? ["High", "Moderate", "Low", "None recorded"] : ["Emergency", "Warning", "Watch", "Normal"];
    const toLevel: Record<string, string> = { High: "Emergency", Moderate: "Warning", Low: "Watch", "None recorded": "Normal" };
    const rank = (k: string) => (order.indexOf(k) < 0 ? 99 : order.indexOf(k));
    return [...counts.entries()]
      .sort((a, b) => rank(a[0]) - rank(b[0]))
      .map(([k, cs]) => ({
        level: layer === "cyclone" ? toLevel[k] ?? "none" : order.includes(k) ? k : "none",
        label: `${k}: ${cs.length}`,
        meaning: [...cs].sort().join(", "),
      }));
  }, [geo, layer]);
  return (
    <div className="grid gap-2">
      <p className="subtle font-semibold">{layer === "priority" ? "Counties by overall level now" : "Counties in each class now"}</p>
      <KeyList items={rows} />
    </div>
  );
}

function FsCountyDetails({ card, props, layer, onOpen, onActions }: {
  card?: InsightCard; props: Record<string, any>; layer: MapLayerMode; onOpen: () => void; onActions: () => void;
}) {
  if (!card) return <p className="muted">No details for this county.</p>;
  return (
    <div className="grid gap-3 pr-6">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg">{card.county}</h3>
        <LevelBadge level={card.overall_level} size="sm" />
        <span className="chip num">Priority #{card.priority_rank}</span>
      </div>
      <p className="text-sm font-semibold">{layerValue(layer, props)}</p>
      <div className="flex flex-wrap gap-1.5">
        {(["drought", "flood", "cyclone"] as const).map((h) => (
          <span key={h} className="chip" style={{ fontSize: 12 }}>
            {h === "flood" ? "Heavy rain" : h[0].toUpperCase() + h.slice(1)}: {card.hazard_levels[h]}
          </span>
        ))}
      </div>
      <p className="muted text-sm">{card.headline}</p>
      {card.next.outlook && <p className="text-sm"><b>Next 3 months:</b> {card.next.outlook.message}</p>}
      <p className="subtle">{fmtPeople(card.exposure.population_2020)} people · {card.actions.length} playbook actions triggered</p>
      <div className="flex flex-wrap gap-2">
        <button className="btn btn-accent" onClick={onOpen}>Open county <ArrowRight size={16} /></button>
        {card.actions.length > 0 && <button className="btn" onClick={onActions}>What to do</button>}
      </div>
    </div>
  );
}
