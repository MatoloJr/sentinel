import type { FeatureCollection } from "geojson";
import { useMemo } from "react";
import { Layer, Source } from "react-map-gl/maplibre";
import type { Track } from "../lib/api";
import { cssVars, useTheme } from "../lib/theme";
import { KenyaMap } from "./KenyaMap";

export default function CycloneMap({ counties, tracks, onSelect }: { counties: FeatureCollection; tracks: Track[]; onSelect?: (c: string) => void }) {
  const theme = useTheme();
  const col = useMemo(() => cssVars(["--accent", "--lvl-warning", "--lvl-emergency"]), [theme]);
  const fc: FeatureCollection = useMemo(
    () => ({
      type: "FeatureCollection",
      features: tracks.map((t) => ({
        type: "Feature",
        properties: { name: t.name, season: t.season, wind: t.max_wind_kt ?? 0 },
        geometry: { type: "LineString", coordinates: t.points },
      })),
    }),
    [tracks],
  );
  return (
    <KenyaMap
      data={counties}
      mode="cyclone"
      fillOpacity={0.45}
      onSelect={onSelect}
      tooltip={(p) => (
        <div className="text-sm">
          <b>{p.county}</b>
          <div>{p.cyclone_storms_300km ?? 0} storm(s) within 300 km since 1981</div>
          <div>Exposure: {p.cyclone_exposure_class}</div>
        </div>
      )}
    >
      <Source id="tracks" type="geojson" data={fc}>
        <Layer
          id="tracks-line"
          type="line"
          layout={{ "line-cap": "round", "line-join": "round" }}
          paint={{
            "line-color": ["interpolate", ["linear"], ["get", "wind"], 34, col["--accent"], 64, col["--lvl-warning"], 100, col["--lvl-emergency"]],
            "line-width": ["interpolate", ["linear"], ["get", "wind"], 34, 1.5, 100, 3.5],
            "line-opacity": 0.85,
          }}
        />
      </Source>
    </KenyaMap>
  );
}
