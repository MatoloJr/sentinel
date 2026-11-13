# Limitations note

**Purpose.** Climate Sentinel supports planning. It does not issue warnings and KMD and NDOC warnings always override it.

## Where the data is weak
- **Rain is modelled (ERA5), not measured.** It under-states intense local storms and over-counts drizzle days. Weakest in the
  **arid north-east (Mandera, Wajir, Garissa, Marsabit, Turkana)**, where few gauges anchor the model and on the **coast**,
  where a 25 km cell mixes land and sea.
- **One point per county.** Turkana is about 68,000 km²; one grid cell at Lodwar cannot represent the whole county. Counties with
  strong internal contrasts (Makueni highlands vs lowlands, Kilifi coast vs hinterland) are averaged away.
- **Floods are about rivers, not only local rain.** Tana River floods usually come from rain in the central highlands,
  hundreds of km upstream of Hola. Our local 3-day indicator can **miss riverine floods** (see `outputs/validation.csv`).
  Urban flash floods (Nairobi) depend on drainage, which we do not model.
- **Population is a 2020 model estimate (WorldPop)**, checked against the 2019 census (`outputs/population.csv`). It does not
  show who is most vulnerable and mobile pastoralists may not be counted where they actually are.

## Where the model is weak
- **Seasonal outlook.** Only about 30 years of training and 8 test years (roughly 8 forecasts per county per target season).
  Bootstrap intervals are wide. Counties marked "No skill" in `outputs/outlook_metrics.csv` publish climatology (33%), not
  the model. ENSO and IOD mainly drive the **Oct-Dec short rains**; expect little or no skill for the **Mar-May long rains**,
  which are known to be hard to predict.
- **Dry-season targets are not forecast** (normal under 30 mm), so outlooks pause for parts of the year in arid counties.
- **7-day watch thresholds come from ERA5,** but forecasts come from other models with different rainfall statistics.
- **Cyclone exposure is historical.** Few storms come within 300 km of Kenya, so the counts are small and the decade trends are not
  statistically meaningful. The system never forecasts tracks.
- **Climate-index lag.** If ONI or DMI publication is late, the last value is carried forward (up to 3 months) and flagged.

## Least-trusted districts and seasons
Arid north-east counties during the Mar-May long rains (sparse observations, low skill); Tana River for floods
(upstream-driven); Nairobi for flash floods (urban drainage); all coastal counties for cyclones (rare events).

## Who might be missed
Mobile pastoralists outside settlements; informal-settlement residents in flood zones (population is spread evenly
inside 1 km cells); people downstream of rain they never saw; anyone without radio or SMS access to the advisories;
non-English and non-Swahili speakers (the agent writes in English only).

## AI-specific limits
The LLM can still word things poorly, so every draft needs human approval. The validator checks numbers, citations,
action ids and risk-denial phrases, but it cannot judge whether the advice is *appropriate* for a local situation.
Free-tier LLM APIs can be rate-limited or unavailable, in which case the dashboard still works and the agent reports it is unavailable.
