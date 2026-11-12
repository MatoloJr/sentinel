"""County polygons, projected distance/area work, cyclone exposure and population exposure."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from . import config as C

GEO_CRS = "EPSG:4326"
# Azimuthal equidistant projection centred on Kenya: distances from the centre are exact and
# distortion stays small across the region and the nearby Indian Ocean. Used for the 300 km test.
KENYA_AEQD = "+proj=aeqd +lat_0=0.5 +lon_0=38.5 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
EQUAL_AREA = "EPSG:6933"  # World Cylindrical Equal Area, for km2


def load_counties(boundaries_path) -> gpd.GeoDataFrame:
    """Select our 14 counties from the ADM1 file by point-in-polygon on each HQ town.
    This avoids depending on exact county name spellings in the source file."""
    adm = gpd.read_file(boundaries_path).to_crs(GEO_CRS)
    pts = gpd.GeoDataFrame(
        {"county": C.COUNTY_NAMES, "town": [c.town for c in C.COUNTIES],
         "zone": [c.zone for c in C.COUNTIES], "coastal": [c.coastal for c in C.COUNTIES],
         "lat": [c.lat for c in C.COUNTIES], "lon": [c.lon for c in C.COUNTIES]},
        geometry=[Point(c.lon, c.lat) for c in C.COUNTIES], crs=GEO_CRS)
    j = gpd.sjoin(pts, adm[["geometry"] + [c for c in adm.columns if c.lower().startswith("shape")]],
                  how="left", predicate="within")
    missing = j[j["index_right"].isna()]["county"].tolist()
    if missing:  # HQ point just outside a simplified coastline -> nearest polygon
        for name in missing:
            p = pts[pts["county"] == name].geometry.iloc[0]
            j.loc[j["county"] == name, "index_right"] = adm.to_crs(KENYA_AEQD).distance(
                gpd.GeoSeries([p], crs=GEO_CRS).to_crs(KENYA_AEQD).iloc[0]).idxmin()
    j["index_right"] = j["index_right"].astype(int)
    g = gpd.GeoDataFrame(j.drop(columns="geometry"),
                         geometry=adm.loc[j["index_right"]].geometry.values, crs=GEO_CRS)
    g["area_km2"] = g.to_crs(EQUAL_AREA).area / 1e6
    return g.drop(columns=["index_right"]).reset_index(drop=True)


# ---------------------------------------------------------------- population
def population_by_county(counties: gpd.GeoDataFrame, raster_path) -> pd.DataFrame:
    """Sum the WorldPop raster inside each county polygon (counts, so no reprojection needed)."""
    import rasterio
    from rasterio.mask import mask

    rows = []
    with rasterio.open(raster_path) as src:
        polys = counties.to_crs(src.crs)
        for name, geom in zip(polys["county"], polys.geometry):
            arr, _ = mask(src, [geom.__geo_interface__], crop=True, filled=True, nodata=src.nodata)
            a = arr[0].astype("float64")
            if src.nodata is not None:
                a[a == src.nodata] = 0
            a[~np.isfinite(a) | (a < 0)] = 0
            rows.append({"county": name, "population_2020": float(a.sum())})
    pop = pd.DataFrame(rows)
    pop["census_2019"] = pop["county"].map(C.CENSUS_2019)
    pop["worldpop_vs_census_pct"] = 100 * (pop["population_2020"] / pop["census_2019"] - 1)
    return pop


def people_by_level(status: pd.DataFrame, pop: pd.DataFrame, level_col: str) -> pd.DataFrame:
    s = status[["county", level_col]].merge(pop[["county", "population_2020"]], on="county")
    t = s.groupby(level_col).agg(counties=("county", lambda x: ", ".join(sorted(x))),
                                 n_counties=("county", "size"), people=("population_2020", "sum"))
    return t.reset_index().rename(columns={level_col: "level"})


# ---------------------------------------------------------------- cyclones
def cyclone_points_near(ib: pd.DataFrame, counties: gpd.GeoDataFrame,
                        radius_km: float) -> pd.DataFrame:
    """All IBTrACS track points within radius_km of each county polygon (projected CRS)."""
    pts = gpd.GeoDataFrame(ib.copy(), geometry=gpd.points_from_xy(ib["LON"], ib["LAT"]), crs=GEO_CRS)
    pts = pts.to_crs(KENYA_AEQD)
    poly = counties.to_crs(KENYA_AEQD)[["county", "geometry"]]
    buf = poly.copy()
    buf["geometry"] = poly.buffer(radius_km * 1000)
    j = gpd.sjoin(pts, buf, how="inner", predicate="within")
    if j.empty:
        return pd.DataFrame(columns=list(ib.columns) + ["county", "dist_km"])
    geom_by_county = dict(zip(poly["county"], poly.geometry))
    j["dist_km"] = [geom_by_county[c].distance(p) / 1000 for c, p in zip(j["county"], j.geometry)]
    return pd.DataFrame(j.drop(columns=["geometry", "index_right"]))


def _max_wind(df: pd.DataFrame) -> pd.Series:
    return df[["WMO_WIND", "USA_WIND"]].max(axis=1)


def cyclone_exposure(ib: pd.DataFrame, counties: gpd.GeoDataFrame,
                     last_season: int | None = None) -> dict[str, pd.DataFrame]:
    """Count distinct tropical storms (>= 34 kt while within 300 km) per county and season.

    IBTrACS SEASON is the cyclone season year (South Indian: July-June, labelled by the
    year it ends). Decade rates are storms per season so a partial decade stays comparable.
    """
    last_season = last_season or int(ib["SEASON"].max())
    seasons = range(C.CYCLONE_FIRST_SEASON, last_season + 1)
    near = cyclone_points_near(ib, counties, C.CYCLONE_RADIUS_KM)
    ts = near[_max_wind(near) >= C.TROPICAL_STORM_KT] if not near.empty else near
    per_season = (ts.groupby(["county", "SEASON"])["SID"].nunique().rename("storms").reset_index()
                  if not ts.empty else pd.DataFrame(columns=["county", "SEASON", "storms"]))
    grid = pd.MultiIndex.from_product([C.COUNTY_NAMES, list(seasons)], names=["county", "SEASON"])
    per_season = per_season.set_index(["county", "SEASON"]).reindex(grid, fill_value=0).reset_index()
    per_season["decade"] = (per_season["SEASON"] - 1) // 10 * 10 + 1  # 1981-1990, 1991-2000, ...
    dec = per_season.groupby(["county", "decade"]).agg(storms=("storms", "sum"), seasons=("SEASON", "size"))
    dec["storms_per_season"] = dec["storms"] / dec["seasons"]
    dec = dec.reset_index()
    dec["decade_label"] = dec["decade"].astype(str) + "-" + (dec["decade"] + 9).clip(upper=last_season).astype(str)

    ctx = cyclone_points_near(ib, counties, C.CYCLONE_CONTEXT_RADIUS_KM)
    ctx_n = ctx.groupby("county")["SID"].nunique() if not ctx.empty else pd.Series(dtype=float)
    any300 = near.groupby("county")["SID"].nunique() if not near.empty else pd.Series(dtype=float)
    closest = near.groupby("county")["dist_km"].min() if not near.empty else pd.Series(dtype=float)

    rank = per_season.groupby("county")["storms"].sum().rename("tropical_storms_300km").reset_index()
    rank["storms_per_decade"] = rank["tropical_storms_300km"] / len(seasons) * 10
    rank["any_system_300km"] = rank["county"].map(any300).fillna(0).astype(int)
    rank["any_system_600km_context"] = rank["county"].map(ctx_n).fillna(0).astype(int)
    rank["closest_approach_km"] = rank["county"].map(closest).round(0)
    rank["seasons_covered"] = f"{C.CYCLONE_FIRST_SEASON}-{last_season}"
    rank = rank.sort_values(["tropical_storms_300km", "any_system_300km", "any_system_600km_context"],
                            ascending=False).reset_index(drop=True)
    rank["exposure_rank"] = np.arange(1, len(rank) + 1)
    names = (ts.groupby(["county"]).apply(
        lambda g: ", ".join(sorted({f"{n} ({int(s)})" for n, s in zip(g["NAME"], g["SEASON"])})),
        include_groups=False) if not ts.empty else pd.Series(dtype=str))
    rank["storms_listed"] = rank["county"].map(names).fillna("none")
    tracks = ib[ib["SID"].isin(ctx["SID"].unique())] if not ctx.empty else ib.iloc[0:0]
    return {"per_season": per_season, "per_decade": dec, "ranking": rank, "tracks": tracks}
