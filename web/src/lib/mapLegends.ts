import type { MapLayerMode } from "./mapModes";

export interface KeyItem {
  /** level name used for the colour (Normal / Watch / Warning / Emergency / none) */
  level: string;
  label: string;
  meaning: string;
}

export interface LayerKey {
  title: string;
  question: string;
  items: KeyItem[];
  /** show as a continuous ramp instead of discrete classes */
  gradient?: boolean;
  method: string[];
  source: string;
}

const NOT_ASSESSED: KeyItem = {
  level: "none",
  label: "Not assessed",
  meaning: "Dry season or no data: the normal for these months is too small (under 30 mm) to judge.",
};

const HEAVY_ITEMS = (when: string): KeyItem[] => [
  { level: "Normal", label: "Normal", meaning: `Wettest 3 days ${when} below the county's 95th percentile.` },
  { level: "Watch", label: "Watch", meaning: "At or above the 95th percentile: about 18 days a year reach this." },
  { level: "Warning", label: "Warning", meaning: "At or above the 99th percentile: about 3–4 days a year." },
  { level: "Emergency", label: "Emergency", meaning: "At or above the 99.9th percentile: roughly once every 3 years." },
];

export const LAYER_KEYS: Record<MapLayerMode, LayerKey> = {
  priority: {
    title: "Priority",
    question: "Where should attention go first?",
    gradient: true,
    items: [
      { level: "Normal", label: "Lowest", meaning: "No hazard at Watch or above." },
      { level: "Watch", label: "", meaning: "" },
      { level: "Warning", label: "", meaning: "" },
      { level: "Emergency", label: "Highest", meaning: "Most severe hazards affecting the most people." },
    ],
    method: [
      "Severity points per hazard (drought, heavy rain, cyclone season): Watch 1, Warning 3, Emergency 6, added up.",
      "Multiplied by a population weight: 1 + people ÷ 1 million (WorldPop 2020).",
      "Multiplied by 1.25 when risk is rising (forecast worse than observed, or a skilful outlook ≥ 45% dry).",
      "The colour ramp is scaled to the highest score today.",
    ],
    source: "Insight cards built from all layers below.",
  },
  drought: {
    title: "Drought",
    question: "Has the last 3 months been much drier than normal?",
    items: [
      { level: "Normal", label: "Normal", meaning: "75% of normal rain or more." },
      { level: "Watch", label: "Watch", meaning: "50–75% of normal (similar to NDMA 'Alert')." },
      { level: "Warning", label: "Warning", meaning: "25–50% of normal (similar to NDMA 'Alarm')." },
      { level: "Emergency", label: "Emergency", meaning: "Under 25% of normal (similar to NDMA 'Emergency')." },
      NOT_ASSESSED,
    ],
    method: [
      "Rain over the latest 3 complete months compared with the 1991–2020 average for the same 3 months.",
    ],
    source: "ERA5 reanalysis (ECMWF, via Open-Meteo).",
  },
  observed: {
    title: "Rain, last 7 days",
    question: "Has there just been extreme rain for this place?",
    items: HEAVY_ITEMS("in the last 7 days"),
    method: [
      "Largest 3-day rain total in the last 7 days of data, compared with the county's own 1991–2020 extremes.",
      "Each county has its own thresholds, so 30 mm can be extreme in Wajir but ordinary in Busia.",
    ],
    source: "ERA5 reanalysis (ECMWF, via Open-Meteo).",
  },
  forecast: {
    title: "Rain, next 7 days",
    question: "Is extreme rain forecast this week?",
    items: HEAVY_ITEMS("in the next 7 days"),
    method: [
      "Largest 3-day total in the 7-day forecast, compared with the same county thresholds as the observed layer.",
      "A model forecast: it cannot say exactly where rain falls within the county.",
    ],
    source: "Open-Meteo numerical weather forecast, refreshed with each pipeline run.",
  },
  cyclone: {
    title: "Cyclone exposure",
    question: "How often have tropical storms come close?",
    items: [
      { level: "Normal", label: "None recorded", meaning: "No tropical storm within 300 km since 1981." },
      { level: "Watch", label: "Low", meaning: "Fewer than 1 storm per decade." },
      { level: "Warning", label: "Moderate", meaning: "1 to 3 storms per decade." },
      { level: "Emergency", label: "High", meaning: "3 or more storms per decade." },
    ],
    method: [
      "Distinct tropical storms (winds ≥ 34 knots) whose track passed within 300 km of the county boundary.",
      "This is history only. It never predicts a storm's path.",
    ],
    source: "IBTrACS v04 best tracks, South and North Indian Ocean.",
  },
};

export const COMMON_NOTES = [
  "Weather values come from the model grid cell at each county's HQ town, not a county average.",
  "A teal outline marks the county you are pointing at or have selected.",
  "Boundaries: geoBoundaries ADM1 (simplified). Basemap © CARTO, © OpenStreetMap contributors.",
  "Planning support, not an official warning. Kenya Meteorological Department (KMD) warnings take priority.",
];

export const TRACK_KEY: KeyItem[] = [
  { level: "track-ts", label: "34–63 kt", meaning: "Tropical storm" },
  { level: "track-cy", label: "64–99 kt", meaning: "Tropical cyclone (hurricane force)" },
  { level: "track-in", label: "≥ 100 kt", meaning: "Intense tropical cyclone" },
];
