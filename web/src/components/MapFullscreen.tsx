import { ChevronDown, ChevronUp, Info, Maximize2, Minimize2, X } from "lucide-react";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { KeyItem, LayerKey } from "../lib/mapLegends";
import { COMMON_NOTES } from "../lib/mapLegends";
import { useBreakpoint } from "../lib/useMedia";
import { levelColor } from "./ui";

/** Space covered by floating panels, so the map fits Kenya into the part you can actually see. */
export type MapInsets = { top: number; right: number; bottom: number; left: number };
const MapInsetsContext = createContext<MapInsets | null>(null);
export const useMapInsets = () => useContext(MapInsetsContext);

const PANEL: React.CSSProperties = {
  background: "color-mix(in oklab, var(--surface) 94%, transparent)",
  border: "1px solid var(--surface-3)",
  boxShadow: "var(--shadow)",
  backdropFilter: "blur(8px)",
};

/** Small floating button placed over an inline map to open it full screen. */
export function EnlargeButton({ onClick, label = "Full screen" }: { onClick: () => void; label?: string }) {
  return (
    <button
      onClick={onClick}
      aria-label={`Open the map in full screen`}
      title="Full screen map with key and details"
      className="absolute top-2.5 left-2.5 z-10 flex items-center gap-1.5 rounded-xl px-3 text-sm font-semibold"
      style={{ ...PANEL, minHeight: 40 }}
    >
      <Maximize2 size={16} aria-hidden /> <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

const TRACK_VAR: Record<string, string> = { "track-ts": "var(--accent)", "track-cy": "var(--lvl-warning)", "track-in": "var(--lvl-emergency)" };

function Swatch({ level, line = false }: { level: string; line?: boolean }) {
  const bg = TRACK_VAR[level] ?? levelColor(level === "none" ? null : level);
  return line ? (
    <span aria-hidden className="inline-block h-1.5 w-7 shrink-0 rounded-full" style={{ background: bg }} />
  ) : (
    <span aria-hidden className="inline-block h-4 w-4 shrink-0 rounded" style={{ background: bg, border: "1px solid rgb(0 0 0 / .12)" }} />
  );
}

/** Key items as a list of swatch + label + meaning. */
export function KeyList({ items, line = false }: { items: KeyItem[]; line?: boolean }) {
  return (
    <ul className="grid gap-2">
      {items.map((it) => (
        <li key={it.level + it.label} className="flex items-start gap-2.5 text-sm">
          <span className="mt-0.5"><Swatch level={it.level} line={line} /></span>
          <span className="min-w-0">
            <b>{it.label}</b>
            {it.meaning && <span className="muted"> · {it.meaning}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Full map key for one layer: what it answers, colour classes (or ramp), method, source, general notes. */
export function MapKey({ k, extra, asOf }: { k: LayerKey; extra?: ReactNode; asOf?: string }) {
  return (
    <div className="grid gap-4">
      <div className="grid gap-1">
        <h3>{k.title}</h3>
        <p className="muted text-sm">{k.question}</p>
      </div>
      {k.gradient ? (
        <div className="grid gap-1.5">
          <div
            aria-hidden
            className="h-3 rounded-full"
            style={{ background: "linear-gradient(to right, var(--lvl-normal), var(--lvl-watch), var(--lvl-warning), var(--lvl-emergency))" }}
          />
          <div className="flex justify-between text-xs">
            <span><b>{k.items[0].label}</b> · {k.items[0].meaning}</span>
          </div>
          <div className="flex justify-end text-xs">
            <span className="text-right"><b>{k.items[k.items.length - 1].label}</b> · {k.items[k.items.length - 1].meaning}</span>
          </div>
        </div>
      ) : (
        <KeyList items={k.items} />
      )}
      {extra}
      <div className="grid gap-1.5">
        <p className="subtle font-semibold">How it is calculated</p>
        <ul className="ml-4 grid list-disc gap-1 text-sm">
          {k.method.map((m) => <li key={m}>{m}</li>)}
        </ul>
        <p className="subtle">Source: {k.source}{asOf ? ` · ${asOf}` : ""}</p>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer font-semibold" style={{ minHeight: 32 }}>Reading this map</summary>
        <ul className="mt-2 ml-4 grid list-disc gap-1 muted">
          {COMMON_NOTES.map((n) => <li key={n}>{n}</li>)}
        </ul>
      </details>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  /** layer switcher / filters shown under the title */
  toolbar?: ReactNode;
  /** map key + information */
  panel: ReactNode;
  /** details of the tapped county / track */
  selection?: ReactNode;
  onClearSelection?: () => void;
  /** the map itself (rendered fresh inside the overlay) */
  children: ReactNode;
}

/**
 * Full-screen map mode. Uses the browser Fullscreen API where available (Esc or the button leaves it)
 * and otherwise covers the window. Desktop: title + toolbar and the key on the left, details card on
 * the right. Phones: title bar on top, key in a collapsible drawer at the bottom.
 */
export function MapFullscreen({ open, onClose, title, subtitle, toolbar, panel, selection, onClearSelection, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasNative = useRef(false);
  const { lg } = useBreakpoint();
  const [drawer, setDrawer] = useState(false);
  const closeCb = useRef(onClose);
  closeCb.current = onClose;

  useEffect(() => {
    if (!open) return;
    const el = ref.current;
    closeRef.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // real full screen when the browser allows it (needs the click that opened us)
    el?.requestFullscreen?.().then(() => (wasNative.current = true)).catch(() => undefined);
    const onChange = () => {
      if (!document.fullscreenElement && wasNative.current) {
        wasNative.current = false;
        closeCb.current(); // user pressed Esc / browser exit
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.fullscreenElement) closeCb.current();
    };
    document.addEventListener("fullscreenchange", onChange);
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      document.removeEventListener("fullscreenchange", onChange);
      window.removeEventListener("keydown", onKey);
      if (document.fullscreenElement) {
        wasNative.current = false;
        document.exitFullscreen?.().catch(() => undefined);
      }
    };
  }, [open]);

  useEffect(() => {
    if (selection && !lg) setDrawer(false); // make room for the details card on phones
  }, [selection, lg]);

  if (!open) return null;

  const header = (
    <div className="grid gap-2 rounded-2xl p-3" style={PANEL}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg">{title}</h2>
          {subtitle && <p className="subtle">{subtitle}</p>}
        </div>
        <button ref={closeRef} onClick={onClose} className="btn shrink-0" style={{ minHeight: 40, padding: "0 12px" }} aria-label="Exit full screen">
          <Minimize2 size={16} aria-hidden /> <span className="hidden sm:inline">Exit</span>
        </button>
      </div>
      {toolbar}
    </div>
  );

  const selectionCard = selection && (
    <div className="rise relative rounded-2xl p-4" style={PANEL}>
      {onClearSelection && (
        <button onClick={onClearSelection} aria-label="Close details" className="absolute top-2 right-2 grid h-9 w-9 place-items-center rounded-full hover:bg-[var(--surface-3)]">
          <X size={16} />
        </button>
      )}
      {selection}
    </div>
  );

  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label={`${title}, full screen map`} className={`fixed inset-0 z-[70] ${lg ? "" : "map-fs-mobile"}`} style={{ background: "var(--surface)" }}>
      <MapInsetsContext.Provider value={lg ? { top: 24, right: 72, bottom: 40, left: 404 } : { top: 150, right: 56, bottom: 72, left: 16 }}>
        <div className="absolute inset-0">{children}</div>
      </MapInsetsContext.Provider>

      {lg ? (
        <>
          <div className="pointer-events-none absolute top-3 bottom-3 left-3 z-10 flex w-[380px] flex-col gap-3">
            <div className="pointer-events-auto">{header}</div>
            <div className="pointer-events-auto min-h-0 overflow-y-auto rounded-2xl p-4" style={PANEL} aria-label="Map key and information">
              {panel}
            </div>
          </div>
          {selectionCard && <div className="absolute right-14 bottom-10 z-10 w-[360px] max-h-[70dvh] overflow-y-auto">{selectionCard}</div>}
        </>
      ) : (
        <>
          <div className="absolute top-2 left-2 z-10" style={{ right: 52, paddingTop: "env(safe-area-inset-top)" }}>{header}</div>
          <div className="absolute inset-x-2 z-10 grid gap-2" style={{ bottom: "calc(8px + env(safe-area-inset-bottom))" }}>
            {selectionCard && <div className="max-h-[42dvh] overflow-y-auto">{selectionCard}</div>}
            <div className="overflow-hidden rounded-2xl" style={PANEL}>
              <button
                onClick={() => setDrawer((d) => !d)}
                aria-expanded={drawer}
                className="flex w-full items-center justify-between gap-2 px-4 font-semibold"
                style={{ minHeight: 48 }}
              >
                <span className="flex items-center gap-2"><Info size={16} aria-hidden /> Map key & information</span>
                {drawer ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
              </button>
              {drawer && <div className="max-h-[48dvh] overflow-y-auto px-4 pb-4">{panel}</div>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
