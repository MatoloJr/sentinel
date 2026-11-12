import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "../components/CommandPalette";
import { InsightPanel } from "../components/InsightPanel";
import { Island } from "../components/Island";
import type { InsightCard } from "../lib/api";
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

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AppProvider>{ui}</AppProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const body = url.includes("/api/insights")
      ? { generated_for: "2026-11-12", note: "", region: { counties_at_watch_or_above: 3, counties_at_warning_or_above: 1, people_at_watch_or_above: 1, people_at_warning_or_above: 1, rising: [], top_priorities: [] }, counties: [card] }
      : { ok: true, daily_range: ["1991-01-01", "2026-11-05"], data_lag_days: 7, gemini_configured: true };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});
afterEach(() => vi.unstubAllGlobals());

describe("Island", () => {
  it("renders manager navigation and expands to show Warning counties", async () => {
    wrap(<Island />);
    for (const label of ["Overview", "County", "Outlook", "Cyclones", "Advisory"]) {
      expect(screen.getByRole("link", { name: new RegExp(label) })).toBeInTheDocument();
    }
    const toggle = await screen.findByRole("button", { name: /Show alerts \(1/ });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(screen.getByText("Turkana")).toBeInTheDocument());
  });

  it("switches to the public view", async () => {
    wrap(<Island />);
    fireEvent.click(screen.getByRole("button", { name: /Switch to public view/ }));
    expect(screen.getByRole("link", { name: /My area/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Advisory/ })).toBeNull();
  });
});

describe("Command palette", () => {
  it("opens with Ctrl+K and filters counties", async () => {
    wrap(<CommandPalette />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = await screen.findByRole("combobox");
    fireEvent.change(input, { target: { value: "tana" } });
    expect(screen.getByRole("option", { name: /Tana River/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Kisumu/ })).toBeNull();
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
