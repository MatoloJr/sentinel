import { Link } from "react-router-dom";
import { Disclaimer, Section } from "../components/ui";

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
      <div className="card scroll-x">
        <table className="table">
          <thead><tr><th /><th>Phone / TV forecast</th><th>Climate Sentinel</th></tr></thead>
          <tbody>
            {ROWS.map(([k, a, b]) => (
              <tr key={k}><td className="font-semibold">{k}</td><td className="muted text-sm">{a}</td><td className="text-sm">{b}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <Section title="Where the numbers come from">
        <ul className="card ml-0 grid list-none gap-2 text-sm">
          <li><b>Rainfall and temperature:</b> ERA5 reanalysis (ECMWF, via Open-Meteo) since 1991 at each county HQ point. A model estimate, not a rain gauge.</li>
          <li><b>7-day forecast:</b> Open-Meteo numerical weather prediction, refreshed with each pipeline run.</li>
          <li><b>Climate drivers:</b> NOAA ONI (El Niño / La Niña) and the Indian Ocean Dipole index.</li>
          <li><b>Cyclones:</b> IBTrACS best tracks since 1981 (history only, never a path forecast).</li>
          <li><b>People:</b> WorldPop 2020, checked against the 2019 census.</li>
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
