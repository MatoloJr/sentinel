import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Mode = "manager" | "public";

interface AppState {
  mode: Mode;
  setMode: (m: Mode) => void;
  /** universal search (top island) open / focused */
  searchOpen: boolean;
  setSearchOpen: (o: boolean) => void;
  notificationsOpen: boolean;
  setNotificationsOpen: (o: boolean) => void;
  agentBusy: boolean;
  setAgentBusy: (b: boolean) => void;
  hovered: string | null;
  setHovered: (c: string | null) => void;
}

const Ctx = createContext<AppState | null>(null);

/** localStorage that never throws (private mode, blocked storage, previews). */
export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem(key);
      return v == null ? fallback : (JSON.parse(v) as T);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore */
    }
  },
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>(() => store.get<Mode>("cs.mode", "manager"));
  const [searchOpen, setSearchOpenState] = useState(false);
  const [notificationsOpen, setNotificationsOpenState] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const setMode = useCallback((m: Mode) => {
    setModeState(m);
    store.set("cs.mode", m);
  }, []);
  // only one top-level popover at a time
  const setSearchOpen = useCallback((o: boolean) => {
    setSearchOpenState(o);
    if (o) setNotificationsOpenState(false);
  }, []);
  const setNotificationsOpen = useCallback((o: boolean) => {
    setNotificationsOpenState(o);
    if (o) setSearchOpenState(false);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      const typing = t instanceof Element && !!t.closest("input, textarea, select, [contenteditable]");
      if ((e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === "Escape") {
        setSearchOpenState(false);
        setNotificationsOpenState(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSearchOpen]);

  const value = useMemo(
    () => ({ mode, setMode, searchOpen, setSearchOpen, notificationsOpen, setNotificationsOpen, agentBusy, setAgentBusy, hovered, setHovered }),
    [mode, setMode, searchOpen, setSearchOpen, notificationsOpen, setNotificationsOpen, agentBusy, hovered],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}

/** Per-browser checklist of playbook actions already started for a county. */
export function useChecklist(county: string) {
  const key = `cs.check.${county}`;
  const [done, setDone] = useState<Record<string, string>>(() => store.get(key, {}));
  useEffect(() => setDone(store.get(key, {})), [key]);
  const toggle = (id: string) =>
    setDone((d) => {
      const next = { ...d };
      if (next[id]) delete next[id];
      else next[id] = new Date().toISOString();
      store.set(key, next);
      return next;
    });
  return { done, toggle };
}
