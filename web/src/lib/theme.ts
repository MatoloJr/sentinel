import { useEffect, useState } from "react";
import { store } from "./state";

export function initTheme() {
  const t = store.get<string | null>("cs.theme", null);
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
}

function current(): "light" | "dark" {
  const t = document.documentElement.dataset.theme;
  if (t === "light" || t === "dark") return t;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Effective theme, reacting to the OS setting and to the in-app toggle. */
export function useTheme() {
  const [theme, setTheme] = useState(current);
  useEffect(() => {
    const update = () => setTheme(current());
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    mq?.addEventListener?.("change", update);
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      mq?.removeEventListener?.("change", update);
      mo.disconnect();
    };
  }, []);
  return theme;
}

/** Resolve CSS custom properties to concrete colours (MapLibre / canvas can't read var()). */
export function cssVars(names: string[]): Record<string, string> {
  const cs = getComputedStyle(document.documentElement);
  return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(n).trim() || "#999"]));
}
