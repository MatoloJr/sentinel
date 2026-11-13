"""Independent check of our rainfall drought indicator against NDMA's official county drought phases.

NDMA (National Drought Management Authority) publishes a monthly Drought Early Warning bulletin per ASAL county
that classifies the county as Normal / Alert / Alarm / Emergency / Recovery. Only bulletins that were actually
downloaded and read are used: a month whose bulletin is not listed, cannot be downloaded or whose phase cannot be
read from the PDF text is stored as "not available". Nothing is guessed. County and month are taken from each bulletin's title, because the NDMA listing mislabels some
(e.g. all Dec 2024 bulletins tagged 'Wajir'); per-document results are cached in data/reference/ndma_bulletins_read.csv.

    node scripts/ndma_list_bulletins.js data/reference/ndma_bulletin_index.csv   # 1. list bulletins (needs Playwright)
    python scripts/ndma_compare.py extract                                       # 2. download + read phases
    python scripts/ndma_compare.py                                               # 3. compare -> outputs/ndma_agreement.csv

Mapping (from sentinel/playbook.json drought level descriptions): Watch ~ Alert, Warning ~ Alarm,
Emergency ~ Emergency, Normal ~ Normal. NDMA 'Recovery' has no rainfall equivalent and is left out of the
agreement numbers (counted separately), as are our 'Dry season (not assessed)' months.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"
INDEX_CSV = REF / "ndma_bulletin_index.csv"
PHASES_CSV = REF / "ndma_phases.csv"
OUT_CSV = ROOT / "outputs" / "ndma_agreement.csv"
OUT_JSON = ROOT / "outputs" / "ndma_agreement.json"
DROUGHT = ROOT / "outputs" / "drought.parquet"
PLAYBOOK = ROOT / "sentinel" / "playbook.json"

COUNTIES = ["Turkana", "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", "Makueni", "Kilifi", "Kwale", "Lamu"]
PHASES = ["Normal", "Alert", "Alarm", "Emergency", "Recovery"]
NA = "not available"
PHASE_COLS = ["county", "month", "ndma_phase", "bulletin_url", "accessed_utc", "evidence"]
WINDOW = 3  # months either side when matching an NDMA escalation in time

_P = "|".join(PHASES)
# 1) the 'County' row of the EW phase classification table, e.g. "County Alarm Worsening"
COUNTY_ROW = re.compile(rf"^\s*county\s*[:\-]?\s*({_P})\b", re.I | re.M)
# 2) a header such as "Drought Phase:ALERT-WORSENING" or "DROUGHT EW PHASE: ALARM"
HEADER = re.compile(rf"drought\s+(?:ew\s+|early\s+warning\s+)?phase\s*(?:classification)?\s*[:\-]?\s*({_P})\b", re.I)


# ------------------------------------------------------------------ reading bulletins
def parse_phase(text: str) -> tuple[str, str]:
    """(phase, evidence) from the text of a bulletin's first pages; (NA, reason) when it cannot be read."""
    if not text or not text.strip():
        return NA, "no extractable text (scanned image?)"
    rows = {m.group(1).title() for m in COUNTY_ROW.finditer(text)}
    if len(rows) == 1:
        m = COUNTY_ROW.search(text)
        return rows.pop(), _snip(text, m)
    if len(rows) > 1:
        return NA, f"ambiguous County rows: {sorted(rows)}"
    heads = {m.group(1).title() for m in HEADER.finditer(text)}
    if len(heads) == 1:
        m = HEADER.search(text)
        return heads.pop(), _snip(text, m)
    if len(heads) > 1:
        return NA, f"ambiguous phase headers: {sorted(heads)}"
    return NA, "phase classification not found in text"


def _snip(text: str, m: re.Match) -> str:
    end = text.find("\n", m.end())
    line = text[text.rfind("\n", 0, m.start()) + 1: end if end >= 0 else len(text)]
    return re.sub(r"\s+", " ", line).strip()[:120]


def _pdf_text(data: bytes, pages: int = 2) -> str:
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(data))
    return "\n".join((r.pages[i].extract_text() or "") for i in range(min(pages, len(r.pages))))


def _download(url: str, tries: int = 3) -> bytes:
    import requests
    last = None
    for t in range(tries):
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError(f"not a PDF ({r.headers.get('content-type')})")
            return r.content
        except Exception as e:  # noqa: BLE001 - recorded as the reason
            last = e
            time.sleep(3 * (t + 1))
    raise RuntimeError(str(last))


