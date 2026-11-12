# Data sources, access and licences

Exact download URLs and UTC access timestamps are written automatically to `data/raw/ACCESS_LOG.json` on every fetch.
Copy the access dates into the table below before submitting.

| Dataset | Used for | Provider / URL | Licence | Access date |
|---|---|---|---|---|
| ERA5 daily reanalysis (rain, Tmax, Tmin, Tmean, apparent Tmax), 1991-present, via the Open-Meteo Historical Weather API with `models=era5` | Climatology, trends, extremes, indicators, outlook | ECMWF Copernicus C3S ERA5 · https://archive-api.open-meteo.com/v1/archive | Open-Meteo data CC BY 4.0; ERA5 under the Copernicus licence (attribution) | *(from ACCESS_LOG.json)* |
| Open-Meteo Forecast API, 7 days (rain, wind gusts, Tmax) | Short-range watch | https://api.open-meteo.com/v1/forecast | CC BY 4.0 | *(live)* |
| Oceanic Niño Index (ONI), monthly 3-month means | Outlook feature (ENSO) | NOAA CPC · https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt | US Gov public domain | |
| Dipole Mode Index (DMI, HadISST) | Outlook feature (Indian Ocean Dipole) | NOAA PSL · https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data | Public; HadISST © Met Office (non-commercial research use) | |
| IBTrACS v04r01, South Indian + North Indian basins | Cyclone exposure | NOAA NCEI · https://www.ncei.noaa.gov/products/international-best-track-archive | US Gov public domain (cite Knapp et al. 2010) | |
| Kenya ADM1 county boundaries | Map, zonal sums, 300 km buffers | geoBoundaries gbOpen KEN ADM1 · https://www.geoboundaries.org | CC BY 4.0 (see `data/raw/kenya_adm1_meta.json`) | |
| WorldPop 2020 population, 1 km, UN-adjusted | People exposed per hazard level | https://data.worldpop.org (Global_2000_2020_1km_UNadj) | CC BY 4.0 | |
| KNBS 2019 Kenya Population and Housing Census, Vol. I (county totals) | Sanity check of the WorldPop sums only | Kenya National Bureau of Statistics | Public | |
| Documented events (ReliefWeb, IFRC, NDMA) | Indicator validation | URLs listed in `sentinel/config.py` → `REFERENCE_EVENTS` and `outputs/validation.csv` | Public reports | |
| Guidance documents (KRCS/IFRC EAPs, IFRC PAPE, WFP, FAO) | Action playbook | See `PLAYBOOK.md` sources | Public reports | |

## Rainfall is a model estimate, not a rain-gauge reading
ERA5 is a **reanalysis**: a weather model run over the past and nudged towards satellite, radiosonde and surface
observations, on a ~25 km grid (ERA5 itself is ~31 km; Open-Meteo serves it at 0.25°). What that means:

- **It is an area average.** A value represents a whole grid cell, not the HQ town. Local thunderstorms are smoothed out,
  so daily extremes are **under-estimated** and light-rain days are **over-counted** (the "drizzle problem").
- **Kenya has few gauges feeding it,** especially in the arid north-east, so the model has less to anchor to there.
- **Indicators are relative.** We compare each county with its own ERA5 history (percentiles, % of normal), which cancels
  much of the constant bias. We never compare ERA5 millimetres with gauge-based thresholds.
- **The forecast uses different models** (Open-Meteo forecast blend) from the ERA5 history behind the thresholds, so p99 flags in the
  7-day watch are prompts to check KMD forecasts, not calibrated warnings.
- We request `models=era5` explicitly so the whole 1991-present series comes from one consistent system. Mixing models
  over time would create artificial trends.

## Processing notes
- Representative point per county = HQ town coordinates (`sentinel/config.py`). The notebook reports the distance to the ERA5 grid centre.
- Only complete months (all days present) enter monthly analysis, and only complete years enter annual trends and extremes.
- Projected CRSs: Kenya-centred azimuthal equidistant (`+proj=aeqd +lat_0=0.5 +lon_0=38.5`) for the 300 km cyclone buffers, EPSG:6933 for areas.
- IBTrACS: main tracks only, seasons 1981 onward (satellite era). A "tropical storm" means max(WMO_WIND, USA_WIND) ≥ 34 kt at a point within 300 km.
