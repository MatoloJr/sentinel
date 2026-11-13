import { Link } from "react-router-dom";
import { Disclaimer, RTable, Section } from "../components/ui";

const ROWS: [string, string, string][] = [
  ["Question it answers", "What will the weather be? (“40 mm on Thursday”)", "Is that unusual here, and what should we do? (“40 mm in 3 days is above Garissa's 1-in-100-day level: Flood Warning”)"],
  ["Time horizon", "Hours to about 10 days", "Three horizons at once: the last 3 months (drought), the next 7 days (heavy rain) and the next 3 months (seasonal odds)"],
  ["Reference point", "Absolute numbers", "Each county's own 1991–2020 normal and its own extremes, so 20 mm can matter in Wajir but not in Busia"],
  ["Slow disasters", "Rarely mentioned", "Tracks drought as 3-month rain against normal, the hazard that affects the most Kenyans"],
  ["People", "Not considered", "Counts the people living under each alert level and ranks counties by severity × people"],
  ["What to do", "Stops at the forecast", "Each alert unlocks cited actions from Kenya Red Cross / IFRC early-action protocols, plus an SMS-length message"],
  ["Honesty about skill", "One number, no track record shown", "Shows its own test record. Where the seasonal model did not beat normal odds, it says so and publishes 33%"],
  ["Accountability", "Broadcast as is", "AI drafts cite every number, a validator blocks invented ones, and a named person approves before release"],
];

export function About() {
  return (
    <div className="page grid gap-8">
      <header className="grid gap-3">
        <h1>How is this different from the forecast on your phone or TV?</h1>
        <p className="muted max-w-[68ch] text-lg">
          Your phone tells you the weather. Climate Sentinel tells a county what the weather <em>means</em>, compared with
          what is normal there, who is exposed and which preparations to start.
        </p>
      </header>
      <RTable
        stack
        rows={ROWS}
        rowKey={([k]) => k}
        cols={[
          { key: "k", header: "", primary: true, className: "font-semibold", cell: ([k]) => k },
          { key: "a", header: "Phone / TV", className: "muted text-sm", cell: ([, a]) => <span className="block text-left">{a}</span> },
          { key: "b", header: "Climate Sentinel", className: "text-sm", cell: ([, , b]) => <span className="block text-left">{b}</span> },
        ]}
      />
      <Section title="Where the numbers come from">
        <ul className="card ml-0 grid list-none gap-2 text-sm">
          <li><b>Rainfall and temperature:</b> ERA5 reanalysis (ECMWF, via Open-Meteo) since 1991 at each county HQ point. A model estimate, not a rain gauge.</li>
          <li><b>7-day forecast:</b> Open-Meteo numerical weather prediction, refreshed with each pipeline run.</li>
          <li><b>Climate drivers:</b> NOAA ONI (El Niño / La Niña) and the Indian Ocean Dipole index.</li>
          <li><b>Cyclones:</b> IBTrACS best tracks since 1981 (history only, never a path forecast).</li>
          <li><b>People:</b> KNBS 2019 census county totals. WorldPop 2020 is kept as a cross-check only (it over-counts the arid north-east by up to +199%).</li>
          <li><b>Rain after drought:</b> heavy rain (observed or forecast) on land that had at most 75% of normal rain over the previous 12 months. Validated on documented 2019 and 2023 rain-after-drought disasters (see Evidence).</li>
          <li><b>Actions:</b> Kenya Red Cross / IFRC Early Action Protocols and IFRC public-awareness messages.</li>
        </ul>
      </Section>
      <p>
        <Link to="/evidence">See how well it performs →</Link>
      </p>
      <Disclaimer text="Official warnings from the Kenya Meteorological Department (KMD) and the National Disaster Operations Centre always take priority." />
    </div>
  );
}