def _read_one(row: dict) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        phase, ev = parse_phase(_pdf_text(_download(row["pdf_url"])))
    except Exception as e:  # noqa: BLE001
        phase, ev = NA, f"download/read failed: {str(e)[:100]}"
    return {"county": row["county"], "month": row["month"], "ndma_phase": phase,
            "bulletin_url": row["pdf_url"], "accessed_utc": now, "evidence": ev}


# NDMA's listing metadata is wrong for some bulletins (e.g. every county's Dec 2024 bulletin is tagged 'Wajir';
# May 2025 bulletins are filed under June). The bulletin's own title is used for county and month instead.
ALL_NDMA_COUNTIES = COUNTIES + ["Baringo", "Embu", "Isiolo", "Kajiado", "Kitui", "Laikipia", "Meru", "Narok", "Nyeri",
                                "Samburu", "Taita Taveta", "Tharaka Nithi", "West Pokot"]
_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
           "nov": 11, "dec": 12}
_MONTH_RE = re.compile(r"(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
                       r"(?:uary|ruary|ch|il+|e|y|ust|t|tember|ember|ober)?(?![a-z])")
CACHE_CSV = REF / "ndma_bulletins_read.csv"
CACHE_COLS = ["doc_id", "ndma_phase", "evidence", "accessed_utc"]


def title_county_month(title: str, listed_month: str) -> tuple[str | None, str | None]:
    """(county, 'YYYY-MM') named in a bulletin title; None for a part the title does not give."""
    t = re.sub(r"[_\-]+", " ", str(title).lower())
    t = re.sub(r"([a-z])(20\d\d)", r"\1 \2", t)  # 'February2022'
    county = next((c for c in ALL_NDMA_COUNTIES if re.search(r"\b" + c.lower().replace(" ", r"\s*") + r"\b", t)), None)
    rest = t
    for c in ALL_NDMA_COUNTIES:  # 'Marsabit' must not read as 'Mar'
        rest = re.sub(c.lower().replace(" ", r"\s*"), " ", rest)
    m = _MONTH_RE.search(rest)
    if not m:
        return county, None
    mon = _MONTHS[m.group(1)]
    y = re.search(r"\b(20\d\d)\b", t)
    ly, lm = int(listed_month[:4]), int(listed_month[5:7])
    year = int(y.group(1)) if y else (ly - 1 if mon == 12 and lm == 1 else ly + 1 if mon == 1 and lm == 12 else ly)
    return county, f"{year}-{mon:02d}"


def relabel(idx: pd.DataFrame) -> pd.DataFrame:
    """County and month from each bulletin's title; the listing's labels only where the title has none."""
    idx = idx.drop_duplicates("doc_id").copy()
    tc = [title_county_month(t, m) for t, m in zip(idx["title"], idx["month"])]
    idx["listed_as"] = idx["county"] + " " + idx["month"]
    idx["county"] = [c or lc for (c, _), lc in zip(tc, idx["county"])]
    idx["month"] = [m or lm for (_, m), lm in zip(tc, idx["month"])]
    return idx[idx["county"].isin(COUNTIES)]


def _seed_cache(phases_csv: Path) -> pd.DataFrame:
    """Per-document results recovered from an older ndma_phases.csv (so nothing is downloaded twice)."""
    if not phases_csv.exists():
        return pd.DataFrame(columns=CACHE_COLS)
    p = pd.read_csv(phases_csv, dtype=str).fillna("")
    p = p[(p["bulletin_url"] != "") & ~p["evidence"].str.startswith("conflicting")]
    rows = [{"doc_id": u.split("document=")[-1], "ndma_phase": r.ndma_phase, "evidence": r.evidence,
             "accessed_utc": r.accessed_utc} for r in p.itertuples() for u in r.bulletin_url.split()]
    return pd.DataFrame(rows, columns=CACHE_COLS)


