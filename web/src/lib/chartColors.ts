import { useMemo } from "react";
import { cssVars, useTheme } from "./theme";

/** Concrete colours for SVG charts, recomputed when the theme flips. */
export function useChartColors() {
  const theme = useTheme();
  return useMemo(() => {
    const v = cssVars(["--accent", "--ink", "--ink-2", "--ink-3", "--surface", "--surface-2", "--surface-3",
      "--lvl-normal", "--lvl-watch", "--lvl-warning", "--lvl-emergency"]);
    return {
      accent: v["--accent"], ink: v["--ink"], ink2: v["--ink-2"], ink3: v["--ink-3"], surface: v["--surface"],
      surface2: v["--surface-2"], grid: v["--surface-3"], normal: v["--lvl-normal"], watch: v["--lvl-watch"],
      warning: v["--lvl-warning"], emergency: v["--lvl-emergency"], theme,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);
}

export const tooltipStyle = (c: ReturnType<typeof useChartColors>) => ({
  contentStyle: { background: c.surface, border: `1px solid ${c.grid}`, borderRadius: 12, color: c.ink, fontSize: 13 },
  labelStyle: { color: c.ink, fontWeight: 600 },
  itemStyle: { color: c.ink },
});
