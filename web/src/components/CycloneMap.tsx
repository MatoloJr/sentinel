import type { FeatureCollection } from "geojson";
import { useMemo } from "react";
import { Layer, Source } from "react-map-gl/maplibre";
import type { Track } from "../lib/api";
import { cssVars, useTheme } from "../lib/theme";
import { KenyaMap } from "./KenyaMap";

interface Props {
  counties: FeatureCollection;
  tracks: Track[];
  onSelect?: (county: string) => void;
  onTrack?: (sid: string) => void;
  selectedCounty?: string | null;
  selectedTrack?: string | null;
  expanded?: boolean;
}

export default function CycloneMap({ counties, tracks, onSelect, onTrack, selectedCounty, selectedTrack, expanded }: Props) {
  const theme = useTheme();
  const col = useMemo(() => cssVars(["--accent", "--lvl-warning", "--lvl-emergency", "--ink"]), [theme]);
  const fc: FeatureCollection = useMemo(
    () => ({
      type: "FeatureCollection",
      features: tracks.map((t) => ({
        type: "Feature",
        properties: { sid: t.sid, name: t.name, season: t.season, wind: t.max_wind_kt ?? 0, basin: t.basin },
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
      expanded={expanded}
      selected={selectedCounty}
      onSelect={onSelect}
      extraInteractive={["tracks-hit"]}
      onFeatureClick={(layer, p) => layer === "tracks-hit" && onTrack?.(String(p.sid))}
      tooltip={(p, layer) =>
        layer === "tracks-hit" ? (
          <div className="text-sm">
            <b>{p.name === "NOT_NAMED" ? "Unnamed storm" : p.name}</b> · {p.season}
            <div>Peak wind {Math.round(p.wind)} kt</div>
            <div className="subtle">Tap for details</div>
          </div>
        ) : (
          <div className="text-sm">
            <b>{p.county}</b>
            <div>{p.cyclone_storms_300km ?? 0} storm(s) within 300 km since 1981</div>
            <div>Exposure: {p.cyclone_exposure_class}</div>
          </div>
        )
      }
    >
      <Source id="tracks" type="geojson" data={fc}>
        <Layer
          id="tracks-line"
          type="line"
          layout={{ "line-cap": "round", "line-join": "round" }}
          paint={{
            "line-color": ["step", ["get", "wind"], col["--accent"], 64, col["--lvl-warning"], 100, col["--lvl-emergency"]],
            "line-width": ["interpolate", ["linear"], ["get", "wind"], 34, 1.5, 100, 3.5],
            "line-opacity": selectedTrack ? 0.35 : 0.85,
          }}
        />
        <Layer
          id="tracks-selected"
          type="line"
          filter={["==", ["get", "sid"], selectedTrack ?? ""]}
          layout={{ "line-cap": "round", "line-join": "round" }}
          paint={{ "line-color": col["--ink"], "line-width": 5, "line-opacity": 0.9 }}
        />
        {/* wide invisible line so thin tracks are easy to hover and tap */}
        <Layer id="tracks-hit" type="line" paint={{ "line-color": "#000", "line-width": 14, "line-opacity": 0.001 }} />
      </Source>
    </KenyaMap>
  );
}
