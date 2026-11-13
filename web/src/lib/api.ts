// Typed client for the FastAPI backend (/api/*). Shapes mirror sentinel/api/main.py.
import type { FeatureCollection } from "geojson";

export type Level = "Normal" | "Watch" | "Warning" | "Emergency";
export type Hazard = "drought" | "flood" | "cyclone";

export interface Action {
  id: string;
  hazard: Hazard;
  level: Level;
  action: string;
  timeframe: string;
  source: string;
  source_url?: string;
  section?: string;
  /** brought forward by the rain-after-drought (compound) alert */
  compound?: boolean;
}

/** Rain after drought (drought-to-flood whiplash): heavy rain arriving on drought-hit land. */
export interface Compound {
  type: "drought_to_flood";
  label: string;
  level: Level;
  headline: string;
  message: string;
  trigger: "forecast" | "observed" | null;
  trigger_3day_mm: number | null;
  antecedent_12m_pct: number;
  antecedent_12m_mm: number | null;
  antecedent_12m_normal_mm: number | null;
  deficit_12m_mm: number | null;
  antecedent_window_end: string | null;
  recovery: null | { deficit_12m_mm: number; forecast_7day_mm: number; share_of_deficit_pct: number | null; text: string };
  history: null | {
    p99_rain_days: number | null;
    p99_rain_days_on_drought_land: number | null;
    share_on_drought_land_pct: number | null;
    episodes_since_1991: number | null;
    episodes_warning_plus: number | null;
    last_episode: string | null;
    recent_episodes?: Row[];
  };
  rule: string;
  action_ids?: string[];
}

export interface WhiplashView {
  rule: { antecedent_months: number; dry_pct: number; rain_levels: Record<string, number> };
  documented_events: Record<string, unknown>[];
  validation: Row[];
  stats: Record<string, number | null>;
  sensitivity: Row[];
  summary: Row[];
  episodes: Row[];
}

/** Our drought level vs NDMA's official county drought phase (Normal / Alert / Alarm / Emergency). */
export interface NdmaView {
  agreement: Row[];
  overall: Record<string, string | number | null | Record<string, string>>;
}

export interface Driver {
  hazard: Hazard;
  level: string;
  text: string;
  value: number | null;
  unit: string | null;
}

export interface InsightCard {
  county: string;
  zone: string;
  overall_level: Level;
  headline: string;
  hazard_levels: Record<Hazard, Level>;
  /** level of the compound rain-after-drought alert (Normal when none) */
  compound_level?: Level;
  compound?: Compound | null;
  drivers: Driver[];
  trend: null | {
    variable: string;
    slope_mm_per_decade: number | null;
    change_pct_of_mean: number | null;
    p_value: number | null;
    significant: boolean;
    years: string;
  };
  significant_extreme_trends: { variable: string; unit: string; slope_per_decade: number; p_value: number }[];
  next: {
    forecast: null | {
      level: Level;
      max_3day_mm: number;
      window: string;
      total_7day_mm: number;
      p99_3day_mm: number;
      gale_gusts: boolean | null;
      max_gust_kmh: number | null;
      hot_days: number | null;
      fetched_utc: string;
    };
    outlook: null | {
      target_months: string;
      prob_below_normal: number | null;
      skilful: boolean;
      verdict: string;
      confidence: string;
      model_raw_prob: number;
      message: string;
    };
  };
  rising: boolean;
  exposure: { population: number; population_source?: string; share_of_region_pct: number; people_at_watch_or_above: number };
  priority_score: number;
  priority_rank: number;
  priority_explained: string;
  actions: Action[];
  rainy_seasons: string | null;
  public: { summary: string; sms: string; level: Level };
}

export interface Insights {
  generated_for: string;
  region: {
    counties_at_watch_or_above: number;
    counties_at_warning_or_above: number;
    people_at_watch_or_above: number;
    people_at_warning_or_above: number;
    rising: string[];
    top_priorities: string[];
    whiplash?: string[];
    drought_hit_land?: string[];
  };
  counties: InsightCard[];
  note: string;
}

export interface PublicCard {
  county: string;
  zone: string;
  level: Level;
  headline: string;
  summary: string;
  sms: string;
  rainy_seasons: string | null;
}

export interface Health {
  ok: boolean;
  built_utc: string | null;
  daily_range: [string, string] | null;
  data_lag_days: number | null;
  forecast_fetched_utc: string | null;
  latest_complete_month: string | null;
  gemini_configured: boolean;
  official_note: string;
  cyclone_centres: string;
}

export type Row = Record<string, string | number | boolean | null>;

