# Limitations note

**Purpose.** Climate Sentinel supports planning. It does not issue warnings, and KMD and NDOC warnings always override it.

## Where the data is weak
- **Rain is modelled (ERA5), not measured.** It under-states intense local storms and over-counts drizzle days. Weakest in the
  **arid north-east (Mandera, Wajir, Garissa, Marsabit, Turkana)**, where few gauges anchor the model, and on the **coast**,
  where a 25 km cell mixes land and sea.
- **One point per county.** Turkana is about 68,000 km²; one grid cell at Lodwar cannot represent the whole county. Counties with
  strong internal contrasts (Makueni highlands vs lowlands, Kilifi coast vs hinterland) are averaged away.
- **Floods are about rivers, not only local rain.** Tana River floods usually come from rain in the central highlands,
  hundreds of km upstream of Hola. Our local 3-day indicator can **miss riverine floods** (see `outputs/validation.csv`).
  Urban flash floods (Nairobi) depend on drainage, which we do not model.
- **People are KNBS 2019 census county totals.** They are 7 years old and do not show who is most vulnerable. Mobile
  pastoralists may not be where the census counted them. WorldPop 2020 is kept only as a cross-check (`outputs/population.csv`)
  because it over-counts the arid north-east by +89% to +199%.

## Where the model is weak
- **Seasonal outlook.** Only about 30 years of training and 8 test years (roughly 8 forecasts per county per target season).
  Bootstrap intervals are wide. Counties marked "No skill" in `outputs/outlook_metrics.csv` publish climatology (33%), not
  the model. ENSO and IOD mainly drive the **Oct-Dec short rains**; expect little or no skill for the **Mar-May long rains**,
  which are known to be hard to predict.
- **Dry-season targets are not forecast** (normal under 30 mm), so outlooks pause for parts of the year in arid counties.
- **7-day watch thresholds come from ERA5,** but forecasts come from other models with different rainfall statistics.
- **Rain after drought (compound alert).** The 12-month look-back and the 75% threshold were fixed before validation, but
  only 3 documented events (20 county-events) were available. It caught 5 at Warning and 3 at Watch. Most Oct-Nov 2019
  counties were missed because ERA5 showed near-normal rain over the 12 months at the HQ point, while OCHA described a
  national drought. It uses one point per county, so a dry hinterland with a wet HQ town is missed. It does not raise
  the flood level by itself; it is a separate alert that adds to the priority score.
- **Live cyclone check uses the IBTrACS ACTIVE list,** which is provisional and can lag by a day or more. With
  `--offline`, or when the list is older than 3 days, the check is marked unavailable and no Watch is raised. KMD and
  RSMC La Réunion remain the only sources for live storms.
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
