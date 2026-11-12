import { useQuery } from "@tanstack/react-query";
import {
  BellRing, ChevronDown, CloudRain, Command, Compass, Info, LayoutGrid, LoaderCircle, Map as MapIcon,
  MessageSquareText, ShieldCheck, Tornado, Users,
} from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api, LEVEL_RANK } from "../lib/api";
import { useApp } from "../lib/state";
import { LevelBadge } from "./ui";

type Item = { to: string; label: string; icon: typeof MapIcon };

export const MANAGER_NAV: Item[] = [
  { to: "/", label: "Overview", icon: MapIcon },
  { to: "/county", label: "County", icon: LayoutGrid },
  { to: "/outlook", label: "Outlook", icon: CloudRain },
  { to: "/cyclones", label: "Cyclones", icon: Tornado },
  { to: "/advisory", label: "Advisory", icon: MessageSquareText },
];
export const PUBLIC_NAV: Item[] = [
  { to: "/", label: "My area", icon: Compass },
  { to: "/county", label: "County", icon: LayoutGrid },
  { to: "/cyclones", label: "Cyclones", icon: Tornado },
  { to: "/about", label: "Why this", icon: Info },
];

const isActive = (to: string, path: string) => (to === "/" ? path === "/" : path.startsWith(to));

/**
 * Dynamic island: a floating pill centred at the bottom. It hides on scroll-down, returns on
 * scroll-up, slides an indicator under the active destination and morphs open to show live
 * alerts, data freshness and the agent's drafting state.
 */
