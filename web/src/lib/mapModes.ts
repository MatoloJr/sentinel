export type MapLayerMode = "priority" | "drought" | "observed" | "forecast" | "compound" | "cyclone";

export const LAYER_LABEL: Record<MapLayerMode, string> = {
  priority: "Priority",
  drought: "Drought",
  observed: "Rain (last 7 days)",
  forecast: "Rain (next 7 days)",
  compound: "Rain after drought",
  cyclone: "Cyclone exposure",
};
