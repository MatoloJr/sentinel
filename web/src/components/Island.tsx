import {
  CloudRain, Compass, Ellipsis, FlaskConical, GripVertical, Info, LayoutGrid, Map as MapIcon, MessageSquareText, Tornado,
  UserRound, Users,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { store, useApp } from "../lib/state";

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
const ISLAND_BG = "color-mix(in oklab, var(--ink) 94%, var(--accent))";
const NAV_PAD = 12; // p-1.5 on both sides
const GAP = 4; // gap-1 between groups

const itemClass =
  "relative z-10 flex shrink-0 flex-row items-center justify-center gap-1.5 rounded-full px-3 sm:flex-col sm:gap-0.5 sm:px-2.5 xl:flex-row xl:gap-1.5 xl:px-3.5";
const labelClass = (active: boolean) =>
  `${active ? "text-xs" : "sr-only sm:not-sr-only"} font-semibold leading-none whitespace-nowrap sm:text-[0.66rem] xl:text-sm`;
const itemStyle: CSSProperties = { minHeight: 48, minWidth: 46, textDecoration: "none" };

function ItemBody({ item, active }: { item: Item; active: boolean }) {
  const Icon = item.icon;
  return (
    <>
      <Icon size={19} aria-hidden />
      <span className={labelClass(active)}>{item.label}</span>
    </>
  );
}

/**
 * Pick which destinations fit in the bar. The active one always stays; the rest are added in
 * order until the next would not fit. Widths come from an invisible measuring row that uses the
 * same classes, so the result follows every breakpoint and font size.
 */
function useFit(nav: Item[], pathname: string) {
  const measureRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef<HTMLButtonElement>(null);
  const [visible, setVisible] = useState<string[]>(() => nav.map((n) => n.to));

  const compute = useCallback(() => {
    const m = measureRef.current;
    if (!m) return;
    const inactive = Array.from(m.querySelectorAll<HTMLElement>("[data-measure='inactive']")).map((e) => e.offsetWidth);
    const active = Array.from(m.querySelectorAll<HTMLElement>("[data-measure='active']")).map((e) => e.offsetWidth);
    if (!inactive.length || inactive.every((w) => w === 0)) return setVisible(nav.map((n) => n.to)); // not laid out (tests)
    const sidePad = window.innerWidth >= 640 ? 24 : 16;
    const modeW = modeRef.current?.offsetWidth ?? 46;
    const avail = window.innerWidth - sidePad - NAV_PAD - GAP * 2 - 1 - modeW;
    const activeIdx = nav.findIndex((n) => isActive(n.to, pathname));
    let used = activeIdx >= 0 ? active[activeIdx] : 0;
    const keep = new Set<number>(activeIdx >= 0 ? [activeIdx] : []);
    for (let i = 0; i < nav.length; i++) {
      if (i === activeIdx) continue;
      if (used + inactive[i] > avail) break;
      used += inactive[i];
      keep.add(i);
    }
    setVisible(nav.filter((_, i) => keep.has(i)).map((n) => n.to));
  }, [nav, pathname]);

  useLayoutEffect(() => {
    compute();
    window.addEventListener("resize", compute);
    document.fonts?.ready.then(compute).catch(() => undefined);
    return () => window.removeEventListener("resize", compute);
  }, [compute]);

  return { measureRef, modeRef, visible };
}

/**
 * Bottom dynamic island: every destination plus the manager/public switch. Destinations that do
 * not fit on narrow screens move into a draggable floating button (bottom-right by default).
 */
export function Island() {
  const { mode, setMode } = useApp();
  const nav = mode === "manager" ? MANAGER_NAV : PUBLIC_NAV;
  const { pathname } = useLocation();
  const trackRef = useRef<HTMLDivElement>(null);
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);
  const { measureRef, modeRef, visible } = useFit(nav, pathname);
  const shown = nav.filter((n) => visible.includes(n.to));
  const overflow = nav.filter((n) => !visible.includes(n.to));

  useLayoutEffect(() => {
    const el = trackRef.current?.querySelector<HTMLElement>("[data-active='true']");
    setInd(el ? { x: el.offsetLeft, w: el.offsetWidth } : null);
  }, [pathname, mode, visible.join("|")]);

  return (
    <>
      {/* invisible measuring row: same markup, every item inactive + active */}
      <div ref={measureRef} aria-hidden className="pointer-events-none fixed -left-[9999px] top-0 flex" style={{ visibility: "hidden" }}>
        {nav.map((n) => (
          <span key={`i${n.to}`} data-measure="inactive" className={itemClass} style={itemStyle}><ItemBody item={n} active={false} /></span>
        ))}
        {nav.map((n) => (
          <span key={`a${n.to}`} data-measure="active" className={itemClass} style={itemStyle}><ItemBody item={n} active /></span>
        ))}
      </div>

      <div
        className="no-print pointer-events-none fixed inset-x-0 z-40 flex justify-center px-2 sm:px-3"
        style={{ bottom: "calc(10px + env(safe-area-inset-bottom))" }}
      >
        <nav
          aria-label="Main"
          className="pointer-events-auto flex max-w-full items-center gap-1 rounded-full p-1.5"
          style={{ background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)" }}
        >
          <div ref={trackRef} className="relative flex items-center">
            {ind && (
              <span
                aria-hidden
                className="absolute top-0 bottom-0 rounded-full"
                style={{ left: 0, width: ind.w, transform: `translateX(${ind.x}px)`, background: "var(--accent)", transition: "transform 260ms cubic-bezier(.2,.8,.2,1), width 260ms cubic-bezier(.2,.8,.2,1)" }}
              />
            )}
            {shown.map((n) => {
              const active = isActive(n.to, pathname);
              return (
                <NavLink
                  key={n.to}
                  to={n.to}
                  viewTransition
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  aria-label={n.label}
                  className={itemClass}
                  style={{ ...itemStyle, color: active ? "var(--accent-ink)" : "inherit", opacity: active ? 1 : 0.8, transition: "color 200ms, opacity 200ms" }}
                >
                  <ItemBody item={n} active={active} />
                </NavLink>
              );
            })}
          </div>
          <span aria-hidden className="h-8 w-px shrink-0" style={{ background: "rgb(255 255 255 / .18)" }} />
          <button
            ref={modeRef}
            onClick={() => setMode(mode === "manager" ? "public" : "manager")}
            aria-label={`Switch to ${mode === "manager" ? "public" : "manager"} view`}
            title={mode === "manager" ? "Manager view" : "Public view"}
            className="flex shrink-0 flex-col items-center justify-center gap-0.5 rounded-full px-2 hover:bg-white/10 xl:flex-row xl:gap-1.5 xl:px-3"
            style={{ minHeight: 48, minWidth: 46 }}
          >
            {mode === "manager" ? <UserRound size={19} aria-hidden /> : <Users size={19} aria-hidden />}
            <span className="sr-only font-semibold leading-none sm:not-sr-only sm:text-[0.66rem] xl:text-sm">{mode === "manager" ? "Manager" : "Public"}</span>
          </button>
        </nav>
      </div>

      {overflow.length > 0 && <OverflowFab items={overflow} />}
    </>
  );
}

// ------------------------------------------------------------------ draggable overflow button
type FabPos = { side: "left" | "right"; y: number | null };
const FAB = 52;
const EDGE = 12;

function clampY(y: number) {
  const min = 76; // below the top island
  const max = window.innerHeight - FAB - 84; // above the bottom island
  return Math.max(min, Math.min(max, y));
}

/**
 * Floating "more" button for destinations that did not fit in the bottom island.
 * Drag it anywhere (mouse, touch or pen); it snaps to the nearest side and remembers where it was.
 * Keyboard: Enter/Space opens it, arrow keys move it.
 */
export function OverflowFab({ items }: { items: Item[] }) {
  const { pathname } = useLocation();
  const [pos, setPos] = useState<FabPos>(() => store.get<FabPos>("cs.fab", { side: "right", y: null }));
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const [open, setOpen] = useState(false);
  const start = useRef<{ px: number; py: number; ox: number; oy: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [, force] = useState(0);

  const y = drag ? drag.y : clampY(pos.y ?? window.innerHeight - FAB - 96);
  const save = (p: FabPos) => {
    setPos(p);
    store.set("cs.fab", p);
  };

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    const onResize = () => force((n) => n + 1);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent | TouchEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("touchstart", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("touchstart", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    const r = btnRef.current!.getBoundingClientRect();
    start.current = { px: e.clientX, py: e.clientY, ox: e.clientX - r.left, oy: e.clientY - r.top, moved: false };
    btnRef.current?.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const s = start.current;
    if (!s) return;
    if (!s.moved && Math.hypot(e.clientX - s.px, e.clientY - s.py) < 6) return;
    s.moved = true;
    setOpen(false);
    setDrag({
      x: Math.max(4, Math.min(window.innerWidth - FAB - 4, e.clientX - s.ox)),
      y: Math.max(4, Math.min(window.innerHeight - FAB - 4, e.clientY - s.oy)),
    });
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const s = start.current;
    start.current = null;
    if (!s?.moved || !drag) return;
    suppressClick.current = true;
    const centre = drag.x + FAB / 2;
    save({ side: centre < window.innerWidth / 2 ? "left" : "right", y: clampY(drag.y) });
    setDrag(null);
    btnRef.current?.releasePointerCapture(e.pointerId);
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 64 : 24;
    if (e.key === "ArrowUp") { e.preventDefault(); save({ ...pos, y: clampY(y - step) }); }
    if (e.key === "ArrowDown") { e.preventDefault(); save({ ...pos, y: clampY(y + step) }); }
    if (e.key === "ArrowLeft") { e.preventDefault(); save({ ...pos, side: "left" }); }
    if (e.key === "ArrowRight") { e.preventDefault(); save({ ...pos, side: "right" }); }
  };

  const horizontal: CSSProperties = drag ? { left: drag.x } : pos.side === "left" ? { left: EDGE } : { right: EDGE };
  const menuBelow = y < window.innerHeight / 2;
  const activeInside = items.some((n) => isActive(n.to, pathname));

  return (
    <div
      ref={boxRef}
      className="no-print fixed z-50"
      style={{ top: y, ...horizontal, transition: drag ? "none" : "top 220ms ease-out, left 220ms ease-out, right 220ms ease-out" }}
    >
      <button
        ref={btnRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => { start.current = null; setDrag(null); }}
        onClick={() => {
          if (suppressClick.current) { suppressClick.current = false; return; }
          setOpen((o) => !o);
        }}
        onKeyDown={onKeyDown}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`More pages (${items.length}). Drag or use arrow keys to move.`}
        title="More pages: drag to move"
        className="relative grid place-items-center rounded-full"
        style={{
          width: FAB, height: FAB, touchAction: "none", cursor: drag ? "grabbing" : "grab",
          background: activeInside ? "var(--accent)" : ISLAND_BG, color: activeInside ? "var(--accent-ink)" : "var(--surface)",
          boxShadow: drag ? "0 18px 40px -12px rgb(0 0 0 / .55)" : "var(--shadow)",
          transform: drag ? "scale(1.08)" : "none", transition: "transform 150ms, box-shadow 150ms",
        }}
      >
        <Ellipsis size={22} aria-hidden />
        <GripVertical size={12} aria-hidden className="absolute bottom-1.5 opacity-50" />
        <span className="num absolute -top-1 -right-1 grid h-5 min-w-5 place-items-center rounded-full px-1 text-[11px] font-bold" style={{ background: "var(--accent)", color: "var(--accent-ink)", boxShadow: "0 0 0 2px var(--surface)" }}>
          {items.length}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          aria-label="More pages"
          className="rise absolute w-56 overflow-hidden rounded-3xl p-1.5"
          style={{
            [menuBelow ? "top" : "bottom"]: FAB + 8,
            [pos.side === "left" && !drag ? "left" : "right"]: 0,
            background: ISLAND_BG, color: "var(--surface)", boxShadow: "var(--shadow)",
          }}
        >
          {items.map((n) => {
            const active = isActive(n.to, pathname);
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                viewTransition
                role="menuitem"
                aria-current={active ? "page" : undefined}
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 rounded-2xl px-3 font-semibold hover:bg-white/10"
                style={{ minHeight: 46, textDecoration: "none", color: active ? "var(--accent-ink)" : "inherit", background: active ? "var(--accent)" : undefined }}
              >
                <Icon size={18} aria-hidden /> {n.label}
              </NavLink>
            );
          })}
        </div>
      )}
    </div>
  );
}
