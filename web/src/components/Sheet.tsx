import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/** Slide-up sheet (centred, never a sidebar). Esc / backdrop / swipe-down closes it. */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const startY = useRef<number | null>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center md:items-center md:p-6" style={{ background: "rgb(15 20 18 / .4)" }} onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : "Details"}
        className="rise w-full max-w-3xl overflow-y-auto rounded-t-[28px] outline-none md:rounded-[28px]"
        style={{ background: "var(--surface-2)", maxHeight: "min(90dvh, 900px)", boxShadow: "var(--shadow)", paddingBottom: "env(safe-area-inset-bottom)" }}
        onClick={(e) => e.stopPropagation()}
        onTouchStart={(e) => (startY.current = e.touches[0].clientY)}
        onTouchEnd={(e) => {
          if (startY.current != null && e.changedTouches[0].clientY - startY.current > 90 && (ref.current?.scrollTop ?? 0) <= 0) onClose();
          startY.current = null;
        }}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-5 pt-3 pb-2" style={{ background: "var(--surface-2)" }}>
          <span aria-hidden className="absolute top-1.5 left-1/2 h-1 w-10 -translate-x-1/2 rounded-full" style={{ background: "var(--surface-3)" }} />
          <h2 className="pt-2">{title}</h2>
          <button className="btn" style={{ minWidth: 44, padding: 0 }} onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="px-5 pb-6">{children}</div>
      </div>
    </div>
  );
}