export function Island() {
  const { mode, setMode, agentBusy, setPaletteOpen } = useApp();
  const nav = mode === "manager" ? MANAGER_NAV : PUBLIC_NAV;
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);

  const insights = useQuery({ queryKey: ["insights"], queryFn: api.insights, staleTime: 60_000 });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, staleTime: 60_000 });
  const alerts = (insights.data?.counties ?? [])
    .filter((c) => LEVEL_RANK[c.overall_level] >= 2)
    .sort((a, b) => b.priority_score - a.priority_score);
  const watchN = insights.data?.region.counties_at_watch_or_above ?? 0;

  // hide on scroll down, show on scroll up
  useEffect(() => {
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      if (Math.abs(y - last) < 8) return;
      setHidden(y > last && y > 120);
      last = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (agentBusy) setOpen(true);
  }, [agentBusy]);

  // sliding active indicator
  useLayoutEffect(() => {
    const bar = barRef.current;
    if (!bar) return;
    const measure = () => {
      const el = bar.querySelector<HTMLElement>("[data-active='true']");
      if (!el) return setInd(null);
      setInd({ x: el.offsetLeft, w: el.offsetWidth });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(bar);
    return () => ro.disconnect();
  }, [pathname, mode]);

  const lag = health.data?.data_lag_days;
  const fresh = lag == null ? null : lag <= 10 ? "Fresh" : "Stale";

  return (
    <div
      className="no-print fixed inset-x-0 z-40 flex justify-center px-3"
      style={{
        bottom: "calc(12px + env(safe-area-inset-bottom))",
        transform: hidden && !open ? "translateY(140%)" : "none",
        transition: "transform 220ms ease-out",
        pointerEvents: "none",
      }}
    >
      <nav
        aria-label="Main"
        className="w-full max-w-[640px]"
        style={{
          pointerEvents: "auto",
          background: "color-mix(in oklab, var(--ink) 94%, var(--accent))",
          color: "var(--surface)",
          borderRadius: open ? 26 : 999,
          boxShadow: "var(--shadow)",
          transition: "border-radius 220ms ease-out",
          overflow: "hidden",
        }}
      >
        {/* expanding panel */}
        <div
          id="island-panel"
          style={{
            display: "grid",
            gridTemplateRows: open ? "1fr" : "0fr",
            transition: "grid-template-rows 240ms ease-out",
          }}
        >
          <div style={{ overflow: "hidden" }}>
            <div className="grid gap-3 px-4 pt-4 pb-2">
              {agentBusy && (
                <div className="flex items-center gap-2 text-sm font-semibold" role="status">
                  <LoaderCircle size={16} className="animate-spin" aria-hidden />
                  Gemini is drafting an advisory: calling tools, then the validator checks every number…
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="chip" style={{ background: "rgb(255 255 255 / .1)", color: "inherit" }}>
                  <ShieldCheck size={14} aria-hidden /> {fresh ?? "…"} data · ERA5 to {health.data?.daily_range?.[1] ?? "…"}
                </span>
                <span className="chip" style={{ background: "rgb(255 255 255 / .1)", color: "inherit" }}>
                  <Users size={14} aria-hidden /> {watchN} of 14 counties at Watch+
                </span>
              </div>
              {alerts.length > 0 ? (
                <ul className="grid gap-1" aria-label="Counties at Warning or above">
                  {alerts.map((c) => (
                    <li key={c.county}>
                      <button
                        onClick={() => navigate(`/county/${encodeURIComponent(c.county)}`)}
                        className="flex w-full items-center justify-between gap-3 rounded-xl px-2 py-2 text-left text-sm hover:bg-white/10"
                        style={{ minHeight: 44 }}
                      >
                        <span className="min-w-0">
                          <span className="font-semibold">{c.county}</span>{" "}
                          <span className="opacity-75">{c.headline.split(":")[0]}</span>
                        </span>
                        <LevelBadge level={c.overall_level} size="sm" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm opacity-75">No county is at Warning or above.</p>
              )}
            </div>
          </div>
        </div>

        {/* the pill */}
        <div className="flex items-center gap-1 p-1.5">
          <div ref={barRef} className="relative flex flex-1 items-center justify-around">
            {ind && (
              <span
                aria-hidden
                className="absolute top-0 bottom-0 rounded-full"
                style={{
                  left: 0, width: ind.w, transform: `translateX(${ind.x}px)`,
                  background: "var(--accent)", transition: "transform 240ms ease-out, width 240ms ease-out",
                }}
              />
            )}
            {nav.map((n) => {
              const active = isActive(n.to, pathname);
              const Icon = n.icon;
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  className="relative z-10 flex flex-col items-center justify-center gap-0.5 rounded-full px-2.5 sm:flex-row sm:gap-1.5 sm:px-3.5"
                  style={{
                    minHeight: 44, minWidth: 44, textDecoration: "none",
                    color: active ? "var(--accent-ink)" : "inherit", opacity: active ? 1 : 0.82,
                    transition: "color 200ms",
                  }}
                >
                  <Icon size={18} aria-hidden />
                  <span className="text-[0.66rem] font-semibold sm:text-sm">{n.label}</span>
                </NavLink>
              );
            })}
          </div>
          <span aria-hidden className="mx-0.5 h-7 w-px" style={{ background: "rgb(255 255 255 / .18)" }} />
          <button
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls="island-panel"
            aria-label={open ? "Hide alerts" : `Show alerts (${alerts.length} at Warning or above)`}
            className="relative flex items-center justify-center rounded-full"
            style={{ minHeight: 44, minWidth: 44 }}
          >
            {agentBusy ? <LoaderCircle size={18} className="animate-spin" /> : open ? <ChevronDown size={18} /> : <BellRing size={18} />}
            {!open && alerts.length > 0 && (
              <span
                className="num absolute top-1 right-1 grid h-4 min-w-4 place-items-center rounded-full px-1 text-[10px] font-bold"
                style={{ background: "var(--lvl-warning)", color: "#fff" }}
              >
                {alerts.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setMode(mode === "manager" ? "public" : "manager")}
            className="hidden rounded-full px-3 text-xs font-bold sm:block"
            style={{ minHeight: 44, background: "rgb(255 255 255 / .1)" }}
            aria-label={`Switch to ${mode === "manager" ? "public" : "manager"} view`}
          >
            {mode === "manager" ? "Manager" : "Public"}
          </button>
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center justify-center rounded-full lg:hidden"
            style={{ minHeight: 44, minWidth: 44 }}
            aria-label="Open search and more"
          >
            <Command size={18} />
          </button>
        </div>
      </nav>
    </div>
  );
}
