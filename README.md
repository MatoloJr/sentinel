# Climate Sentinel Kenya

**Analysing weather behaviour and estimating drought, heavy-rain and cyclone risk for Kenyan counties**
Zetech Alumni x Student Hackathon · ML & Data Science track · Challenge 1

> ⚠️ **This is a planning-support tool, not an official warning system.** Official warnings from the
> Kenya Meteorological Department (KMD, https://meteo.go.ke) and the National Disaster Operations Centre take
> priority. For any live cyclone, follow KMD and RSMC La Réunion (the WMO centre for the South-West Indian Ocean).
> Climate Sentinel never predicts cyclone paths.

## Region, users and SDGs

| | |
|---|---|
| **Region** | 14 Kenyan counties, one representative point each (county HQ town): Turkana, Marsabit, Mandera, Wajir, Garissa (arid north/north-east), Tana River (Tana basin), Makueni (semi-arid south-east), Nairobi (highlands), Kisumu, Busia (Lake Victoria basin), Lamu, Kilifi, Mombasa, Kwale (coast) |
| **Why here** | Drought and floods both recur and are well documented (2020-22 drought, 2023 and 2024 floods), giving real events to validate against. The coast adds cyclone exposure, which is low but not zero. |
| **Target users** | County disaster risk management officers, county drought coordinators, and humanitarian responders such as Kenya Red Cross county branches |
| **SDGs** | **13.1** (resilience to climate hazards), **2.4** (resilient agriculture and pastoralism), **11.5** (reduce disaster deaths and losses), **1.5** (resilience of the poor) |

## What it does

1. **Weather behaviour**: 1991-2020 monthly normals, rainy seasons, Mann-Kendall + Sen's slope trends, and yearly extremes (longest dry spell, heavy-rain days, maximum 3-day rain, hot days).
2. **Hazard indicators**: drought = 3-month rain as % of normal (Normal / Watch / Warning / Emergency); heavy rain = 3-day total against the county's own p95 / p99 / p99.9. Both are validated against documented events.
3. **Cyclone exposure**: IBTrACS tropical storms within 300 km of each county by season and decade, ranked. Distances are computed in a projected CRS.
4. **Seasonal outlook**: the probability that the next 3 months are below normal, using ENSO and the Indian Ocean Dipole. Leak-free time split, tested on the last 8 years, compared with climatology and persistence. Where the model shows no skill, the system says so and publishes 33%.
5. **7-day watch**: live forecast 3-day rain against each county's p99, plus coastal gale gusts and heat days.
6. **Insights & actions** (`sentinel/insights.py`, no LLM): one card per county with the main drivers, what is likely next (with the model's tested skill), people exposed, a priority rank (severity × population, boosted when risk is rising) and the triggered playbook actions with timeframes. A public view gives plain-language advice and an SMS of at most 160 characters.
7. **Rain after drought (compound drought-to-flood alert)** (`sentinel/indicators.py`, new): heavy rain (the county's own p95 / p99 / p99.9, observed or forecast) on land that had at most 75% of normal rain over the previous 12 months. See the section below.
8. **Early-warning agent (Gemini)**: 8 tools. Every number cites a tool result, a validator blocks unverified numbers or risk denials, actions come only from the cited playbook, every tool call is logged, and each draft needs human approval.
9. **Web app (React)**: an interactive map with hazard layers, a ranked "needs attention" list linked to the map, county dashboards with charts, comparison and an action checklist, the outlook and its verification, cyclone tracks, the advisory workflow and an evidence page. Navigation is a centred dynamic island at the bottom; Ctrl+K opens search. A Manager / Public switch changes the whole app's voice.

## What is new: the rain-after-drought alert

Heavy rain that lands on drought-hit land is more dangerous than the same rain after a normal year. Hard, bare ground sheds
water, so flash floods come faster. Weakened livestock are swept away or fall sick, and scarce water sources are contaminated.
Kenya saw this in Oct-Nov 2019 (OCHA: floods that "follow a period of prolonged drought"), in Mar-May 2023 (NDMA: flash floods
in Marsabit, Mandera, Garissa and Wajir while they were still in drought alarm) and in the Oct-Dec 2023 El Niño floods.

Single-hazard indicators cannot see it. The 3-month drought indicator goes back to "Normal" as soon as the rain arrives,
and a flood indicator ignores what came before. Climate Sentinel joins the two:

* **Rule (fixed before validation):** 3-day rain at the county's p95 (Watch), p99 (Warning) or p99.9 (Emergency), observed
  in the last 7 days or forecast for the next 7, when the previous 12 full months had at most 75% of normal rain.
* **The blind spot it closes (measured, 1991-2026, 14 counties):** in **65%** of rain-after-drought episodes the standard
  3-month drought indicator already read "Normal" or "not assessed" when the rain hit, and in **89%** it was below Warning.
  **17%** of all 1-in-100-day rain days fell on drought-hit land (24-35% in Wajir, Marsabit, Garissa and Turkana).
* **Validation:** caught 5 of 20 documented county-events at Warning, plus 3 at Watch (`outputs/whiplash_validation.csv`).
  Misses are listed with the reason: most 2019 counties had near-normal rain over the 12 months at the HQ point. A
  sensitivity table (`outputs/whiplash_sensitivity.csv`) shows the published rule sits in the middle of the
  6/12-month x 60/75/90% grid, so it was not tuned to the events. It fires about 2 Warning-level episodes per county
  per decade.
* **What the card adds:** the 12-month deficit in mm, how much of it the coming week's rain would make up ("one wet week
  does not end the drought"), the county's history of such episodes, and existing cited playbook actions brought
  forward (early warning, water treatment, livestock health, early evacuation). No new uncited actions are introduced.

## Fixes in this version

* **People = KNBS 2019 census totals.** WorldPop 2020 summed over county polygons over-counted Mandera (+199%), Wajir
  (+117%) and Garissa (+89%) and pushed them up the ranking. WorldPop is kept as a cross-check column.
* **Cyclone Watch needs a live storm.** Watch is raised only when an active storm (IBTrACS ACTIVE list) is within
  1,000 km of a coastal county. Cyclone season alone is shown as background text, so the coast is not flagged for six
  months a year with no storm in sight.
* **Minor-season drought is capped at Watch.** A 3-month window that normally brings under 20% of the year's rain
  (e.g. Aug-Oct in Nairobi, 13%) gives a large % deficit from a few millimetres. Such windows are capped at Watch and
  left out of the "3 worst droughts" ranking. The ranking now shows the documented 2016-18, 1996-97 and 2008-09
  droughts instead of a Jan-Mar 2012 dry-season artefact.
* **Urban counties get urban actions.** Nairobi is marked urban, so pastoral actions (water pans, fodder, de-stocking,
  grazing land, seed) are not recommended there.
* **Ranking:** counties are ordered by alert level first (a Warning never ranks below a Watch), then by severity x a log
  population weight, so a large city cannot outrank a more severe alert on head-count alone.

## How is this different from the forecast on my phone or TV?

| | Phone / TV forecast | Climate Sentinel |
|---|---|---|
| Answers | What will the weather be? | Is it unusual *here*, who is exposed, and what should the county do? |
| Horizon | Hours to ~10 days | Last 3 months (drought) + next 7 days (heavy rain) + next 3 months (seasonal odds) |
| Reference | Absolute numbers | Each county's own 1991-2020 normal and extremes |
| Drought | Rarely covered | Core indicator |
| Rain after drought | Not covered | Compound alert: flags heavy rain on drought-hit land, when drought indicators already say "Normal" |
| People | Not considered | People per alert level; counties ranked by severity × people |
| Action | Stops at the forecast | Cited Kenya Red Cross / IFRC early actions + SMS text |
| Track record | Not shown | Shows its own test skill; falls back to 33% where it has none |

## How to run

### Docker (recommended)
```bash
cp .env.example .env                                      # add a free Gemini key (agent only)
docker build -f docker/api.Dockerfile -t climate-sentinel-api .
docker build -t climate-sentinel-web web
docker compose --profile pipeline run --rm pipeline       # download data + build outputs
docker compose up -d --no-build                           # http://localhost:8080  (API docs: /api/docs)
docker compose --profile train run --rm train             # optional: tune + register the outlook model
```
To rebuild from cached data only: `docker compose --profile pipeline run --rm pipeline python run_all.py --offline`.
`docker compose build` also works where Buildx bake may read the Dockerfiles; the two `docker build` lines avoid that permission prompt on Windows.
`data/`, `outputs/`, `logs/` and `models/` are bind-mounted, so results persist. Change the web port with `WEB_PORT=9000`.

### Local
```bash
python -m venv .venv && source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                      # GEMINI_API_KEY=... (agent only)

python run_all.py                     # downloads + caches all data, builds every output (first run: 10-40 min)
python run_all.py --offline           # rebuild from cached data only (no live cyclone check)
python -c "from sentinel import fetch; fetch.fetch_active_storms()"   # refresh the live active-storm list only
uvicorn sentinel.api.main:app --reload             # API on http://localhost:8000 (docs at /api/docs)
cd web && npm install && npm run dev               # web app on http://localhost:5173 (proxies /api)
python -m sentinel.train --trials 40               # tune the outlook model; promoted only if it passes the gate
python scripts/run_agent_tests.py     # the 6 agent test questions, with approval prompts -> logs/agent_test_log.md
pytest -q                             # pipeline, leakage, agent, API, insights, metrics, registry tests
cd web && npm test                    # frontend smoke tests
```

Open-Meteo's free tier limits calls per minute, hour and day, weighted by request size. The fetcher paces requests, waits for the minute or hour window to reset, saves after every chunk and resumes where it stopped. A first full download can exceed the daily quota, so it may need a second run the next day. Commit `data/raw/` after the first full download so others can rebuild everything with `--offline`.

## Training in Google Colab

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/MatoloJr/sentinel/blob/main/notebooks/colab/train_outlook.ipynb)

`notebooks/colab/train_outlook.ipynb` does the following:
1. Clones the repo and installs the package.
2. Loads the raw data, from the repo, a Drive zip or a fresh download.
3. Runs rolling-origin cross-validation with an Optuna search over model type, hyper-parameters, feature set and calibration.
4. Verifies the result once on the held-out years.
5. Plots reliability, economic value and per-county skill.
6. Exports `outlook-<version>.zip` to Drive.

Then, back on your machine:

```bash
python -m sentinel.model_registry import outlook-<version>.zip
python -m sentinel.model_registry promote <version>       # refuses if the gate fails (use --force to override)
python run_all.py --offline                                # backtest + live outlook now use the promoted config
```

**Promotion gate**: a model becomes active only if its test Brier skill score has a 90% bootstrap lower bound above 0, or if it beats the active model on Brier without worse calibration. Otherwise the pipeline keeps its inline default, and counties without skill keep publishing 33%. Re-running many searches against the same test years slowly overfits them, so treat repeated "wins" with caution.

## Evaluation metrics

| Component | Metrics | Why |
|---|---|---|
| Seasonal outlook (probability of the driest tercile) | **Brier skill score vs climatology and vs persistence** with block-bootstrap 90% CI (primary); reliability diagram + ECE; ROC AUC and PR AUC; POD, FAR, CSI, Peirce and Heidke skill at the warning threshold; **relative economic value** over cost/loss ratios; RPSS if extended to 3 categories | Skill must beat the free baselines; probabilities must mean what they say; managers need to know whether acting pays off |
| Breakdowns | All of the above per county and per season (MAM long rains vs OND short rains) | ENSO and IOD mainly drive the short rains; skill is local |
| Drought / heavy-rain indicators | Hit rate on documented disasters (IFRC, ReliefWeb, NDMA), false-alarm rate, lead time | Do alerts fire when it matters? |
| 7-day watch | POD / FAR / CSI for p95 and p99 exceedances, checked later against ERA5 | Short-range reliability |
| Advisory agent | Validator pass rate, citation coverage, unsupported-number rate, adversarial refusals, human approval rate, latency | Trustworthy text, not just a good model |

Implemented in `sentinel/metrics.py` and shown in the model card (`models/outlook/<version>/model_card.json`), on the Outlook page ("How good is it?") and on the Evidence page.

## Repository map

| Path | What |
|---|---|
| `run_all.py` | One-command pipeline: fetch → analyse → model → status → insights |
| `sentinel/config.py` | Counties, every threshold (with justification), documented reference events |
| `sentinel/fetch.py` | Open-Meteo ERA5 + forecast, NOAA ONI + DMI, IBTrACS, geoBoundaries, WorldPop (rate-limit aware) |
| `sentinel/climate.py` · `indicators.py` · `geo.py` | Weather behaviour · hazard indicators + validation · projected-CRS cyclone and population exposure |
| `sentinel/outlook.py` · `watch.py` | Seasonal outlook with baselines + bootstrap skill · 7-day watch |
| `sentinel/insights.py` | Deterministic insight cards, priority ranking, actions, public text and SMS |
| `sentinel/metrics.py` · `train.py` · `model_registry.py` | Verification metrics · CV + Optuna training CLI · versioned models and promotion gate |
| `sentinel/api/main.py` | FastAPI backend for the web app |
| `sentinel/agent/` | Tools, Gemini tool-calling loop, validator, run log, approval |
| `sentinel/playbook.json` → `PLAYBOOK.md` | The only actions the agent and the insight cards may recommend, each cited |
| `web/` | React + TypeScript + Vite app (MapLibre, Recharts, TanStack Query, Tailwind) |
| `docker/`, `docker-compose.yml`, `web/Dockerfile` | Containers: api, web (nginx), pipeline and train jobs |
| `configs/outlook.yaml` | Training search space |
| `notebooks/01_*.ipynb` · `02_*.ipynb` · `colab/train_outlook.ipynb` | Submission notebooks and the Colab training notebook (generated by `scripts/build_notebooks.py`) |
| `LIMITATIONS.md` · `DATA.md` · `PLAN.md` | Limitations note · sources and licences · team plan and demo script |

## Responsible AI in one paragraph
The LLM does no arithmetic. Tools compute every number, percentage and level. Each tool result gets an id (`T1`, `T2`, …) and the
advisory must cite it. A code validator checks every number, date and action id in the draft against the logged tool
results, and blocks drafts that invent numbers, cite unknown results, recommend non-playbook actions or deny a risk the
data shows. Blocked drafts cannot be approved. Unknown counties are refused (no fuzzy guessing). Missing data produces
"I don't know". Only public, aggregated climate data is sent to the LLM provider. No personal data is collected.
