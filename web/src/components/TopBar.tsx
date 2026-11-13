import { useQuery } from "@tanstack/react-query";
import {
  Bell, BellRing, CheckCheck, Clock, CornerDownLeft, FileClock, LoaderCircle, Moon, Search, ShieldCheck, Sun, TrendingUp, UserRound, Users, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, LEVEL_RANK } from "../lib/api";
import { buildIndex, search, type Entry, type Group } from "../lib/search";
import { store, useApp } from "../lib/state";
import { toggleTheme, useTheme } from "../lib/theme";
import { useBreakpoint } from "../lib/useMedia";
import { LevelBadge, levelColor } from "./ui";

const TOP = "calc(10px + env(safe-area-inset-top))";
const ISLAND_BG = "color-mix(in oklab, var(--ink) 94%, var(--accent))";

/** Shared live data for the chrome (refreshes in the background so alerts stay current). */
function useChromeData() {
  const { mode } = useApp();
  const insights = useQuery({ queryKey: ["insights"], queryFn: api.insights, refetchInterval: 5 * 60_000 });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 5 * 60_000 });
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, enabled: mode === "manager", refetchInterval: 60_000 });
  return { insights, health, runs };
}

export function TopBar() {
  const { searchOpen } = useApp();
  const { mobile } = useBreakpoint();
  const hideSides = searchOpen && mobile;
  return (
    <header className="no-print pointer-events-none fixed inset-x-0 top-0 z-50" style={{ paddingTop: TOP }}>
      <div className={`relative mx-auto flex h-12 items-start px-3 ${mobile ? "justify-start" : "justify-center"}`}>
        <Link
          to="/"
          viewTransition
          aria-label="Climate Sentinel home"
          className="pointer-events-auto absolute left-3 top-0 hidden h-12 w-12 place-items-center rounded-full sm:grid"
          style={{ background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)", opacity: hideSides ? 0 : 1, transition: "opacity 150ms" }}
        >
          <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden>
            <circle cx="16" cy="16" r="14" fill="var(--accent)" />
            <path d="M9 19c3-6 11-6 14 0" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
          </svg>
        </Link>
        <SearchIsland />
        <div
          className="absolute right-3 top-0 flex items-center gap-2"
          style={{ opacity: hideSides ? 0 : 1, pointerEvents: hideSides ? "none" : "auto", transition: "opacity 150ms" }}
        >
          <ViewSwitch />
          <ThemeButton />
          <NotificationBell />
        </div>
      </div>
    </header>
  );
}

// ------------------------------------------------------------------ view switch (manager <-> public)
function ViewSwitch() {
  const { mode, setMode } = useApp();
  const next = mode === "manager" ? "public" : "manager";
  const Icon = mode === "manager" ? UserRound : Users;
  return (
    <button
      onClick={() => setMode(next)}
      aria-label={`${mode === "manager" ? "Manager" : "Public"} view. Switch to ${next} view`}
      title={`You are in the ${mode} view. Click for the ${next} view.`}
      className="flex h-12 min-w-12 items-center justify-center gap-2 rounded-full px-3.5"
      style={{ background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)" }}
    >
      <Icon size={20} aria-hidden />
      <span className="hidden text-sm font-semibold lg:inline">{mode === "manager" ? "Manager" : "Public"}</span>
    </button>
  );
}

// ------------------------------------------------------------------ theme switch (top right, left of the bell)
function ThemeButton() {
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className="grid h-12 w-12 place-items-center rounded-full"
      style={{ background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)" }}
    >
      {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
    </button>
  );
}

// ------------------------------------------------------------------ search island
function SearchIsland() {
  const { mode, setMode, searchOpen, setSearchOpen, agentBusy } = useApp();
  const { insights, runs } = useChromeData();
  const theme = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { mobile, lg } = useBreakpoint();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const index = useMemo(
    () => buildIndex({ mode, cards: insights.data?.counties, runs: runs.data, theme }),
    [mode, insights.data, runs.data, theme],
  );
  const results = useMemo(() => {
    if (q.trim()) {
      const r = search(index, q);
      if (mode === "manager" && q.trim().length > 2)
        r.push({ id: "ask", group: "Commands", label: `Ask Gemini: “${q.trim()}”`, to: `/advisory?q=${encodeURIComponent(q.trim())}` });
      return r;
    }
    // empty query: recent picks, current alerts, pages
    const recent = store.get<string[]>("cs.recent", []).map((id) => index.find((e) => e.id === id)).filter(Boolean) as Entry[];
    const alerts = index.filter((e) => e.group === "Alerts" && LEVEL_RANK[e.level ?? ""] >= 2);
    const pages = index.filter((e) => e.group === "Pages");
    const seen = new Set<string>();
    return [
      ...recent.map((e) => ({ ...e, group: "Recent" as unknown as Group })),
      ...alerts,
      ...pages,
    ].filter((e) => (seen.has(e.id) ? false : (seen.add(e.id), true)));
  }, [q, index, mode]);

  useEffect(() => setSel(0), [q, searchOpen]);
  useEffect(() => {
    if (searchOpen) setTimeout(() => inputRef.current?.focus(), 20);
    else {
      setQ("");
      inputRef.current?.blur();
    }
  }, [searchOpen]);
  useEffect(() => setSearchOpen(false), [pathname, setSearchOpen]);
  useEffect(() => {
    if (!searchOpen) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setSearchOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [searchOpen, setSearchOpen]);

  const choose = (e?: Entry) => {
    if (!e) return;
    if (e.id !== "ask") store.set("cs.recent", [e.id, ...store.get<string[]>("cs.recent", []).filter((x) => x !== e.id)].slice(0, 5));
    setSearchOpen(false);
    if (e.command === "toggle-mode") setMode(mode === "manager" ? "public" : "manager");
    else if (e.command === "toggle-theme") toggleTheme();
    else if (e.to) navigate(e.to, { viewTransition: true });
  };

  // right side holds view switch + theme + bell (3 x 48px, the switch grows a label on wide screens);
  // phones hide the logo and left-align the search
  const width = searchOpen
    ? mobile ? "calc(100vw - 24px)" : "min(640px, calc(100vw - 32px))"
    : mobile ? "calc(100vw - 200px)" : lg ? "min(520px, calc(100vw - 560px))" : "min(520px, calc(100vw - 384px))";
  let lastGroup = "";

  return (
    <div
      ref={boxRef}
      className="pointer-events-auto relative z-10"
      style={{
        width,
        background: ISLAND_BG,
        color: "var(--surface)",
        borderRadius: searchOpen ? 24 : 999,
        boxShadow: "var(--shadow)",
        transition: "width 240ms ease-out, border-radius 240ms ease-out",
        overflow: "hidden",
      }}
    >
      <div className="flex h-12 items-center gap-2 pl-4 pr-2">
        {agentBusy && !searchOpen ? <LoaderCircle size={18} className="shrink-0 animate-spin" aria-hidden /> : <Search size={18} className="shrink-0 opacity-75" aria-hidden />}
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            if (!searchOpen) setSearchOpen(true);
          }}
          onFocus={() => setSearchOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
            if (e.key === "Enter") choose(results[sel]);
            if (e.key === "Escape") setSearchOpen(false);
          }}
          placeholder={agentBusy ? "Gemini is drafting an advisory…" : mobile ? "Search" : "Search counties, alerts, actions, pages…"}
          aria-label="Universal search"
          role="combobox"
          aria-expanded={searchOpen}
          aria-controls="search-results"
          aria-activedescendant={searchOpen && results[sel] ? `sr-${results[sel].id}` : undefined}
          className="h-full min-w-0 flex-1 bg-transparent text-[0.95rem] outline-none placeholder:text-[color:inherit] placeholder:opacity-65"
          style={{ boxShadow: "none" }}
        />
        {searchOpen ? (
          <button onClick={() => setSearchOpen(false)} aria-label="Close search" className="grid h-10 w-10 shrink-0 place-items-center rounded-full hover:bg-white/10">
            <X size={18} />
          </button>
        ) : (
          !mobile && <kbd className="shrink-0 rounded-md px-2 py-0.5 text-xs opacity-70" style={{ background: "rgb(255 255 255 / .1)" }}>Ctrl K</kbd>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateRows: searchOpen ? "1fr" : "0fr", transition: "grid-template-rows 240ms ease-out" }}>
        <div style={{ overflow: "hidden" }}>
          <ul id="search-results" role="listbox" aria-label="Search results" className="max-h-[min(62dvh,520px)] overflow-y-auto px-2 pb-2">
            {results.length === 0 && (
              <li className="px-3 py-6 text-center text-sm opacity-75">
                No match. Climate Sentinel covers 14 counties; try a county, HQ town, hazard or action id.
              </li>
            )}
            {results.map((e, i) => {
              const header = e.group !== lastGroup ? (lastGroup = e.group) : null;
              return (
                <li key={`${e.group}-${e.id}`} role="presentation">
                  {header && <p className="px-3 pt-3 pb-1 text-[0.7rem] font-bold uppercase tracking-wider opacity-60">{header}</p>}
                  <div
                    id={`sr-${e.id}`}
                    role="option"
                    aria-selected={i === sel}
                    onMouseEnter={() => setSel(i)}
                    onClick={() => choose(e)}
                    className="flex cursor-pointer items-center gap-3 rounded-xl px-3"
                    style={{ minHeight: 46, background: i === sel ? "rgb(255 255 255 / .12)" : undefined }}
                  >
                    {e.level && <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: levelColor(e.level) }} />}
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{e.label}</span>
                      {e.hint && <span className="block truncate text-xs opacity-65">{e.hint}</span>}
                    </span>
                    {i === sel && <CornerDownLeft size={14} className="shrink-0 opacity-70" aria-hidden />}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ notifications
interface Note {
  id: string;
  title: string;
  body: string;
  to: string;
  level?: string;
  icon: typeof Bell;
}

export function NotificationBell() {
  const { mode, notificationsOpen, setNotificationsOpen } = useApp();
  const { insights, health, runs } = useChromeData();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState<string[]>(() => store.get("cs.seen", []));

  const notes: Note[] = useMemo(() => {
    const out: Note[] = [];
    const cards = [...(insights.data?.counties ?? [])].sort((a, b) => b.priority_score - a.priority_score);
    for (const c of cards)
      if (LEVEL_RANK[c.overall_level] >= 2)
        out.push({ id: `lvl:${c.county}:${c.overall_level}:${c.headline}`, title: c.county, body: c.headline, level: c.overall_level, to: `/county/${encodeURIComponent(c.county)}`, icon: BellRing });
    for (const c of cards)
      if (c.rising && LEVEL_RANK[c.overall_level] < 2)
        out.push({ id: `rise:${c.county}:${insights.data?.generated_for}`, title: `Risk rising in ${c.county}`, body: c.headline, level: c.overall_level, to: `/county/${encodeURIComponent(c.county)}`, icon: TrendingUp });
    if (mode === "manager")
      for (const r of runs.data ?? [])
        if (r.status === "draft")
          out.push({ id: `draft:${r.run_id}`, title: "Advisory awaiting approval", body: r.question, to: `/advisory?run=${encodeURIComponent(r.run_id)}`, icon: FileClock });
    const lag = health.data?.data_lag_days;
    if (lag != null && lag > 10)
      out.push({ id: `stale:${health.data?.built_utc}`, title: "Data is getting old", body: `Latest weather data is ${lag} days old. Re-run the pipeline.`, to: "/evidence", icon: Clock });
    return out;
  }, [insights.data, runs.data, health.data, mode]);

  const unread = notes.filter((n) => !seen.includes(n.id));
  const markRead = (ids: string[]) => {
    const next = Array.from(new Set([...seen, ...ids])).slice(-300);
    setSeen(next);
    store.set("cs.seen", next);
  };

  useEffect(() => setNotificationsOpen(false), [pathname, setNotificationsOpen]);
  useEffect(() => {
    if (!notificationsOpen) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setNotificationsOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
    };
  }, [notificationsOpen, setNotificationsOpen]);

  const lag = health.data?.data_lag_days;
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setNotificationsOpen(!notificationsOpen)}
        aria-expanded={notificationsOpen}
        aria-haspopup="dialog"
        aria-label={`Notifications${unread.length ? ` (${unread.length} unread)` : ""}`}
        className="relative grid h-12 w-12 place-items-center rounded-full"
        style={{ background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)" }}
      >
        {unread.length ? <BellRing size={20} className="bell-ring" /> : <Bell size={20} />}
        {unread.length > 0 && (
          <span className="num absolute -top-0.5 -right-0.5 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold" style={{ background: "var(--lvl-warning)", color: "#fff", boxShadow: "0 0 0 2px var(--surface)" }}>
            {unread.length > 9 ? "9+" : unread.length}
          </span>
        )}
      </button>

      {notificationsOpen && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="rise fixed right-2 left-2 mt-2 overflow-hidden rounded-3xl sm:absolute sm:left-auto sm:right-0 sm:w-[400px]"
          style={{ background: "var(--surface)", border: "1px solid var(--surface-3)", boxShadow: "var(--shadow)", top: "auto" }}
        >
          <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-2" style={{ borderBottom: "1px solid var(--surface-3)" }}>
            <h2 className="text-base">Notifications</h2>
            <button className="btn" style={{ minHeight: 36, padding: "0 10px", fontSize: 13 }} disabled={!unread.length} onClick={() => markRead(notes.map((n) => n.id))}>
              <CheckCheck size={15} /> Mark all read
            </button>
          </div>
          <ul className="max-h-[min(60dvh,480px)] overflow-y-auto p-2">
            {notes.length === 0 && <li className="muted p-6 text-center text-sm">All clear: no county at Warning and nothing awaiting review.</li>}
            {notes.map((n) => {
              const isNew = !seen.includes(n.id);
              const Icon = n.icon;
              return (
                <li key={n.id}>
                  <button
                    onClick={() => {
                      markRead([n.id]);
                      setNotificationsOpen(false);
                      navigate(n.to, { viewTransition: true });
                    }}
                    className="flex w-full items-start gap-3 rounded-2xl p-3 text-left hover:bg-[var(--surface-2)]"
                    style={{ minHeight: 44 }}
                  >
                    <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full" style={{ background: n.level ? `color-mix(in oklab, ${levelColor(n.level)} 30%, transparent)` : "var(--accent-soft)" }}>
                      <Icon size={16} aria-hidden />
                    </span>
                    <span className="grid min-w-0 flex-1 gap-0.5">
                      <span className="flex items-center gap-2">
                        <span className={`truncate text-sm ${isNew ? "font-bold" : "font-medium"}`}>{n.title}</span>
                        {n.level && LEVEL_RANK[n.level] >= 2 && <LevelBadge level={n.level} size="sm" />}
                      </span>
                      <span className="muted line-clamp-2 text-sm">{n.body}</span>
                    </span>
                    {isNew && <span aria-label="unread" className="mt-2 h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--accent)" }} />}
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="subtle flex items-center gap-2 px-4 py-2.5" style={{ borderTop: "1px solid var(--surface-3)" }}>
            <ShieldCheck size={14} aria-hidden /> Weather data to {health.data?.daily_range?.[1] ?? "…"}
            {lag != null && ` (${lag} days)`} · refreshes every 5 min
          </p>
        </div>
      )}
    </div>
  );
}
