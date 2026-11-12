"""Generate the two submission notebooks from code (keeps them reproducible and diff-able).

    python scripts/build_notebooks.py            # writes notebooks/*.ipynb (unexecuted)
    jupyter nbconvert --execute --to notebook --inplace notebooks/*.ipynb   # after run_all.py
"""
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
SETUP = """import sys, json
from pathlib import Path
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from sentinel import config as C
OUT, RAW = C.OUT_DIR, C.RAW_DIR
pd.set_option("display.max_columns", 40); pd.set_option("display.width", 200)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
csv = lambda n, **k: pd.read_csv(OUT / n, **k)
summary = json.loads((OUT / "run_summary.json").read_text())
print("Daily data:", summary["daily_range"], "| built", summary["built_utc"])"""


def md(s):
    return nbf.v4.new_markdown_cell(s.strip())


def code(s):
    return nbf.v4.new_code_cell(s.strip())


def nb1():
    cells = [
        md("""# 01 - Weather behaviour, hazard indicators, cyclone exposure and validation
**Climate Sentinel Kenya** - 14 counties (arid north-east, Lake Victoria basin, central highlands, coast).

Run `python run_all.py` first; this notebook only reads `outputs/` so every number here is reproducible.

> **Rainfall is a model estimate, not a rain-gauge reading.** It comes from the ERA5 reanalysis (via Open-Meteo):
> a weather model constrained by observations on a ~25 km grid. It is smooth in space, can miss local convective
> storms, tends to put too many light-rain days in the tropics and can under-estimate extreme daily totals.
> Thresholds are therefore *relative to each location's own ERA5 history*, never absolute mm values from gauges."""),
        code(SETUP),
        md("## 0. Data provenance and coverage"),
        code("""acc = RAW / "ACCESS_LOG.json"
print(json.dumps(json.loads(acc.read_text()), indent=1) if acc.exists() else "no access log (offline build)")
daily = pd.read_parquet(RAW / "daily_all.parquet")
cov = daily.groupby("county").agg(first=("date", "min"), last=("date", "max"), days=("date", "size"),
                                  missing_rain=("precip", lambda s: int(s.isna().sum())),
                                  grid_lat=("grid_lat", "first"), grid_lon=("grid_lon", "first"))
pts = pd.DataFrame([(c.name, c.town, c.lat, c.lon) for c in C.COUNTIES], columns=["county", "town", "lat", "lon"]).set_index("county")
cov = cov.join(pts)
cov["grid_offset_km"] = (111 * np.hypot(cov.grid_lat - cov.lat, (cov.grid_lon - cov.lon) * np.cos(np.radians(cov.lat)))).round(1)
cov"""),
        md("## 1. Climatology (1991-2020 normals) and rainy seasons"),
        code("""clim = csv("climatology.csv")
fig, axes = plt.subplots(4, 4, figsize=(14, 10), sharex=True)
for ax, (county, g) in zip(axes.flat, clim.groupby("county")):
    ax.bar(g.month, g.precip_mean, color="#4a7fb5"); ax.set_title(county, fontsize=9)
    ax2 = ax.twinx(); ax2.plot(g.month, g.tmax_mean, color="#c0392b", lw=1); ax2.tick_params(labelsize=6)
for ax in axes.flat[len(C.COUNTIES):]: ax.axis("off")
fig.suptitle("Monthly normal rainfall (bars, mm) and mean Tmax (red, degC), 1991-2020"); fig.tight_layout()"""),
        code("""seasons = csv("seasons.csv"); seasons"""),
        md("Wet months are months whose normal is above the county's average month (annual/12); contiguous wet months form a season. "
           "Expect **bimodal** regimes (long rains Mar-May, short rains Oct-Dec) in most of Kenya, a later long-rains peak "
           "(Apr-Jun) on the coast, and a wetter, flatter regime in the Lake Victoria basin."),
        md("## 2. Trends: annual and seasonal rainfall, temperature\nMann-Kendall test (Kendall's tau vs year) for significance, "
           "Sen's slope for the size of change, complete years only."),
        code("""tr = csv("trends.csv")
tr["change"] = tr.apply(lambda r: f"{r.sen_slope_per_decade:+.1f} {r.unit}/decade" + (f" ({r.change_pct_of_mean:+.0f}% over period)" if r.unit == 'mm' else ""), axis=1)
tr.pivot(index="county", columns="variable", values="change")"""),
        code("""sig = tr[tr.significant_5pct]
print(f"{len(sig)} of {len(tr)} county-variable trends are significant at 5%.")
for r in sig.itertuples():
    print(f"- {r.county}: {r.variable} {r.sen_slope_per_decade:+.2f} {r.unit}/decade (p={r.p_value:.3f}, 95% CI {r.slope_95ci_per_decade})")
print("\\nCaution: with 14 counties x 7 variables (~98 tests) about 5 'significant' results are expected by chance alone.")"""),
        code("""ext = csv("extremes.csv"); daily_ann = ext.pivot(index="year", columns="county", values="annual_rain_mm")
ax = daily_ann[["Mandera", "Tana River", "Nairobi", "Kisumu", "Mombasa"]].plot(figsize=(11, 4), marker=".")
ax.set_ylabel("Annual rain (mm)"); ax.set_title("Annual rainfall, selected counties")"""),
        md("## 3. Extremes\nLongest dry spell (consecutive days < 1 mm), heavy-rain days (above the county's own 95th percentile of wet days), "
           "maximum 3-day rainfall, and hot days (apparent Tmax above the county's 95th percentile)."),
        code("""ext.groupby("county")[["longest_dry_spell_days", "heavy_rain_days", "max_3day_rain_mm", "hot_days"]].agg(["mean", "max"]).round(1)"""),
        code("""et = csv("extremes_trends.csv")
et.pivot(index="county", columns="variable", values="sen_slope_per_decade").round(2).join(
    et.pivot(index="county", columns="variable", values="significant_5pct").add_suffix(" sig"))"""),
        md("## 4. Drought indicator: 3-month rainfall as % of normal\n"
           "| Level | % of 1991-2020 normal | Why |\n|---|---|---|\n"
           "| Normal | >= 75% | 75% is the lower edge of 'near normal' used in seasonal rainfall performance reporting |\n"
           "| Watch | 50-75% | clearly below normal; comparable to NDMA 'Alert' |\n"
           "| Warning | 25-50% | half or less of normal; comparable to NDMA 'Alarm' |\n"
           "| Emergency | < 25% | near-total season failure |\n\n"
           "When the 3-month normal is under **30 mm** (dry season) the % is not assessed: 5 mm vs a 10 mm normal is '50%' but means nothing. "
           "The class frequencies below check that Watch+ is uncommon but not rare."),
        code("""csv("drought_class_frequency.csv", index_col=0)"""),
        code("""dro = pd.read_parquet(OUT / "drought.parquet")
fig, ax = plt.subplots(figsize=(12, 4))
for c in ["Mandera", "Wajir", "Garissa", "Tana River"]:
    g = dro[dro.county == c]; ax.plot(g.date, g.pct_of_normal, lw=0.9, label=c)
for y in (75, 50, 25): ax.axhline(y, color="#c0392b", ls=":", lw=0.8)
ax.set_ylim(0, 300); ax.set_ylabel("% of normal"); ax.legend(ncol=4); ax.set_title("3-month rainfall as % of normal (gaps = dry season)")"""),
        md("## 5. Heavy-rain indicator: 3-day total vs the county's own 99th percentile"),
        code("""csv("heavy_thresholds.csv", index_col=0).round(1)"""),
        md("## 6. Validation against history\n### 6a. The 3 worst droughts and 3 worst heavy-rain periods our indicators flag (region-wide)"),
        code("""display(csv("worst_droughts.csv")); display(csv("worst_heavy_rain.csv"))"""),
        code("""csv("per_county_worst.csv").pivot_table(index="county", columns="hazard", values="when", aggfunc=", ".join)"""),
        md("### 6b. Check against documented real events (ReliefWeb / IFRC / NDMA)\n"
           "Matched = indicator reached **Warning** or worse in the listed county within the reported window +/- 1 month."),
        code("""val = csv("validation.csv")
display(val[["event", "county", "window", "result", "indicator_detail"]])
s = val.groupby("event")["result"].value_counts().unstack(fill_value=0); display(s)
for ev, g in val.groupby("event"):
    m = (g.result == "matched").sum(); p = g.result.str.startswith("partial").sum()
    print(f"{ev}: matched {m}/{len(g)} counties, partial {p}; missed: {', '.join(g[g.result=='missed'].county) or 'none'}")
print("\\nSources:"); [print("-", u) for u in val.url.unique()]"""),
        md("**Reading the misses:** a point estimate at the county HQ cannot see rain that fell upstream (e.g. Tana River floods are often driven by "
           "rain in the central highlands, far from Hola), and ERA5 smooths intense local storms (urban flash floods in Nairobi). "
           "These are recorded in LIMITATIONS.md."),
        md("## 7. Cyclone exposure (IBTrACS, 300 km from the county boundary)\n"
           "Distances are computed in a Kenya-centred azimuthal equidistant projection (metres), not in degrees."),
        code("""rk = csv("cyclone_ranking.csv"); display(rk)
dec = csv("cyclone_per_decade.csv")
dec[dec.county.isin([c.name for c in C.COUNTIES if c.coastal])].pivot(index="decade_label", columns="county", values="storms")"""),
        code("""import geopandas as gpd
g = gpd.read_file(OUT / "counties_status.geojson")
tracks = pd.read_parquet(OUT / "cyclone_tracks.parquet")
ax = g.plot(column="cyclone_exposure_class", legend=True, figsize=(7, 8), edgecolor="k", cmap="YlOrRd")
for sid, t in tracks.sort_values("ISO_TIME").groupby("SID"):
    ax.plot(t.LON, t.LAT, lw=0.8, color="#3355cc", alpha=0.6)
ax.set_xlim(33, 46); ax.set_ylim(-8, 6); ax.set_title("Storm tracks within 600 km (blue) and 300 km exposure class")"""),
        md("Cyclones rarely reach Kenya: South-West Indian Ocean storms mostly track south of ~10 S. Low counts are the honest result, "
           "which is why the playbook ties cyclone actions to official KMD / RSMC La Reunion warnings rather than to our exposure count."),
        md("## 8. Population exposure (WorldPop 2020, 1 km)"),
        code("""pop = csv("population.csv"); display(pop.round(0))
print("Median |WorldPop - census| difference:", round(pop.worldpop_vs_census_pct.abs().median(), 1), "%")
for f in sorted(OUT.glob("people_by_*.csv")):
    print("\\n" + f.stem); display(pd.read_csv(f))"""),
    ]
    return cells


