import type { Metric } from "./types"

export const metricTitle = (metric: Pick<Metric, "label" | "name">) => metric.label?.trim() || metric.name

/** Number formats Superset understands (d3-format), with a sample value each so the choice reads at a glance. */
export const FORMAT_PRESETS = [
  { value: "", label: "Mặc định" },
  { value: ",d", label: "Số nguyên" },
  { value: ",.2f", label: "2 số lẻ" },
  { value: ".1%", label: "Phần trăm" },
  { value: ".3s", label: "Rút gọn" },
] as const

export const CUSTOM_FORMAT = "custom"

const SAMPLE = 1234567.891
const SAMPLE_RATIO = 0.1234

/** A sample formatted the way Superset will show it, or null for a format this preview doesn't know. */
export function formatSample(format: string | null, currency: string | null) {
  const spec = format?.trim() ?? ""
  const match = /^(,)?(?:\.(\d+))?([dfs%])$/.exec(spec)
  if (spec && !match) return null
  const [, comma, digits, kind] = match ?? [null, ",", undefined, "s"]
  const precision = digits === undefined ? undefined : Number(digits)
  let text: string
  if (kind === "%") {
    text = new Intl.NumberFormat("en-US", {
      style: "percent",
      minimumFractionDigits: precision ?? 0,
      maximumFractionDigits: precision ?? 0,
      useGrouping: !!comma,
    }).format(SAMPLE_RATIO)
  } else if (kind === "s") {
    text = new Intl.NumberFormat("en-US", {
      notation: "compact",
      maximumSignificantDigits: precision ?? 3,
    }).format(SAMPLE)
  } else {
    text = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: kind === "d" ? 0 : (precision ?? 6),
      maximumFractionDigits: kind === "d" ? 0 : (precision ?? 6),
      useGrouping: !!comma,
    }).format(SAMPLE)
  }
  return currency?.trim() && kind !== "%" ? `${currency.trim()} ${text}` : text
}

const AGGREGATE = /^\s*(SUM|AVG|MIN|MAX|COUNT)\s*\(\s*(DISTINCT\s+)?(.+?)\s*\)\s*$/i

/** `SUM(amount)` → `sum__amount`, Superset's own naming for simple metrics. */
export function suggestName(expression: string) {
  const match = AGGREGATE.exec(expression)
  if (!match) return null
  const column = match[3]!.replace(/["`[\]]/g, "").replace(/\W+/g, "_").replace(/^_|_$/g, "").toLowerCase()
  const fn = `${match[1]!.toLowerCase()}${match[2] ? "_distinct" : ""}`
  return column ? `${fn}__${column}` : fn
}

const AGGREGATE_LABEL: Record<string, string> = {
  SUM: "Tổng",
  AVG: "Trung bình",
  MIN: "Nhỏ nhất",
  MAX: "Lớn nhất",
  COUNT: "Số lượng",
}

/** `SUM(amount)` with the column shown as "Doanh thu" → "Tổng Doanh thu". */
export function suggestLabel(expression: string, displayName: (column: string) => string | undefined) {
  const match = AGGREGATE.exec(expression)
  if (!match) return null
  const fn = match[1]!.toUpperCase()
  const column = match[3]!.replace(/["`[\]]/g, "")
  if (column === "*") return "Số dòng"
  const name = displayName(column) ?? column
  return match[2] ? `Số ${name} khác nhau` : `${AGGREGATE_LABEL[fn]} ${name}`
}
