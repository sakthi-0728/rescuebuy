import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";

// AG Grid Community only (MIT licence, no licence key needed).
ModuleRegistry.registerModules([AllCommunityModule]);

/**
 * One grid theme for every table in the app. Colours come from the app's CSS variables, so the
 * grids follow light and dark mode and the rest of the design without a second palette.
 */
export const gridTheme = themeQuartz.withParams({
  accentColor: "var(--accent)",
  backgroundColor: "var(--surface)",
  foregroundColor: "var(--ink)",
  borderColor: "var(--line)",
  headerTextColor: "var(--muted)",
  headerBackgroundColor: "var(--surface)",
  headerFontWeight: 600,
  fontFamily: "inherit",
  fontSize: 14,
  headerHeight: 44,
  rowHeight: 60,
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  oddRowBackgroundColor: "var(--surface)",
  rowHoverColor: "var(--accent-soft)",
});

export const gridDefaults = {
  theme: gridTheme,
  domLayout: "autoHeight" as const,
  suppressMovableColumns: true,
  animateRows: false,
};