def extract(index_csv: Path = INDEX_CSV, phases_csv: Path = PHASES_CSV, workers: int = 4,
            first: str = "2021-01", retry_na: bool = False) -> pd.DataFrame:
    """Download and read every listed bulletin not read yet; fill unlisted county-months with 'not available'."""
    idx = relabel(pd.read_csv(index_csv, dtype=str))
    cache = pd.read_csv(CACHE_CSV, dtype=str).fillna("") if CACHE_CSV.exists() else _seed_cache(phases_csv)
    cache = cache.drop_duplicates("doc_id", keep="last")
    if retry_na:
        cache = cache[cache["ndma_phase"] != NA]
    todo = [r for r in idx.to_dict("records") if r["doc_id"] not in set(cache["doc_id"])]
    print(f"{len(idx)} bulletins for our counties, {len(cache)} already read, {len(todo)} to read")
    new = []
    with cf.ThreadPoolExecutor(workers) as ex:
        for i, res in enumerate(ex.map(_read_one, todo), 1):
            new.append({"doc_id": todo[i - 1]["doc_id"], **{k: res[k] for k in CACHE_COLS[1:]}})
            print(f"[{i}/{len(todo)}] {res['county']} {res['month']}: {res['ndma_phase']} | {res['evidence'][:70]}", flush=True)
    cache = pd.concat([cache, pd.DataFrame(new, columns=CACHE_COLS)], ignore_index=True)
    cache.to_csv(CACHE_CSV, index=False)
    j = idx.merge(cache, on="doc_id", how="inner")
    note = [f"{ev} [listed as {la}]" if la != f"{c} {m}" else ev
            for ev, la, c, m in zip(j["evidence"], j["listed_as"], j["county"], j["month"])]
    rows = pd.DataFrame({"county": j["county"], "month": j["month"], "ndma_phase": j["ndma_phase"],
                         "bulletin_url": j["pdf_url"], "accessed_utc": j["accessed_utc"], "evidence": note})
    return _write_phases(rows.to_dict("records"), idx, phases_csv, first)


def _merge_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """More than one bulletin listed for a county-month: keep it only if every copy gives the same phase."""
    out = []
    for _, g in df.groupby(["county", "month"], sort=False):
        if len(g) == 1:
            out.append(g.iloc[0].to_dict())
            continue
        read = g[g["ndma_phase"] != NA]
        r = (read if len(read) else g).iloc[0].to_dict()
        if read["ndma_phase"].nunique() > 1:
            r.update(ndma_phase=NA, evidence="conflicting bulletins: " + "; ".join(f"{a} (doc {b.split('=')[-1][:8]})" for a, b in zip(read.ndma_phase, read.bulletin_url)))
        elif len(read):
            r["bulletin_url"] = " ".join(read["bulletin_url"])
        out.append(r)
    return pd.DataFrame(out, columns=PHASE_COLS)


def _write_phases(rows: list[dict], idx: pd.DataFrame, phases_csv: Path, first: str) -> pd.DataFrame:
    df = _merge_duplicates(pd.DataFrame(rows, columns=PHASE_COLS))
    last = max(idx["month"]) if len(idx) else first
    months = pd.period_range(first, last, freq="M").strftime("%Y-%m")
    grid = pd.MultiIndex.from_product([COUNTIES, months], names=["county", "month"]).to_frame(index=False)
    df = grid.merge(df, on=["county", "month"], how="left")
    miss = df["ndma_phase"].isna()
    df.loc[miss, "ndma_phase"] = NA
    df.loc[miss, "evidence"] = "no bulletin listed on NDMA KnowledgeWeb for this county-month"
    df = df.fillna("").sort_values(["county", "month"])
    phases_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(phases_csv, index=False, quoting=csv.QUOTE_MINIMAL)
    return df


# ------------------------------------------------------------------ comparison
def ndma_mapping(playbook: Path = PLAYBOOK) -> dict[str, str]:
    """Our level -> NDMA phase, read from the playbook's drought level descriptions ("comparable to NDMA 'X'")."""
    pb = json.loads(playbook.read_text(encoding="utf-8"))
    levels = pb["levels"]["drought"]
    m = {"Normal": "Normal"}
    for lvl, text in levels.items():
        hit = re.search(r"NDMA '(\w+)'", text)
        if hit:
            m[lvl] = hit.group(1)
    return m


