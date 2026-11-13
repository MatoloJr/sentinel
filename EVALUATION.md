# Evaluation metrics

How Climate Sentinel Kenya is evaluated, component by component. Each metric is marked:
- **✅** computed today: in `sentinel/metrics.py`, `sentinel/outlook.py`, `sentinel/indicators.py` or the API, and shown in the app.
- **🟡** planned, not yet computed.

The numbers quoted are from the build of 2026-11-12. Re-run `python run_all.py` to refresh them.

---

## 1. Seasonal outlook model (main ML component)

**Task:** for each county and each month, give the probability that the next 3 months' rainfall falls in the **driest third** of historical totals (the below-normal tercile).

**Test design:**
- The model is tested on the last 8 complete years (2018 onward), which it never sees in training.
- Every normal, tercile threshold and standard deviation is computed from the training years only.
- Model selection uses rolling-origin cross-validation inside the training period.
- Leakage tests in `tests/test_outlook_leakage.py` check all of this.

**Baselines every model must beat:**
- **Climatology:** always forecast 33%.
- **Persistence:** "the next 3 months will be like the last 3".

### Probabilistic quality

| Metric | What it answers | Good value | Status |
|---|---|---|---|
| **Brier score** | Average squared error of the probabilities | Lower; climatology ≈ 0.22 | ✅ |
| **Brier Skill Score (BSS) vs climatology**, **primary metric** | Does the model add anything over "always 33%"? | > 0 = useful; 0 = no better than climatology | ✅ |
| **BSS 90% confidence interval** (block bootstrap over years) | Is the skill real or luck? | Lower bound > 0 | ✅ |
| **BSS vs persistence** | Does it beat the simplest forecast? | > 0 | ✅ |
| **Reliability diagram** | When it says 60%, does it happen ~60% of the time? | Points on the diagonal | ✅ |
| **Expected Calibration Error (ECE)** | Average gap between forecast and observed frequency | Close to 0 | ✅ |
| **ROC AUC** | Can it rank dry seasons above wet ones? | 0.5 = coin flip; higher is better | ✅ |
| **PR AUC** | Same idea, but more honest for a 1-in-3 event | Above the base rate (~0.31) | ✅ |

### Yes/no warning quality (at the chosen threshold)

| Metric | What it answers | Status |
|---|---|---|
| **POD** (hit rate) | Share of dry seasons that were warned | ✅ |
| **FAR** (false-alarm ratio) | Share of warnings that turned out wrong | ✅ |
| **POFD** (false-alarm rate) | Share of normal or wet seasons warned anyway | ✅ |
| **CSI** (critical success index) | Hits ÷ (hits + misses + false alarms) | ✅ |
| **Peirce / Hanssen-Kuipers skill score** | POD − POFD; fair for uncommon events, unlike accuracy | ✅ |
| **Heidke skill score** | Accuracy beyond what chance would give | ✅ |
| **Frequency bias** | Does it warn too often (> 1) or too rarely (< 1)? | ✅ |
| Precision / recall / F1 vs both baselines | The original backtest comparison | ✅ |

### Decision value

| Metric | What it answers | Status |
|---|---|---|
| **Relative economic value** (Richardson cost/loss model) | For a user whose preparation costs *C* and avoided loss is *L*: what share of a perfect forecast's savings does acting on this forecast capture? Plotted over cost/loss ratios. Above 0 = worth acting on. | ✅ |
| **RPSS** (ranked probability skill score) | Skill for full 3-category (below / near / above normal) forecasts | Function exists ✅; used only if the model is extended to 3 categories 🟡 |

### Breakdowns
All of the above are also reported **per county** and **per season**: the March–May long rains and the October–December short rains. ENSO and the Indian Ocean Dipole mostly drive the short rains, so skill is not the same everywhere. ✅

### How the metrics are used
- **County level:** if a county's BSS is ≤ 0, the app publishes **33%** (climatology) instead of the model's number and says so.
- **Promotion gate:** a newly trained model (from `sentinel/train.py` or Colab) becomes active only if:
  - its test BSS has a 90% lower bound above 0, **or**
  - it beats the active model on Brier score without worse calibration (ECE).

**Current result:** the pooled BSS is **−0.029** (90% CI −0.111 to +0.030) and the ROC AUC is **0.60**. There is no reliable skill overall; five coastal and north-eastern counties show weak, uncertain skill. The latest 40-trial tuning run was **not** promoted, because its CI included 0.

---

## 2. Hazard indicators (drought and heavy rain)

**Drought** is 3-month rain as a % of the 1991–2020 normal. **Heavy rain** is the 3-day total against the county's own p95 / p99 / p99.9.

| Metric | What it answers | Status |
|---|---|---|
| **Event hit rate** | During documented disasters (IFRC appeals, ReliefWeb / GLIDE, NDMA bulletins), did the indicator reach Watch or worse in the affected counties? | ✅ **20 of 23 county-events matched (87%)** |
| **Class frequency** | How often each level occurs per county, so levels are neither constant nor never-seen | ✅ |
| **False-alarm rate** | How often Warning fires with no reported impact | 🟡 |
| **Lead time** | How many weeks before the official declaration the indicator first reached Watch | 🟡 |

---

## 3. 7-day heavy-rain watch

| Metric | What it answers | Status |
|---|---|---|
| **POD / FAR / CSI for p95 and p99 exceedances** | Once the real rain is in the ERA5 archive, did the forecast Watch/Warning come true? | 🟡 needs forecasts saved each day to verify against later (planned `outputs/watch_verification.csv`) |

---

## 4. Advisory agent (Gemini)

| Metric | What it answers | Status |
|---|---|---|
| **Validator pass rate** | Share of drafts in which every number, date and action id traces back to a tool result | ✅ |
| **Citation coverage** | Share of sentences containing numbers that cite a tool result `[T#]` | ✅ |
| **Human approval rate** | Share of reviewed drafts that an officer approved | ✅ |
| **Median latency** | Time from question to draft | ✅ |
| **Average tool calls per draft** | How much evidence each answer uses | ✅ |
| **Unsupported-number rate** | Numbers the validator could not find in any tool result | Listed per draft ✅; aggregate rate 🟡 |
| **Refusal correctness** | On trick questions (unknown county, cyclone landfall, "say there's no risk"), does it refuse correctly? | Test script `scripts/run_agent_tests.py` ✅; automatic score 🟡 |

---

## 5. Operational health

| Metric | Status |
|---|---|
| **Data freshness:** days since the latest ERA5 day (alert in the notification bell if > 10) | ✅ |
| **Forecast age:** hours since the last 7-day forecast download | ✅ |
| **Pipeline success:** `run_all.py` completes and every output exists (test suite) | ✅ |
| **API latency (p95)** | 🟡 |

---

## Where to see them

| Place | What |
|---|---|
| App → **Outlook → "How good is it?"** | Headline scores, reliability diagram, economic-value curve, skill by county and season |
| App → **Evidence** | Event validation, active model card, agent quality, metric glossary |
| `outputs/outlook_metrics.csv`, `outlook_by_season.csv`, `validation.csv` | Raw tables |
| `models/outlook/<version>/model_card.json` | Full report for each trained model |
| `notebooks/colab/train_outlook.ipynb` | Plots of every metric after a training run |
