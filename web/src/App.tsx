import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { CommandPalette, Fab } from "./components/CommandPalette";
import { Island } from "./components/Island";
import { PageSkeleton } from "./components/ui";
import { Overview } from "./pages/Overview";

const County = lazy(() => import("./pages/County").then((m) => ({ default: m.County })));
const Outlook = lazy(() => import("./pages/Outlook").then((m) => ({ default: m.Outlook })));
const Cyclones = lazy(() => import("./pages/Cyclones").then((m) => ({ default: m.Cyclones })));
const Advisory = lazy(() => import("./pages/Advisory").then((m) => ({ default: m.Advisory })));
const Evidence = lazy(() => import("./pages/Evidence").then((m) => ({ default: m.Evidence })));
const About = lazy(() => import("./pages/About").then((m) => ({ default: m.About })));

function NotFound() {
  return (
    <div className="page grid gap-2">
      <h1>Page not found</h1>
      <p className="muted">Use the bar below or press Ctrl+K to search.</p>
    </div>
  );
}

export default function App() {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 btn">
        Skip to content
      </a>
      <main id="main">
        <Suspense fallback={<PageSkeleton />}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/county" element={<County />} />
            <Route path="/county/:name" element={<County />} />
            <Route path="/outlook" element={<Outlook />} />
            <Route path="/cyclones" element={<Cyclones />} />
            <Route path="/advisory" element={<Advisory />} />
            <Route path="/evidence" element={<Evidence />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <Island />
      <Fab />
      <CommandPalette />
    </>
  );
}