def compare(phases: pd.DataFrame, drought: pd.DataFrame, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Per-county agreement between NDMA phases and our drought level for the same month."""
    rank = {ph: i for i, ph in enumerate(["Normal", "Alert", "Alarm", "Emergency"])}
    ours_rank = {lvl: rank[ph] for lvl, ph in mapping.items() if ph in rank}
    p = phases[phases["ndma_phase"].isin(PHASES)].copy()
    p["m"] = pd.PeriodIndex(p["month"], freq="M")
    d = drought[["county", "date", "level"]].copy()
    d["m"] = pd.to_datetime(d["date"]).dt.to_period("M")
    x = p.merge(d[["county", "m", "level"]], on=["county", "m"], how="left")
    x["n"] = x["ndma_phase"].map(rank)          # NaN for Recovery
    x["o"] = x["level"].map(ours_rank)          # NaN for dry season / missing
    rows = []
    for county, g in x.groupby("county"):
        rows.append(_county_row(county, g, phases[phases["county"] == county], d[d["county"] == county], ours_rank))
    out = pd.DataFrame(rows)
    tot = _county_row("ALL", x, phases, d, ours_rank)
    out = pd.concat([out, pd.DataFrame([tot])], ignore_index=True)
    overall = {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in tot.items()}
    overall["mapping"] = mapping
    return out, overall


def _pct(a, b):
    return round(100 * a / b, 1) if b else np.nan


def _county_row(county, g, ph, d, ours_rank) -> dict:
    c = g.dropna(subset=["n", "o"])
    n, o = c["n"].to_numpy(), c["o"].to_numpy()
    timing = _escalations(g, d, ours_rank)
    ndma_alert = n >= 1
    ours_watch = o >= 1
    return {
        "county": county,
        "bulletins_read": int(len(g)),
        "not_available": int((ph["ndma_phase"] == NA).sum()),
        "recovery_excluded": int((g["ndma_phase"] == "Recovery").sum()),
        "dry_season_excluded": int((g["level"] == "Dry season (not assessed)").sum()),
        "months_compared": int(len(c)),
        "exact_agreement_pct": _pct((n == o).sum(), len(c)),
        "within_one_level_pct": _pct((abs(n - o) <= 1).sum(), len(c)),
        "always_normal_baseline_pct": _pct((n == 0).sum(), len(c)),
        "ndma_alert_plus_months": int(ndma_alert.sum()),
        "we_watch_plus_when_ndma_alert_plus_pct": _pct((ndma_alert & ours_watch).sum(), ndma_alert.sum()),
        "we_watch_plus_when_ndma_normal_pct": _pct((~ndma_alert & ours_watch).sum(), (~ndma_alert).sum()),
        "we_higher_months": int((o > n).sum()),
        "we_lower_months": int((o < n).sum()),
        **timing,
    }


def _escalations(g, d, ours_rank) -> dict:
    """At each NDMA escalation (phase rises vs the previous month), when did our indicator first reach the same
    level within +/- WINDOW months? earlier = before NDMA, later = after, not_matched = not within the window."""
    res = {"ndma_escalations": 0, "we_earlier": 0, "same_month": 0, "we_later": 0, "not_matched": 0}
    leads = []
    for county, gc in g.groupby("county"):
        s = gc.set_index("m")["n"].sort_index()
        dc = d[d["county"] == county].set_index("m")["level"].map(ours_rank)
        for m, lvl in s.items():
            prev = s.get(m - 1)
            if not (lvl >= 1 and prev is not None and not np.isnan(prev) and lvl > prev):
                continue
            res["ndma_escalations"] += 1
            hit = [k for k in range(-WINDOW, WINDOW + 1) if dc.get(m + k, np.nan) >= lvl]
            if not hit:
                res["not_matched"] += 1
                continue
            k = min(hit)  # earliest month in the window at which we reached NDMA's level
            leads.append(-k)
            res["we_earlier" if k < 0 else "same_month" if k == 0 else "we_later"] += 1
    res["median_lead_months"] = float(np.median(leads)) if leads else np.nan
    return res


def run(phases_csv: Path = PHASES_CSV, drought_path: Path = DROUGHT, out_csv: Path = OUT_CSV,
        out_json: Path | None = OUT_JSON, playbook: Path = PLAYBOOK) -> tuple[pd.DataFrame, dict]:
    phases = pd.read_csv(phases_csv, dtype=str).fillna("")
    drought = pd.read_parquet(drought_path) if str(drought_path).endswith(".parquet") else pd.read_csv(drought_path)
    table, overall = compare(phases, drought, ndma_mapping(playbook))
    p = phases[phases["ndma_phase"].isin(PHASES)]["month"]
    overall["period"] = f"{p.min()} to {p.max()}" if len(p) else None
    overall["source"] = "NDMA KnowledgeWeb county Drought Early Warning bulletins"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_csv, index=False)
    if out_json:
        out_json.write_text(json.dumps(overall, indent=2, default=str))
    a = table.iloc[-1]
    print(table.to_string(index=False))
    print(f"\nOVERALL ({overall['period']}): {a.months_compared} county-months compared; exact agreement "
          f"{a.exact_agreement_pct}% (always-'Normal' baseline {a.always_normal_baseline_pct}%), within one level "
          f"{a.within_one_level_pct}%; NDMA escalations {a.ndma_escalations}: we were earlier {a.we_earlier}, same month "
          f"{a.same_month}, later {a.we_later}, not within {WINDOW} months {a.not_matched}.")
    return table, overall


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", default="compare", choices=["extract", "compare", "all"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--retry-na", action="store_true", help="re-read bulletins previously recorded as not available")
    a = ap.parse_args(argv)
    if a.step in ("extract", "all"):
        extract(workers=a.workers, retry_na=a.retry_na)
    if a.step in ("compare", "all"):
        run()


if __name__ == "__main__":
    sys.exit(main())