export interface CountyDetail {
  county: string;
  meta: { town: string; lat: number; lon: number; zone: string; coastal: boolean };
  status: Row | null;
  insight: InsightCard | null;
  monthly: { date: string; precip: number; tmax: number; tmean: number; precip_mean: number; precip_p33: number; precip_p67: number }[];
  drought: { date: string; rain_3m_mm: number; normal_3m_mm: number; pct_of_normal: number | null; level: string }[];
  daily_recent: { date: string; precip: number; rain_3d_mm: number; p99_3day_mm: number; level: string }[];
  trends: Row[];
  extremes_trends: Row[];
  extremes: Row[];
  worst_events: Row[];
  season: Row | null;
  heavy_thresholds: Row | null;
  heat_threshold_c: number | null;
  outlook: Row | null;
  outlook_backtest: Row | null;
  watch: Row | null;
  cyclone: Row | null;
  population: Row | null;
}

export interface Verification {
  n: number;
  brier: number;
  bss: number;
  roc_auc: number;
  pr_auc: number;
  ece: number;
  threshold: number;
  categorical: Record<string, number>;
  reliability: { bin_lo: number; bin_hi: number; n: number; mean_forecast: number; observed_freq: number }[];
  relative_value: { cost_loss: number; value: number; best_threshold: number }[];
  relative_value_persistence: { cost_loss: number; value: number }[];
}

export interface OutlookView {
  live: Row[];
  metrics: Row[];
  by_season: Row[];
  info: Record<string, unknown> & { model_source?: string; split?: Record<string, string> };
  verification: Verification | null;
}

export interface Track {
  sid: string;
  name: string;
  season: number;
  basin: string;
  max_wind_kt: number | null;
  points: [number, number][];
}

export interface CyclonesView {
  ranking: Row[];
  per_decade: Row[];
  per_season: Row[];
  tracks: Track[];
  radius_km: number;
  note: string;
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
  at_utc: string;
  ms: number;
}

export interface AgentRun {
  run_id: string;
  question: string;
  model: string;
  started_utc: string;
  finished_utc?: string;
  tool_calls: ToolCall[];
  answer_draft: string;
  advisory: string;
  validation: { passed: boolean; issues: string[]; numbers_checked: number };
  status: "draft" | "blocked" | "approved" | "rejected";
  approval: Record<string, string> | null;
}

export interface RunSummary {
  run_id: string;
  question: string;
  status: AgentRun["status"];
  started_utc: string;
  model: string;
  validation_passed: boolean;
  n_tool_calls: number;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : body.detail?.message ?? JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<Health>("/api/health"),
  meta: () => req<Record<string, unknown>>("/api/meta"),
  counties: () => req<FeatureCollection>("/api/counties"),
  insights: () => req<Insights>("/api/insights"),
  publicInsights: () => req<{ counties: PublicCard[]; note: string; generated_for: string }>("/api/insights?audience=public"),
  county: (name: string, months = 36) => req<CountyDetail>(`/api/county/${encodeURIComponent(name)}?months=${months}`),
  outlook: () => req<OutlookView>("/api/outlook"),
  watch: () => req<Row[]>("/api/watch"),
  cyclones: () => req<CyclonesView>("/api/cyclones"),
  validation: () => req<{ events: Row[]; reference_events: Record<string, unknown>[]; drought_class_frequency: Row[] }>("/api/validation"),
  whiplash: () => req<WhiplashView>("/api/whiplash"),
  ndma: () => req<NdmaView>("/api/ndma"),
  model: () => req<{ active: Record<string, any> | null; registry: { active: string | null; history: Row[] }; pipeline_model_source?: string; pipeline_selection?: Record<string, any> }>("/api/model"),
  ask: (question: string) => req<AgentRun>("/api/agent/ask", { method: "POST", body: JSON.stringify({ question }) }),
  runs: () => req<RunSummary[]>("/api/agent/runs"),
  run: (id: string) => req<AgentRun>(`/api/agent/runs/${id}`),
  approve: (id: string, approver: string, note = "") =>
    req<AgentRun>(`/api/agent/runs/${id}/approve`, { method: "POST", body: JSON.stringify({ approver, note }) }),
  reject: (id: string, approver: string, note = "") =>
    req<AgentRun>(`/api/agent/runs/${id}/reject`, { method: "POST", body: JSON.stringify({ approver, note }) }),
  agentMetrics: () => req<Record<string, number | null>>("/api/agent/metrics"),
};

export const COUNTIES = [
  "Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", "Makueni",
  "Nairobi", "Kisumu", "Busia", "Lamu", "Kilifi", "Mombasa", "Kwale",
];

export const LEVEL_RANK: Record<string, number> = { Normal: 0, Watch: 1, Warning: 2, Emergency: 3 };

export const fmtInt = (n: number | null | undefined) =>
  n == null ? "–" : new Intl.NumberFormat("en-KE").format(Math.round(n));
export const fmtPeople = (n: number | null | undefined) => {
  if (n == null) return "–";
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`;
  return String(Math.round(n));
};
export const pct = (x: number | null | undefined, d = 0) => (x == null ? "–" : `${(100 * x).toFixed(d)}%`);
export const num = (x: number | null | undefined, d = 2) => (x == null || Number.isNaN(x) ? "–" : x.toFixed(d));
