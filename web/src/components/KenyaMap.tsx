import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection } from "geojson";
import type { ExpressionSpecification } from "maplibre-gl";
import { Crosshair } from "lucide-react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import MapGL, { Layer, NavigationControl, Popup, ScaleControl, Source, type MapLayerMouseEvent, type MapRef } from "react-map-gl/maplibre";
import { cssVars, useTheme } from "../lib/theme";
import { useMapInsets } from "./MapFullscreen";
import type { MapLayerMode } from "../lib/mapModes";

export type { MapLayerMode };

const PROP: Record<Exclude<MapLayerMode, "priority" | "cyclone">, string> = {
  drought: "drought_level",
  observed: "observed_heavy_level",
  forecast: "forecast_heavy_level",
};

const STYLE = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};

export const KENYA_BOUNDS: [[number, number], [number, number]] = [[33.4, -5.2], [42.4, 5.4]];

interface Props {
  data: FeatureCollection;
  mode: MapLayerMode;
  highlighted?: string | null;
  selected?: string | null;
  onHover?: (county: string | null) => void;
  onSelect?: (county: string) => void;
  /** tooltip content; layerId tells county fill apart from extra layers such as storm tracks */
  tooltip?: (props: Record<string, any>, layerId: string) => ReactNode;
  height?: number | string;
  children?: ReactNode;
  fillOpacity?: number;
  /** extra layer ids (from children) that respond to hover / click */
  extraInteractive?: string[];
  onFeatureClick?: (layerId: string, props: Record<string, any>) => void;
  /** full-screen extras: "fit Kenya" button, distance scale, roomier padding */
  expanded?: boolean;
}

export function KenyaMap({
  data, mode, highlighted, selected, onHover, onSelect, tooltip, height = "100%", children, fillOpacity = 0.72,
  extraInteractive = [], onFeatureClick, expanded = false,
}: Props) {
  const theme = useTheme();
  const mapRef = useRef<MapRef>(null);
  const [hover, setHover] = useState<{ lng: number; lat: number; props: Record<string, any>; layer: string } | null>(null);
  const insets = useMapInsets();
  const padding = insets ?? (expanded ? 48 : 24);

  const colors = useMemo(
    () => cssVars(["--lvl-normal", "--lvl-watch", "--lvl-warning", "--lvl-emergency", "--lvl-none", "--accent", "--ink", "--surface"]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  );

  const fill: ExpressionSpecification = useMemo(() => {
    const levelMatch = (prop: string): ExpressionSpecification => [
      "match", ["coalesce", ["get", prop], "none"],
      "Normal", colors["--lvl-normal"],
      "Watch", colors["--lvl-watch"],
      "Warning", colors["--lvl-warning"],
      "Emergency", colors["--lvl-emergency"],
      colors["--lvl-none"],
    ];
    if (mode === "priority") {
      const maxScore = Math.max(1, ...data.features.map((f) => Number(f.properties?.priority_score ?? 0)));
      return [
        "interpolate", ["linear"], ["coalesce", ["get", "priority_score"], 0],
        0, colors["--lvl-normal"],
        maxScore * 0.25, colors["--lvl-watch"],
        maxScore * 0.6, colors["--lvl-warning"],
        maxScore, colors["--lvl-emergency"],
      ];
    }
    if (mode === "cyclone") {
      return [
        "match", ["coalesce", ["get", "cyclone_exposure_class"], "none"],
        "None recorded", colors["--lvl-normal"],
        "Low", colors["--lvl-watch"],
        "Moderate", colors["--lvl-warning"],
        "High", colors["--lvl-emergency"],
        colors["--lvl-none"],
      ];
    }
    return levelMatch(PROP[mode]);
  }, [mode, colors, data]);

  const onMove = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0];
    const layer = f?.layer?.id ?? "";
    const c = layer === "county-fill" ? ((f?.properties?.county as string) ?? null) : null;
    onHover?.(c);
    setHover(f ? { lng: e.lngLat.lng, lat: e.lngLat.lat, props: f.properties as Record<string, any>, layer } : null);
  };

  return (
    <div style={{ height, width: "100%", position: "relative" }}>
      <MapGL
        ref={mapRef}
        initialViewState={{ bounds: KENYA_BOUNDS, fitBoundsOptions: { padding } }}
        mapStyle={STYLE[theme]}
        style={{ width: "100%", height: "100%" }}
        interactiveLayerIds={[...extraInteractive, "county-fill"]}
        onMouseMove={onMove}
        onMouseLeave={() => {
          setHover(null);
          onHover?.(null);
        }}
        onClick={(e) => {
          const f = e.features?.[0];
          if (!f) return;
          if (f.layer.id === "county-fill") {
            if (f.properties?.county) onSelect?.(f.properties.county);
          } else onFeatureClick?.(f.layer.id, f.properties as Record<string, any>);
        }}
        cursor={hover ? "pointer" : "grab"}
        attributionControl={{ compact: true }}
        dragRotate={false}
        touchPitch={false}
      >
        <NavigationControl position="top-right" showCompass={false} />
        {expanded && <ScaleControl position="bottom-right" unit="metric" maxWidth={120} />}
        <Source id="counties" type="geojson" data={data}>
          <Layer id="county-fill" type="fill" paint={{ "fill-color": fill, "fill-opacity": fillOpacity }} />
          <Layer id="county-line" type="line" paint={{ "line-color": colors["--surface"], "line-width": 1 }} />
          <Layer
            id="county-hl"
            type="line"
            filter={["in", ["get", "county"], ["literal", [highlighted ?? "", selected ?? ""]]]}
            paint={{ "line-color": colors["--accent"], "line-width": 3 }}
          />
        </Source>
        {children}
        {hover && tooltip && (
          <Popup longitude={hover.lng} latitude={hover.lat} closeButton={false} closeOnClick={false} offset={12} maxWidth="260px">
            {tooltip(hover.props, hover.layer)}
          </Popup>
        )}
      </MapGL>
      <button
        onClick={() => mapRef.current?.fitBounds(KENYA_BOUNDS, { padding, duration: 600 })}
        aria-label="Fit the map to Kenya"
        title="Fit to Kenya"
        className="absolute grid place-items-center rounded-md"
        style={{ right: 10, top: 82, width: 29, height: 29, background: "#fff", color: "#333", boxShadow: "0 0 0 2px rgb(0 0 0 / .1)" }}
      >
        <Crosshair size={16} />
      </button>
    </div>
  );
}
