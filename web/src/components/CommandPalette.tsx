import { Command, CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COUNTIES } from "../lib/api";
import { store, useApp } from "../lib/state";

type Entry = { id: string; label: string; hint: string; run: () => void };

export function toggleTheme() {
  const root = document.documentElement;
  const cur = root.dataset.theme ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  store.set("cs.theme", next);
}

/** Cmd/Ctrl+K or "/" anywhere: jump to a county, a page, or switch view/theme. */
export function CommandPalette() {
  const { paletteOpen, setPaletteOpen, mode, setMode } = useApp();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const go = (to: string) => () => navigate(to);

  const entries: Entry[] = useMemo(
    () => [
      ...COUNTIES.map((c) => ({ id: `c-${c}`, label: c, hint: "County", run: go(`/county/${encodeURIComponent(c)}`) })),
      { id: "p-ov", label: "Overview map", hint: "Page", run: go("/") },
      { id: "p-ol", label: "Seasonal outlook & 7-day watch", hint: "Page", run: go("/outlook") },
      { id: "p-cy", label: "Cyclone exposure", hint: "Page", run: go("/cyclones") },
      { id: "p-ad", label: "Ask for an advisory", hint: "Page", run: go("/advisory") },
      { id: "p-ev", label: "Evidence, metrics & model card", hint: "Page", run: go("/evidence") },
      { id: "p-ab", label: "How is this different from the TV forecast?", hint: "Page", run: go("/about") },
      { id: "a-mode", label: `Switch to ${mode === "manager" ? "public" : "manager"} view`, hint: "Action", run: () => setMode(mode === "manager" ? "public" : "manager") },
      { id: "a-theme", label: "Toggle light / dark theme", hint: "Action", run: toggleTheme },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode],
  );
  const list = entries.filter((e) => e.label.toLowerCase().includes(q.trim().toLowerCase()));

  useEffect(() => {
    if (paletteOpen) {
      setQ("");
      setSel(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [paletteOpen]);
  useEffect(() => setSel(0), [q]);

  if (!paletteOpen) return null;
  const choose = (e?: Entry) => {
    if (!e) return;
    setPaletteOpen(false);
    e.run();
  };
  return (
    <div
      className="no-print fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]"
      style={{ background: "rgb(15 20 18 / .45)" }}
      onClick={() => setPaletteOpen(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search and commands"
        className="rise w-full max-w-lg overflow-hidden rounded-3xl"
        style={{ background: "var(--surface)", boxShadow: "var(--shadow)", border: "1px solid var(--surface-3)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4" style={{ borderBottom: "1px solid var(--surface-3)" }}>
          <Search size={18} className="muted" aria-hidden />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, list.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              if (e.key === "Enter") choose(list[sel]);
            }}
            placeholder="Search counties, pages, actions…"
            aria-label="Search"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-list"
            aria-activedescendant={list[sel]?.id}
            className="h-14 flex-1 bg-transparent outline-none"
            style={{ boxShadow: "none" }}
          />
          <kbd className="chip">Esc</kbd>
        </div>
        <ul id="palette-list" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {list.length === 0 && <li className="muted p-4 text-center">No match. Only the 14 covered counties are listed.</li>}
          {list.map((e, i) => (
            <li
              key={e.id}
              id={e.id}
              role="option"
              aria-selected={i === sel}
              onMouseEnter={() => setSel(i)}
              onClick={() => choose(e)}
              className="flex cursor-pointer items-center justify-between rounded-xl px-3"
              style={{ minHeight: 44, background: i === sel ? "var(--accent-soft)" : undefined }}
            >
              <span className="font-medium">{e.label}</span>
              <span className="subtle flex items-center gap-2">
                {e.hint} {i === sel && <CornerDownLeft size={14} aria-hidden />}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Floating action button (bottom-right, above the island) for everything not in the bar. */
export function Fab() {
  const { setPaletteOpen } = useApp();
  return (
    <button
      onClick={() => setPaletteOpen(true)}
      className="no-print fixed z-40 hidden items-center gap-2 rounded-full px-4 font-semibold lg:flex"
      style={{
        right: 20, bottom: "calc(20px + env(safe-area-inset-bottom))", minHeight: 48,
        background: "var(--accent)", color: "var(--accent-ink)", boxShadow: "var(--shadow)",
      }}
      aria-label="Search and more (Ctrl+K)"
    >
      <Command size={16} aria-hidden /> <span className="text-sm">More</span>
      <kbd className="text-xs opacity-80">Ctrl K</kbd>
    </button>
  );
}
