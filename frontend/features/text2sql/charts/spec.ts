// Chart spec version 1, mirroring backend/common/charts/spec.py. Specs coming back from the backend are compact
// (defaults dropped), so every key is optional here and readers fill in the defaults.
// This file, data.ts, format.ts and suggest.ts run under `node --test` as well: plain TypeScript only (no enums,
// no `@/` imports), and imports between them carry the `.ts` extension.

export const CHART_TYPES = [
  "kpi", "bullet", "bar", "bar_horizontal", "bar_grouped", "lollipop", "dumbbell", "diverging_bar", "radial_bar",
  "radar", "bar_stacked", "bar_stacked_100", "pie", "donut", "treemap", "sunburst", "waterfall", "funnel", "line",
  "area", "area_stacked", "area_stacked_100", "combo", "sparkline_table", "calendar_heatmap", "histogram",
  "box_plot", "heatmap", "scatter", "bubble", "sankey", "table",
] as const

export type ChartType = (typeof CHART_TYPES)[number]

export const PALETTE = [
  "series-1", "series-2", "series-3", "series-4", "series-5", "series-6", "series-7", "series-8", "muted",
] as const

export type PaletteToken = (typeof PALETTE)[number]

export type FieldType = "number" | "date" | "datetime" | "text" | "boolean" | "other"
export type TimeUnit = "day" | "week" | "month" | "quarter" | "year"

// One column of a query result, as the backend describes it (FieldOut / ChartField).
export type ChartField = {
  name: string
  label: string
  type: FieldType
  unit?: string | null
  decimals?: number | null
  percent?: boolean
  additive?: boolean | null
  role?: "measure" | "dimension"
  format_hint?: "plain" | null
  time_unit?: TimeUnit | null
  pii?: boolean
}

export type Aggregate = "auto" | "none" | "sum" | "avg" | "min" | "max" | "count" | "count_distinct"

export type NumberFormat = {
  style?: "number" | "percent" | "compact"
  decimals?: number | null
  percent_input?: "ratio" | "percent"
  unit?: string | null
}

export type DateFormat = { style?: "auto" | "day" | "day_weekday" | "week" | "month" | "quarter" | "year" | "datetime" }

export type FieldRef = { field: string; label?: string | null }
export type Dimension = FieldRef & { time_unit?: TimeUnit | null }
export type Measure = FieldRef & {
  aggregate?: Aggregate
  mark?: "bar" | "line" | "area" | null
  color?: PaletteToken | null
  format?: NumberFormat | null
}

export type Encoding = {
  x?: Dimension | null
  y?: Measure[]
  series?: FieldRef | null
  row?: Dimension | null
  path?: FieldRef[]
  size?: Measure | null
  color?: Measure | null
  goal?: Measure | null
  compare?: Measure | null
  source?: FieldRef | null
  target?: FieldRef | null
  label?: FieldRef | null
}

export type FilterOp = "eq" | "ne" | "in" | "not_in" | "gt" | "gte" | "lt" | "lte"
export type FilterValue = string | number | boolean | null | (string | number)[]
export type FilterSpec = { field: string; op: FilterOp; value: FilterValue }
export type SortSpec = { by?: string; order?: "asc" | "desc" }
export type TopN = { n: number; other?: boolean; other_label?: string }

export type Transform = {
  filter?: FilterSpec[]
  sort?: SortSpec | null
  top_n?: TopN | null
  limit?: number | null
  index_to?: "none" | "first"
  cumulative?: boolean
}

export type AxisSpec = {
  title?: string | null
  hide?: boolean
  scale?: "linear" | "log"
  min?: number | null
  max?: number | null
  zero?: boolean
  tick_angle?: 0 | -45 | -90
}

export type ReferenceLine = { axis: "x" | "y"; value: number | string; label?: string | null; color?: PaletteToken }
export type ReferenceBand = { axis: "x" | "y"; start: number | string; end: number | string; label?: string | null }
export type Annotation = { x: number | string; y?: number | null; text: string }
export type LabelMode = "auto" | "none" | "endpoints" | "extremes" | "all"
export type ColorScheme = "categorical" | "sequential" | "diverging" | "emphasis"

export type ChartSpec = {
  version?: 1
  type: ChartType
  title?: string | null
  subtitle?: string | null
  encoding?: Encoding
  transform?: Transform
  orientation?: "vertical" | "horizontal" | null
  axes?: { x?: AxisSpec; y?: AxisSpec }
  format?: { number?: NumberFormat | null; date?: DateFormat }
  reference_lines?: ReferenceLine[]
  reference_bands?: ReferenceBand[]
  annotations?: Annotation[]
  legend?: { show?: "auto" | "show" | "hide"; position?: "top" | "bottom" | "right" }
  labels?: { show?: LabelMode }
  colors?: { scheme?: ColorScheme; assign?: Record<string, PaletteToken>; highlight?: string[] }
  facet?: { by: "measure" | "series"; columns?: number } | null
  options?: Record<string, unknown>
}

export type ChartDisplay = "chart" | "chart_if_last" | "none"
export type ChartSource = "auto" | "agent"

export const isChartType = (value: unknown): value is ChartType =>
  typeof value === "string" && (CHART_TYPES as readonly string[]).includes(value)

export const isChartSpec = (value: unknown): value is ChartSpec =>
  typeof value === "object" && value !== null && isChartType((value as { type?: unknown }).type)
