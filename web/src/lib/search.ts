import type { InsightCard, RunSummary } from "./api";
import { COUNTIES, LEVEL_RANK } from "./api";
import type { Mode } from "./state";

export type Group = "Counties" | "Alerts" | "Actions" | "Pages" | "Advisories" | "Commands";
export const GROUP_ORDER: Group[] = ["Alerts", "Counties", "Pages", "Actions", "Advisories", "Commands"];

export interface Entry {
  id: string;
  group: Group;
  label: string;
  hint?: string;
  level?: string;
  /** extra searchable text (towns, ids, headlines) */
  keywords?: string;
  to?: string;
  command?: "toggle-mode" | "toggle-theme";
}

export const TOWNS: Record<string, string> = {
  Turkana: "Lodwar", Marsabit: "Marsabit", Mandera: "Mandera", Wajir: "Wajir", Garissa: "Garissa",
  "Tana River": "Hola", Makueni: "Wote", Nairobi: "Nairobi", Kisumu: "Kisumu", Busia: "Busia",
  Lamu: "Lamu", Kilifi: "Kilifi", Mombasa: "Mombasa", Kwale: "Kwale",
};

const PAGES: { label: string; to: string; keywords: string }[] = [
  { label: "Overview map", to: "/", keywords: "home map priority needs attention" },
  { label: "Counties", to: "/county", keywords: "county list choose" },
  { label: "Outlook & 7-day watch", to: "/outlook", keywords: "seasonal forecast rain next week probability skill" },
  { label: "Cyclone exposure", to: "/cyclones", keywords: "storm tracks coast ibtracs" },
  { label: "Draft an advisory", to: "/advisory", keywords: "gemini agent ask approve" },
  { label: "Evidence & model card", to: "/evidence", keywords: "validation metrics brier model card accuracy" },
  { label: "How is this different from the TV forecast?", to: "/about", keywords: "about phone tv why sources" },
];

const enc = encodeURIComponent;

export function buildIndex(opts: { mode: Mode; cards?: InsightCard[]; runs?: RunSummary[]; theme: string }): Entry[] {
  const { mode, cards = [], runs = [], theme } = opts;
  const byCounty = new Map(cards.map((c) => [c.county, c]));
  const out: Entry[] = [];

  for (const c of COUNTIES) {
    const card = byCounty.get(c);
    out.push({
      id: `county:${c}`, group: "Counties", label: c, level: card?.overall_level,
      hint: TOWNS[c] !== c ? `HQ ${TOWNS[c]}` : card?.zone, keywords: `${TOWNS[c]} ${card?.zone ?? ""} county`,
      to: `/county/${enc(c)}`,
    });
  }
  for (const card of cards) {
    if (LEVEL_RANK[card.overall_level] >= 1) {
      out.push({
        id: `alert:${card.county}`, group: "Alerts", label: `${card.county}: ${card.headline.split(":")[0]}`,
        hint: card.headline.split(":").slice(1).join(":").trim(), level: card.overall_level,
        keywords: `${card.headline} ${Object.entries(card.hazard_levels).map(([h, l]) => `${h} ${l}`).join(" ")} alert warning`,
        to: `/county/${enc(card.county)}`,
      });
    }
  }
  for (const p of PAGES) {
    out.push({ id: `page:${p.to}`, group: "Pages", label: p.label, keywords: p.keywords, to: p.to });
  }
  if (mode === "manager") {
    const seen = new Map<string, { a: InsightCard["actions"][number]; counties: string[] }>();
    for (const card of cards)
      for (const a of card.actions) {
        const s = seen.get(a.id) ?? { a, counties: [] };
        s.counties.push(card.county);
        seen.set(a.id, s);
      }
    for (const { a, counties } of seen.values()) {
      out.push({
        id: `action:${a.id}`, group: "Actions", label: `${a.id} · ${a.action}`, level: a.level,
        hint: `${counties.slice(0, 3).join(", ")}${counties.length > 3 ? ` +${counties.length - 3}` : ""}`,
        keywords: `${a.hazard} ${a.level} ${a.timeframe} ${counties.join(" ")}`, to: `/county/${enc(counties[0])}`,
      });
    }
    for (const r of runs.slice(0, 30)) {
      out.push({
        id: `run:${r.run_id}`, group: "Advisories", label: r.question, hint: `${r.status} · ${new Date(r.started_utc).toLocaleDateString()}`,
        keywords: r.status, to: `/advisory?run=${enc(r.run_id)}`,
      });
    }
  }
  out.push({ id: "cmd:mode", group: "Commands", label: `Switch to ${mode === "manager" ? "public" : "manager"} view`, keywords: "mode public manager view", command: "toggle-mode" });
  out.push({ id: "cmd:theme", group: "Commands", label: `Switch to ${theme === "dark" ? "light" : "dark"} theme`, keywords: "dark light theme colour", command: "toggle-theme" });
  return out;
}

/** Every query token must appear; label matches outrank keyword matches. */
export function search(index: Entry[], query: string, limitPerGroup = 6): Entry[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const tokens = q.split(/\s+/);
  const scored: { e: Entry; s: number }[] = [];
  for (const e of index) {
    const label = e.label.toLowerCase();
    const hay = `${label} ${(e.hint ?? "").toLowerCase()} ${(e.keywords ?? "").toLowerCase()}`;
    if (!tokens.every((t) => hay.includes(t))) continue;
    let s = 0;
    if (label.startsWith(q)) s += 100;
    else if (label.includes(q)) s += 60;
    s += tokens.filter((t) => label.includes(t)).length * 10;
    if (e.level) s += (LEVEL_RANK[e.level] ?? 0) * 3;
    scored.push({ e, s });
  }
  scored.sort((a, b) => b.s - a.s);
  const perGroup = new Map<Group, number>();
  const res: Entry[] = [];
  for (const { e } of scored) {
    const n = perGroup.get(e.group) ?? 0;
    if (n >= limitPerGroup) continue;
    perGroup.set(e.group, n + 1);
    res.push(e);
  }
  return GROUP_ORDER.flatMap((g) => res.filter((e) => e.group === g));
}
