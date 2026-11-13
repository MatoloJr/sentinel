# Two-day team plan

The code skeleton already runs end to end (tested offline on a synthetic fixture). The team's job is to **run it on real
data, read the results, validate them honestly and write down what they mean**. Rubric weights are shown in brackets.

## Roles (works for 3-5 people; merge roles if you are fewer)

| Role | Owns | Rubric points it protects |
|---|---|---|
| **A. Data lead** | `run_all.py` first full download, `DATA.md` access dates, coverage checks, commit `data/raw/` | Data quality & provenance (20), reproducibility (10) |
| **B. Climate analyst** | Notebook 01: read trends, seasons and extremes; check validation misses and explain them; tune `REFERENCE_EVENTS` if a source gives better dates | Methodology (30), validation (20) |
| **C. ML lead** | Notebook 02: interpret skill per county and season; reliability plot; write the plain skill statement | Evaluation vs baselines (15) |
| **D. Agent & app** | Free API key, `scripts/run_agent_tests.py`, approvals, dashboard polish, deploy (optional) | Responsible AI (15), functionality (30) |
| **E. Docs & demo** (or shared) | `LIMITATIONS.md` with real findings, README, demo script and video | Docs (10), relevance & SDG (10) |

## Day 1: data, analysis, first baseline
| Time | Milestone | Who |
|---|---|---|
| 0:00-0:30 | Clone, `pip install -r requirements.txt`, `pytest -q` green on every laptop | all |
| 0:30-2:30 | `python run_all.py` (re-run if rate-limited; it resumes). Meanwhile read DATA.md / LIMITATIONS.md | A (others review code) |
| 2:30 | **Checkpoint 1:** `outputs/` populated, dashboard opens with real data | A, D |
| 2:30-5:00 | Execute notebook 01; sanity-check the seasons (should be bimodal; coast peaks Apr-Jun); WorldPop vs census within about 20% | B, A |
| 2:30-5:00 | Get a Gemini key; run the agent on 2 counties; read every tool call | D |
| 5:00-7:00 | Validation: do 2020-22 drought / 2023 + 2024 floods match? Write *why* misses happen (upstream rain, ERA5 smoothing) | B |
| 5:00-7:00 | Notebook 02 first read: which counties and seasons have skill? Note it, don't tune on the test set | C |
| End of day 1 | **Checkpoint 2:** both notebooks executed on real data, committed | all |

## Day 2: agent, dashboard, evidence, demo
| Time | Milestone | Who |
|---|---|---|
| 0:00-2:00 | `python scripts/run_agent_tests.py` → approve passing drafts → `logs/agent_test_log.md`; if a test fails, fix the prompt/tools and re-run (keep the failed run in the log; showing the fix is good evidence) | D |
| 0:00-2:00 | Replace the expected-skill wording in LIMITATIONS.md with the measured result | C, E |
| 2:00-4:00 | Dashboard walkthrough as a "county officer": anything confusing gets a caption | D, E |
| 4:00 | **Feature freeze.** Only fixes and docs after this | all |
| 4:00-6:00 | Fresh-clone test on a second laptop: `pip install` → `python run_all.py --offline` → app → notebooks | A |
| 4:00-6:00 | Record the 2-3 minute backup video (script below); export it; link it in the README | E |
| 6:00 | Push the final repo, double-check every deliverable on the checklist | all |

## Deliverables checklist
- [ ] Public repo: README (region, users, SDG, how to run), `requirements.txt`, `DATA.md` with access dates
- [ ] `notebooks/01_weather_behavior.ipynb` executed on real data (climatology, seasons, trends, extremes, indicators, cyclone exposure, validation)
- [ ] `notebooks/02_forecasting.ipynb` executed (model vs 2 baselines, per-county P/R/F1, BSS, plain skill statement)
- [ ] Dashboard runs: map + people per level, rainfall vs normal, outlook, cyclone exposure, agent advisory with approval
- [ ] `logs/agent_test_log.md` with the required tests (cannot answer, non-existent district, cyclone path, deny risk) **and approvals**
- [ ] `PLAYBOOK.md` (cited) and `LIMITATIONS.md` (with real findings)
- [ ] Reproducible demo + 2-3 minute backup video; "planning-support, not official warning" visible in app and README

## Backup video script (about 2:45)
1. **0:00-0:20** Problem in one line + region map. Disclaimer banner visible.
2. **0:20-0:50** Hazard map: switch drought → forecast heavy rain → cyclone layers; read the "people per level" table.
3. **0:50-1:20** District tab (Tana River): rainfall vs normal, 3-month % of normal with class lines, trend table with p-values.
4. **1:20-1:50** Outlook tab: point at one county with skill and one marked "No skill - use climatology" (the honesty moment). Show the by-season table.
5. **1:50-2:30** Agent: ask for a Tana River advisory, expand the tool log, show [T#] citations and the evidence check, click **Approve**. Then ask "where will the cyclone land?" and show the refusal.
6. **2:30-2:45** Evidence tab: validation table (matched and missed) and the limitations note.

## If you reach the Grand Finale (Real-World Impact, +30)
Natural adaptation: plug the indicator, outlook and agent pipeline into a county early-warning workflow, for example a
disaster-intelligence platform such as Hotspot or a Kenya Red Cross county branch dashboard, extended to sub-county wards and
river-basin rainfall (upstream Tana / Nzoia), which fixes the biggest limitation. Label partnerships as *proposed*, keep
measured prototype results separate from projected impact and name the key assumption to test next: that county officers act
on a cited, approved advisory faster than on today's bulletins.
