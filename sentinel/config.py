"""Central configuration: region, paths, thresholds and documented reference events.

Every threshold used anywhere in the project lives here so it can be justified once
(see README "Methods") and changed in one place.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("SENTINEL_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = Path(os.environ.get("SENTINEL_OUT_DIR", ROOT / "outputs"))
LOG_DIR = Path(os.environ.get("SENTINEL_LOG_DIR", ROOT / "logs"))
PLAYBOOK_JSON = ROOT / "sentinel" / "playbook.json"

REGION_NAME = "Kenya (14 counties: arid north-east, Lake Victoria basin, central, coast)"
TIMEZONE = "Africa/Nairobi"
START_DATE = "1991-01-01"
NORMAL_START, NORMAL_END = 1991, 2020  # WMO standard normal period


@dataclass(frozen=True)
class County:
    name: str
    town: str  # representative point = county headquarters town
    lat: float
    lon: float
    zone: str
    coastal: bool
    urban: bool = False  # city county: rural/pastoral playbook actions are not shown


# One representative point per county (the county HQ town, where most people and
# services are). Point values are a model grid-cell estimate, not a county average.
COUNTIES: list[County] = [
    County("Turkana", "Lodwar", 3.1191, 35.5973, "Arid north", False),
    County("Marsabit", "Marsabit", 2.3284, 37.9899, "Arid north", False),
    County("Mandera", "Mandera", 3.9366, 41.8670, "Arid north-east", False),
    County("Wajir", "Wajir", 1.7471, 40.0573, "Arid north-east", False),
    County("Garissa", "Garissa", -0.4532, 39.6461, "Arid north-east", False),
    County("Tana River", "Hola", -1.4980, 40.0300, "Tana basin", False),
    County("Makueni", "Wote", -1.7807, 37.6288, "Semi-arid south-east", False),
    County("Nairobi", "Nairobi", -1.2864, 36.8172, "Central highlands", False, urban=True),
    County("Kisumu", "Kisumu", -0.0917, 34.7680, "Lake Victoria basin", False),
    County("Busia", "Busia", 0.4608, 34.1115, "Lake Victoria basin", False),
    County("Lamu", "Lamu", -2.2717, 40.9020, "Coast", True),
    County("Kilifi", "Kilifi", -3.6305, 39.8499, "Coast", True),
    County("Mombasa", "Mombasa", -4.0435, 39.6682, "Coast", True),
    County("Kwale", "Kwale", -4.1816, 39.4606, "Coast", True),
]
COUNTY_NAMES = [c.name for c in COUNTIES]
COUNTY_BY_NAME = {c.name: c for c in COUNTIES}

# KNBS 2019 Kenya Population and Housing Census, Volume I (county totals).
# These official totals are the people counts used for exposure and ranking. The WorldPop 2020
# raster sum is kept as a cross-check only: it over-counts the arid north-east by +89% to +199%
# (Mandera, Wajir, Garissa), which would distort the priority ranking. Verify against the PDF.
CENSUS_2019 = {
    "Turkana": 926_976, "Marsabit": 459_785, "Mandera": 867_457, "Wajir": 781_263,
    "Garissa": 841_353, "Tana River": 315_943, "Makueni": 987_653, "Nairobi": 4_397_073,
    "Kisumu": 1_155_574, "Busia": 893_681, "Lamu": 143_920, "Kilifi": 1_453_787,
    "Mombasa": 1_208_333, "Kwale": 866_820,
}

# ---------------------------------------------------------------- thresholds
WET_DAY_MM = 1.0             # ETCCDI wet-day definition
HEAVY_DAY_PCTL = 95          # heavy-rain day: > county p95 of wet-day rainfall
DRY_SEASON_MIN_MM = 30.0     # 3-month normal below this = dry season, drought not assessed
# Minor season: a 3-month window that normally brings less than this share of the year's rain
# (an even spread would give 25%). A % of normal there is a small absolute shortfall, so the
# drought level is capped at Watch and the window is left out of the "worst droughts" ranking.
# Percent-of-normal is known to mislead outside the main rainy season (WMO-No. 1090, SPI guide).
MINOR_SEASON_SHARE_PCT = 20.0

# Drought: 3-month rainfall as % of the 1991-2020 normal for the same 3 months.
# 75% is the lower edge of "near normal" in seasonal rainfall performance reporting;
# halving steps below that give Watch / Warning / Emergency. Class frequencies are
# reported per county in notebook 01 to show the classes are neither too common nor too rare.
DROUGHT_CLASSES = [  # (lower bound inclusive, upper bound exclusive, level)
    (75.0, float("inf"), "Normal"),
    (50.0, 75.0, "Watch"),
    (25.0, 50.0, "Warning"),
    (float("-inf"), 25.0, "Emergency"),
]
# Heavy rain: 3-day total vs the county's own 3-day percentiles (1991-2020, all days).
# p95 ~ 18 days/yr, p99 ~ 3-4 days/yr, p99.9 ~ once every ~3 years.
HEAVY_PCTLS = {"Watch": 95.0, "Warning": 99.0, "Emergency": 99.9}
GALE_GUST_KMH = 62.0         # Beaufort 8 (gale) lower bound, for the coastal wind flag
HEAT_PCTL = 95               # hot day: apparent Tmax above county p95 (1991-2020)

LEVELS = ["Normal", "Watch", "Warning", "Emergency"]
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# ---------------------------------------------------------------- cyclones
CYCLONE_RADIUS_KM = 300.0
CYCLONE_CONTEXT_RADIUS_KM = 600.0  # context only; the official metric is 300 km
TROPICAL_STORM_KT = 34.0
# Live check: Cyclone Watch is raised only when an ACTIVE system (IBTrACS ACTIVE list, provisional)
# is within this distance of a coastal county's HQ. Season alone is shown as background, not an alert.
ACTIVE_STORM_WATCH_KM = 1000.0
ACTIVE_STORM_MAX_AGE_DAYS = 3  # older active-storm data = live check unavailable
CYCLONE_FIRST_SEASON = 1981        # reliable satellite era
OFFICIAL_CYCLONE_CENTRES = (
    "Kenya Meteorological Department (https://meteo.go.ke) issues national warnings; "
    "RSMC La Réunion (Météo-France, https://meteofrance.re/fr/cyclone) is the WMO "
    "Regional Specialized Meteorological Centre for South-West Indian Ocean cyclones."
)
OFFICIAL_WARNING_NOTE = (
    "Official warnings from the Kenya Meteorological Department (KMD) and the National "
    "Disaster Operations Centre take priority over this planning-support tool."
)

# ---------------------------------------------------------------- compound: drought-to-flood whiplash
# Heavy rain that lands on drought-hit land is more dangerous than the same rain after a normal
# year: crusted bare soil sheds water (flash floods), weak livestock die in cold rain or are swept
# away, and water sources are contaminated. Single-hazard indicators miss this: the 3-month drought
# indicator flips to "Normal" as soon as rain arrives, and the flood indicator ignores what came before.
WHIPLASH_ANTECEDENT_MONTHS = 12  # rain in the 12 full months before the rain event, as % of normal
WHIPLASH_DRY_PCT = 75.0          # antecedent at or below this = drought-hit land (lower edge of near-normal)
WHIPLASH_EPISODE_GAP_DAYS = 30   # rain days closer than this belong to the same whiplash episode

# ---------------------------------------------------------------- outlook model
TEST_YEARS = 8                # last N complete target years are the test set
INNER_VALID_YEARS = 5         # last N training years used to pick model + threshold
BOOTSTRAP_N = 500

# ---------------------------------------------------------------- reference events
# Documented events used to validate the indicators. Window = months the impact was reported.
REFERENCE_EVENTS = [
    {
        "id": "DR-2021",
        "hazard": "drought",
        "name": "2020-2022 drought, declared a national disaster on 8 Sep 2021",
        "start": "2021-03-01", "end": "2022-12-31",
        "counties": ["Mandera", "Wajir", "Garissa", "Marsabit", "Turkana", "Tana River"],
        "source": "IFRC Emergency Appeal MDRKE049 (ReliefWeb)",
        "url": "https://reliefweb.int/report/kenya/kenya-drought-hunger-crisis-2021-emergency-appeal-mdrke049",
    },
    {
        "id": "FL-2023",
        "hazard": "flood",
        "name": "El Niño short-rains floods Oct-Dec 2023 (GLIDE FL-2023-000216-KEN)",
        "start": "2023-10-15", "end": "2023-12-31",
        "counties": ["Mandera", "Wajir", "Garissa", "Tana River", "Lamu"],
        "source": "IFRC Operation Update MDRKE058 (ReliefWeb); UNICEF Kenya sitrep 15 Dec 2023",
        "url": "https://reliefweb.int/report/kenya/kenya-africa-floods-2023-operation-update-mdrke058",
    },
    {
        "id": "FL-2024",
        "hazard": "flood",
        "name": "Long-rains floods Mar-May 2024 (GLIDE FL-2024-000045-KEN)",
        "start": "2024-03-20", "end": "2024-05-31",
        "counties": ["Nairobi", "Tana River", "Kisumu", "Busia", "Mandera"],
        "source": "ReliefWeb disaster page FL-2024-000045-KEN; OCHA flash updates",
        "url": "https://reliefweb.int/disaster/FL-2024-000045-KEN",
    },
    {
        "id": "DR-2025",
        "hazard": "drought",
        "name": "Failed Oct-Dec 2025 short rains; Mandera in NDMA Alarm phase (Dec 2025)",
        "start": "2025-10-01", "end": "2026-02-28",
        "counties": ["Mandera", "Wajir", "Garissa", "Marsabit", "Kilifi", "Kwale", "Tana River"],
        "source": "IFRC Emergency Appeal MDRKE068 operational update; NDMA bulletins",
        "url": "https://go-api.ifrc.org/api/DownloadFile/93652/MDRKE068%20OU2",
    },
]


# Documented drought-to-flood transitions (rain disasters that struck while the land was still in
# drought). Used to validate the whiplash indicator; independent of the events above.
WHIPLASH_EVENTS = [
    {
        "id": "WH-2019",
        "name": "Oct-Nov 2019 floods that 'follow a period of prolonged drought' (OCHA)",
        "start": "2019-10-01", "end": "2019-11-30",
        "counties": ["Mandera", "Wajir", "Marsabit", "Turkana", "Garissa", "Lamu", "Kwale", "Mombasa",
                     "Tana River", "Kisumu", "Busia"],
        "source": "OCHA Kenya Flash Update No. 2: Floods (5 Nov 2019)",
        "url": "https://reliefweb.int/report/kenya/kenya-flash-update-no-2-floods-5-november-2019",
    },
    {
        "id": "WH-2023A",
        "name": "Mar-May 2023 flash floods in counties still in drought Alarm/Emergency (NDMA)",
        "start": "2023-03-15", "end": "2023-05-31",
        "counties": ["Marsabit", "Mandera", "Garissa", "Wajir"],
        "source": "The Star / NDMA, 'Rains a curse for drought-stricken families' (23 Apr 2023)",
        "url": "https://www.the-star.co.ke/news/2023-04-23-rains-a-curse-for-drought-stricken-families",
    },
    {
        "id": "WH-2023B",
        "name": "El Nino floods Oct-Dec 2023 straight after the 2020-2023 drought",
        "start": "2023-10-15", "end": "2023-12-31",
        "counties": ["Mandera", "Wajir", "Garissa", "Tana River", "Lamu"],
        "source": "IFRC Operation Update MDRKE058; UNICEF Kenya sitrep 15 Dec 2023",
        "url": "https://reliefweb.int/report/kenya/kenya-africa-floods-2023-operation-update-mdrke058",
    },
]


def ensure_dirs() -> None:
    for d in (RAW_DIR, OUT_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