def nb2():
    return [
        md("""# 02 - Seasonal outlook: will the next 3 months be below normal?
At the end of each month we predict whether the next 3 months' rainfall falls in the **driest third** of history for that season.

**No-leakage rules** (enforced in `sentinel/outlook.py`, tested in `tests/test_outlook_leakage.py`):
1. Time split - the test set is every issue whose target starts in the last 8 complete years; training targets must end before that (purged gap).
2. All normals, standard deviations and tercile thresholds come from training months only.
3. ONI is the season ending the previous month (centred two months back) and DMI is last month's value - what was published at issue time.
4. Model type and warning threshold are chosen on the last 5 training years, never on the test years.
5. Outlooks are not issued for dry-season targets (3-month normal < 30 mm) where 'driest third' is meaningless."""),
        code(SETUP),
        code("""info = json.loads((OUT / "outlook_info.json").read_text()); print(json.dumps(info, indent=1))"""),
        md("## Per-county results on the test years\nBaselines: **climatology** (always 33%; as a categorical forecast, a random 1-in-3 warning, "
           "so precision = observed base rate and recall = 1/3) and **persistence** (dry last 3 months -> predict dry)."),
        code("""met = csv("outlook_metrics.csv")
cols = ["county", "n_test", "observed_below_rate", "model_precision", "model_recall", "model_f1", "persistence_precision",
        "persistence_recall", "persistence_f1", "climatology_f1", "brier_model", "brier_persistence", "brier_climatology",
        "bss_model_vs_clim", "bss_90ci_lo", "bss_90ci_hi", "bss_persistence_vs_clim", "roc_auc_model", "verdict"]
met[cols].round(3)"""),
        code("""m = met[met.county != "ALL (pooled)"].sort_values("bss_model_vs_clim")
fig, ax = plt.subplots(figsize=(8, 5))
ax.errorbar(m.bss_model_vs_clim, m.county, xerr=[m.bss_model_vs_clim - m.bss_90ci_lo, m.bss_90ci_hi - m.bss_model_vs_clim], fmt="o", capsize=3)
ax.scatter(m.bss_persistence_vs_clim, m.county, marker="x", color="#c0392b", label="persistence")
ax.axvline(0, color="k", lw=0.8); ax.set_xlabel("Brier skill score vs climatology (90% bootstrap CI)"); ax.legend()"""),
        md("## By target season (all counties pooled)\nThe Indian Ocean Dipole is a known driver of the Oct-Dec short rains, so skill is expected there before Mar-May."),
        code("""csv("outlook_by_season.csv").round(3)"""),
        md("## Reliability: are the probabilities honest?"),
        code("""te = pd.read_parquet(OUT / "outlook_test_predictions.parquet")
bins = np.linspace(0, 1, 6); te["bin"] = pd.cut(te.p_model, bins, include_lowest=True)
rel = te.groupby("bin", observed=True).agg(forecast=("p_model", "mean"), observed=("y", "mean"), n=("y", "size"))
display(rel.round(3))
fig, ax = plt.subplots(figsize=(4.5, 4.5)); ax.plot([0, 1], [0, 1], "k:"); ax.plot(rel.forecast, rel.observed, "o-")
ax.axhline(1/3, color="grey", lw=0.6); ax.set_xlabel("forecast probability"); ax.set_ylabel("observed frequency")"""),
        md("## Plain statement of skill"),
        code("""for r in met.itertuples():
    ci = f"BSS {r.bss_model_vs_clim:+.2f} (90% CI {r.bss_90ci_lo:+.2f} to {r.bss_90ci_hi:+.2f})"
    print(f"- {r.county}: {r.verdict}. {ci}; F1 model {r.model_f1:.2f} vs persistence {r.persistence_f1:.2f} vs climatology {r.climatology_f1:.2f}.")
ns = met[(met.county != "ALL (pooled)") & met.verdict.str.startswith("No skill")].county.tolist()
print(f"\\nWhere there is no skill ({', '.join(ns) or 'none'}), the dashboard and agent publish the climatological 33% instead of the model.")"""),
        md("## Live outlook (issued at the end of the latest complete month)"),
        code("""csv("outlook_live.csv")"""),
    ]


def main():
    out = ROOT / "notebooks"
    out.mkdir(exist_ok=True)
    for name, cells in [("01_weather_behavior.ipynb", nb1()), ("02_forecasting.ipynb", nb2())]:
        nb = nbf.v4.new_notebook()
        nb["cells"] = cells
        nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nbf.write(nb, out / name)
        print("wrote", out / name)


if __name__ == "__main__":
    main()
