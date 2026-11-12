import { useEffect, useState } from "react";

/** Live CSS media query match. */
export function useMedia(query: string) {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false);
  const [match, setMatch] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia?.(query);
    if (!mq) return;
    const on = () => setMatch(mq.matches);
    on();
    mq.addEventListener?.("change", on);
    return () => mq.removeEventListener?.("change", on);
  }, [query]);
  return match;
}

/** Tailwind-aligned breakpoints: sm 640, md 768, lg 1024. */
export function useBreakpoint() {
  const sm = useMedia("(min-width: 640px)");
  const md = useMedia("(min-width: 768px)");
  const lg = useMedia("(min-width: 1024px)");
  return { mobile: !sm, sm, md, lg };
}

/** Scroll direction for hide-on-scroll chrome. Returns true while the user scrolls down past `offset`. */
export function useScrollingDown(offset = 120) {
  const [down, setDown] = useState(false);
  useEffect(() => {
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      if (Math.abs(y - last) < 8) return;
      const atBottom = window.innerHeight + y >= document.documentElement.scrollHeight - 4;
      setDown(y > last && y > offset && !atBottom);
      last = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [offset]);
  return down;
}
