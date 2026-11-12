import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InsightPanel } from "../components/InsightPanel";
import { Island } from "../components/Island";
import { TopBar } from "../components/TopBar";
import type { InsightCard } from "../lib/api";
import { buildIndex, search } from "../lib/search";
import { AppProvider } from "../lib/state";

const card: InsightCard = {
  county: "Turkana", zone: "Arid north", overall_level: "Warning",
  headline: "Drought Warning: 35% of normal rain over the 3 months to 2026-10",
  hazard_levels: { drought: "Warning", flood: "Watch", cyclone: "Normal" },
  drivers: [{ hazard: "drought", level: "Warning", text: "35% of normal rain", value: 35, unit: "% of normal" }],
  trend: null, significant_extreme_trends: [],
  next: { forecast: null, outlook: null }, rising: true,
  exposure: { population_2020: 1226408, share_of_region_pct: 6.5, people_at_watch_or_above: 1226408 },
  priority_score: 11.1, priority_rank: 2, priority_explained: "",
  actions: [
    { id: "DR-A1", hazard: "drought", level: "Warning", action: "Repair and rehabilitate water facilities", timeframe: "This week", source: "KRCS EAP" },
    { id: "FL-W1", hazard: "flood", level: "Watch", action: "Disseminate targeted early warnings", timeframe: "Next 2-4 weeks", source: "KRCS EAP" },
  ],
  rainy_seasons: null,
  public: { summary: "Rain is well below normal.", sms: "Turkana Drought WARNING: Save water.", level: "Warning" },
};
const runs = [{ run_id: "20261112-1-abc", question: "Advisory for Wajir", status: "draft", started_utc: "2026-11-12T10:00:00Z", model: "gemini", validation_passed: true, n_tool_calls: 3 }];

function Where() {
  const l = useLocation();
  return <div data-testid="where">{l.pathname + l.search}</div>;
}

function wrap(ui: React.ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AppProvider>
          {ui}
          <Routes><Route path="*" element={<Where />} /></Routes>
        </AppProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url.includes("/api/insights")
      ? { generated_for: "2026-11-12", note: "", region: { counties_at_watch_or_above: 3, counties_at_warning_or_above: 1, people_at_watch_or_above: 1, people_at_warning_or_above: 1, rising: ["Turkana"], top_priorities: ["Turkana"] }, counties: [card] }
      : url.includes("/api/agent/runs")
        ? runs
        : { ok: true, daily_range: ["1991-01-01", "2026-11-05"], data_lag_days: 7, gemini_configured: true, built_utc: "x" };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => vi.unstubAllGlobals());

describe("Bottom island", () => {
  it("shows every destination plus view and theme switches", () => {
    wrap(<Island />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const label of ["Overview", "County", "Outlook", "Cyclones", "Advisory", "Evidence", "About"]) {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("button", { name: /Switch to public view/ })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /theme/ })).toBeInTheDocument();
  });

  it("switches to the public view (no Advisory)", () => {
    wrap(<Island />);
    fireEvent.click(screen.getByRole("button", { name: /Switch to public view/ }));
    expect(screen.getByRole("link", { name: "My area" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Advisory" })).toBeNull();
  });

  it("toggles the theme", () => {
    wrap(<Island />);
    const before = document.documentElement.dataset.theme;
    fireEvent.click(screen.getByRole("button", { name: /theme/ }));
    expect(document.documentElement.dataset.theme).not.toBe(before);
  });
});

describe("Top island search", () => {
  it("opens with Ctrl+K, finds a county by its HQ town and navigates", async () => {
    wrap(<TopBar />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = screen.getByRole("combobox", { name: "Universal search" });
    await waitFor(() => expect(input).toHaveAttribute("aria-expanded", "true"));
    fireEvent.change(input, { target: { value: "lodwar" } });
    expect(await screen.findByRole("option", { name: /Turkana/ })).toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByTestId("where")).toHaveTextContent("/county/Turkana");
  });

  it("offers to ask Gemini for free-text queries in manager view", async () => {
    wrap(<TopBar />);
    const input = screen.getByRole("combobox", { name: "Universal search" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "flood risk next week" } });
    fireEvent.click(await screen.findByRole("option", { name: /Ask Gemini/ }));
    expect(screen.getByTestId("where").textContent).toContain("/advisory?q=flood");
  });

  it("search index ranks label matches and finds playbook actions", () => {
    const idx = buildIndex({ mode: "manager", cards: [card], runs: runs as any, theme: "light" });
    expect(search(idx, "DR-A1")[0].id).toBe("action:DR-A1");
    expect(search(idx, "tana")[0].label).toBe("Tana River");
    expect(search(buildIndex({ mode: "public", cards: [card], theme: "light" }), "draft").every((e) => e.group !== "Advisories")).toBe(true);
  });
});

describe("Notifications (top right)", () => {
  it("counts unread alerts and drafts, and marks them read", async () => {
    wrap(<TopBar />);
    const bell = await screen.findByRole("button", { name: /Notifications \(2 unread\)/ });
    fireEvent.click(bell);
    const dialog = screen.getByRole("dialog", { name: "Notifications" });
    expect(within(dialog).getByText("Turkana")).toBeInTheDocument();
    expect(within(dialog).getByText("Advisory awaiting approval")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /Mark all read/ }));
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("cs.seen")!)).toHaveLength(2);
  });
});

describe("InsightPanel", () => {
  it("ticks off actions and remembers them on this device", () => {
    wrap(<InsightPanel card={card} />);
    expect(screen.getByText("0/2 started on this device")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Repair and rehabilitate/ }));
    expect(screen.getByText("1/2 started on this device")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("cs.check.Turkana")!)).toHaveProperty("DR-A1");
  });
});
