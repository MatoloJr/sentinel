"""Rain after drought (drought-to-flood whiplash), minor-season drought cap, urban actions, census population."""
import datetime as dt
import json

import numpy as np
import pandas as pd

from sentinel import climate
from sentinel import config as C
from sentinel import indicators as ind
from sentinel import insights as ins


def _daily(drought_then_deluge: bool = True) -> pd.DataFrame:
    """Two synthetic counties; Wajir gets ~2 dry years then 3 days of very heavy rain in Nov 2023."""
    rng = np.random.default_rng(3)
    dates = pd.date_range("1991-01-01", "2024-06-30", freq="D")
    doy = dates.day_of_year.to_numpy()
    out = []
    for name in ("Wajir", "Kisumu"):
        wet = 0.05 + 0.4 * np.sin(2 * np.pi * (doy - 60) / 182.5) ** 2
        rain = (rng.random(len(dates)) < wet) * rng.gamma(0.8, 10, len(dates))
        if name == "Wajir" and drought_then_deluge:
            rain[(dates >= "2022-01-01") & (dates < "2023-10-20")] *= 0.2
            rain[(dates >= "2023-11-02") & (dates <= "2023-11-04")] = 60.0
        out.append(pd.DataFrame({"county": name, "date": dates, "precip": rain, "tmax": 30.0, "tmin": 20.0,
                                 "tmean": 25.0, "atmax": 32.0}))
    return pd.concat(out, ignore_index=True)


def _wh(daily):
    mon = climate.monthly(daily)
    hr = ind.heavy_rain_indicator(daily, ind.heavy_thresholds(daily))
    return mon, hr, ind.whiplash_indicator(hr, ind.antecedent_dryness(mon))


def test_whiplash_level_rule():
    assert ind.whiplash_level("Warning", 60) == "Warning"
    assert ind.whiplash_level("Watch", C.WHIPLASH_DRY_PCT) == "Watch"
    assert ind.whiplash_level("Warning", 90) == "Normal"     # heavy rain after a normal year
    assert ind.whiplash_level("Normal", 20) == "Normal"      # drought, but no heavy rain
    assert ind.whiplash_level("Warning", None) == "Normal"


def test_antecedent_uses_only_past_months():
    daily = _daily()
    mon = climate.monthly(daily)
    a1 = ind.antecedent_dryness(mon)
    mon2 = mon.copy()
    last = mon2["date"].max()
    mon2.loc[mon2["date"] == last, "precip"] *= 10           # change the latest month only
    a2 = ind.antecedent_dryness(mon2)
    k = ["county", "date"]
    m = a1.merge(a2, on=k, suffixes=("", "_2"))
    same = m[m["date"] <= last]                              # rows for months up to `last` ignore `last`'s rain
    assert np.allclose(same["ante_pct"], same["ante_pct_2"])
    assert (a1.groupby("county")["date"].max() == last + pd.offsets.MonthBegin(1)).all()  # current month present


def test_injected_whiplash_is_caught_and_validated():
    mon, hr, wh = _wh(_daily())
    ep = ind.whiplash_episodes(wh)
    w23 = ep[(ep["county"] == "Wajir") & ep["start"].str.startswith("2023-1")]
    assert len(w23) == 1 and C.LEVEL_RANK[w23.iloc[0]["level"]] >= C.LEVEL_RANK["Warning"]
    ev = [{"id": "T", "start": "2023-10-15", "end": "2023-12-31", "counties": ["Wajir", "Kisumu"],
           "source": "test", "url": ""}]
    v = ind.validate_whiplash(wh, ev).set_index("county")
    assert v.loc["Wajir", "result"] == "matched"
    assert v.loc["Kisumu", "result"] != "matched"
    stats = ind.whiplash_stats(wh, ep, ind.drought_indicator(mon))
    assert 0 <= stats["blind_spot_drought_indicator_normal_pct"] <= 100


def test_no_whiplash_without_drought():
    _, _, wh = _wh(_daily(drought_then_deluge=False))
    nov23 = wh[(wh["county"] == "Wajir") & wh["date"].between("2023-11-01", "2023-11-10")]
    assert (nov23["whiplash_level"] == "Normal").all()


def test_minor_season_caps_drought_at_watch():
    """Strong two-season climate (like Nairobi): Jul-Oct windows normally bring <20% of the year's rain."""
    rng = np.random.default_rng(5)
    normal = {1: 50, 2: 40, 3: 90, 4: 200, 5: 150, 6: 30, 7: 15, 8: 20, 9: 25, 10: 40, 11: 150, 12: 90}
    months = pd.date_range("1991-01-01", "2024-12-01", freq="MS")
    precip = [normal[m.month] * rng.uniform(0.1, 1.9) for m in months]
    mon = pd.DataFrame({"county": "Nairobi", "date": months, "precip": precip})
    dro = ind.drought_indicator(mon)
    minor = dro[dro["minor_season"]]
    assert len(minor) and not minor["level"].isin(["Warning", "Emergency"]).any()
    assert minor["uncapped_level"].isin(["Warning", "Emergency"]).any()      # the cap actually bit
    assert dro.loc[~dro["minor_season"], "level"].isin(["Warning", "Emergency"]).any()  # main seasons still escalate
    assert not ind.main_season(dro)["minor_season"].any()   # rankings and validation use main seasons only


def test_urban_county_gets_no_rural_actions():
    pb = ins._playbook()
    rural = {a["id"] for a in pb["actions"] if "rural" in a.get("settings", [])}
    assert rural, "playbook must tag rural/pastoral actions"
    city = {a["id"] for lv in ("Watch", "Warning", "Emergency") for a in ins._actions(pb, "drought", lv, urban=True)}
    assert not city & rural
    assert C.COUNTY_BY_NAME["Nairobi"].urban


def test_compound_actions_are_existing_cited_actions():
    pb = json.loads(C.PLAYBOOK_JSON.read_text())
    ids = {a["id"] for a in pb["actions"]}
    for lvl in ("Watch", "Warning", "Emergency"):
        assert set(pb["compound"]["whiplash"][lvl]) <= ids
        assert lvl in pb["levels"]["whiplash"]


def test_census_drives_population():
    from sentinel import geo
    p = geo.add_census(pd.DataFrame({"county": ["Mandera", "Nowhere"], "worldpop_2020": [2_596_580.0, 1000.0]}))
    p = p.set_index("county")
    assert p.loc["Mandera", "population"] == C.CENSUS_2019["Mandera"]
    assert p.loc["Nowhere", "population"] == 1000.0         # falls back to WorldPop without a census total
    assert round(p.loc["Mandera", "worldpop_vs_census_pct"]) == 199


def test_cards_carry_compound_block(synth):
    data = ins.build_insights(today=dt.date(2026, 11, 12))
    for c in data["counties"]:
        assert c["compound_level"] in C.LEVELS
        if c["compound"]:
            assert c["compound"]["antecedent_12m_pct"] <= C.WHIPLASH_DRY_PCT
    assert "whiplash" in data["region"]
