import {
  CloudRain, Compass, FlaskConical, Info, LayoutGrid, Map as MapIcon, MessageSquareText, Moon, Sun, Tornado, UserRound, Users,
} from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useApp } from "../lib/state";
import { toggleTheme, useTheme } from "../lib/theme";
import { useScrollingDown } from "../lib/useMedia";

type Item = { to: string; label: string; icon: typeof MapIcon };

export const MANAGER_NAV: Item[] = [
  { to: "/", label: "Overview", icon: MapIcon },
  { to: "/county", label: "County", icon: LayoutGrid },
  { to: "/outlook", label: "Outlook", icon: CloudRain },
  { to: "/cyclones", label: "Cyclones", icon: Tornado },
  { to: "/advisory", label: "Advisory", icon: MessageSquareText },
  { to: "/evidence", label: "Evidence", icon: FlaskConical },
  { to: "/about", label: "About", icon: Info },
];
export const PUBLIC_NAV: Item[] = [
  { to: "/", label: "My area", icon: Compass },
  { to: "/county", label: "County", icon: LayoutGrid },
  { to: "/outlook", label: "Outlook", icon: CloudRain },
  { to: "/cyclones", label: "Cyclones", icon: Tornado },
  { to: "/evidence", label: "Evidence", icon: FlaskConical },
  { to: "/about", label: "Why this", icon: Info },
];

const isActive = (to: string, path: string) => (to === "/" ? path === "/" : path.startsWith(to));

/**
 * Bottom dynamic island: every destination plus the view (manager/public) and theme switches.
 * Floats centred, hides while scrolling down, slides an indicator under the active item, and
 * scrolls horizontally (with edge fades) when a phone is too narrow to show everything.
 */
export function Island() {
  const { mode, setMode } = useApp();
  const theme = useTheme();
  const nav = mode === "manager" ? MANAGER_NAV : PUBLIC_NAV;
  const { pathname } = useLocation();
  const down = useScrollingDown();
  const scrollRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);
  const [fade, setFade] = useState({ l: false, r: false });

  useLayoutEffect(() => {
    const track = trackRef.current;
    const sc = scrollRef.current;
    if (!track || !sc) return;
    const measure = () => {
      const el = track.querySelector<HTMLElement>("[data-active='true']");
      setInd(el ? { x: el.offsetLeft, w: el.offsetWidth } : null);
      setFade({ l: sc.scrollLeft > 4, r: sc.scrollLeft + sc.clientWidth < sc.scrollWidth - 4 });
    };
    measure();
    track.querySelector<HTMLElement>("[data-active='true']")?.scrollIntoView?.({ inline: "center", block: "nearest", behavior: "smooth" });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(sc);
    sc.addEventListener("scroll", measure, { passive: true });
    return () => {
      ro?.disconnect();
      sc.removeEventListener("scroll", measure);
    };
  }, [pathname, mode]);

  const mask =
    fade.l || fade.r
      ? `linear-gradient(to right, ${fade.l ? "transparent" : "#000"} 0, #000 28px, #000 calc(100% - 28px), ${fade.r ? "transparent" : "#000"} 100%)`
      : undefined;

  return (
    <div
      className="no-print pointer-events-none fixed inset-x-0 z-40 flex justify-center px-2 sm:px-3"
      style={{
        bottom: "calc(10px + env(safe-area-inset-bottom))",
        transform: down ? "translateY(150%)" : "none",
        transition: "transform 240ms ease-out",
      }}
    >
      <nav
        aria-label="Main"
        className="pointer-events-auto flex max-w-full items-center gap-1 rounded-full p-1.5"
        style={{ background: "color-mix(in oklab, var(--ink) 94%, var(--accent))", color: "var(--surface)", boxShadow: "var(--shadow)" }}
      >
        <div ref={scrollRef} className="no-scrollbar min-w-0 overflow-x-auto" style={{ maskImage: mask, WebkitMaskImage: mask, scrollSnapType: "x proximity" }}>
          <div ref={trackRef} className="relative flex items-center">
            {ind && (
              <span
                aria-hidden
                className="absolute top-0 bottom-0 rounded-full"
                style={{ left: 0, width: ind.w, transform: `translateX(${ind.x}px)`, background: "var(--accent)", transition: "transform 260ms cubic-bezier(.2,.8,.2,1), width 260ms cubic-bezier(.2,.8,.2,1)" }}
              />
            )}
            {nav.map((n) => {
              const active = isActive(n.to, pathname);
              const Icon = n.icon;
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  viewTransition
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  aria-label={n.label}
                  className="relative z-10 flex shrink-0 flex-row items-center justify-center gap-1.5 rounded-full px-3 sm:flex-col sm:gap-0.5 sm:px-2.5 xl:flex-row xl:gap-1.5 xl:px-3.5"
                  style={{ minHeight: 48, minWidth: 46, textDecoration: "none", scrollSnapAlign: "center", color: active ? "var(--accent-ink)" : "inherit", opacity: active ? 1 : 0.8, transition: "color 200ms, opacity 200ms" }}
                >
                  <Icon size={19} aria-hidden />
                  <span className={`${active ? "text-xs" : "sr-only sm:not-sr-only"} font-semibold leading-none sm:text-[0.66rem] xl:text-sm`}>{n.label}</span>
                </NavLink>
              );
            })}
          </div>
        </div>
        <span aria-hidden className="mx-0.5 h-8 w-px shrink-0" style={{ background: "rgb(255 255 255 / .18)" }} />
        <button
          onClick={() => setMode(mode === "manager" ? "public" : "manager")}
          aria-label={`Switch to ${mode === "manager" ? "public" : "manager"} view`}
          title={mode === "manager" ? "Manager view" : "Public view"}
          className="flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-full px-2 hover:bg-white/10 xl:flex-row xl:gap-1.5 xl:px-3"
          style={{ minHeight: 48, minWidth: 46 }}
        >
          {mode === "manager" ? <UserRound size={19} aria-hidden /> : <Users size={19} aria-hidden />}
          <span className="sr-only font-semibold leading-none sm:not-sr-only sm:text-[0.66rem] xl:text-sm">{mode === "manager" ? "Manager" : "Public"}</span>
        </button>
        <button
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          className="grid shrink-0 place-items-center rounded-full hover:bg-white/10"
          style={{ minHeight: 48, minWidth: 46 }}
        >
          {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </nav>
    </div>
  );
}
