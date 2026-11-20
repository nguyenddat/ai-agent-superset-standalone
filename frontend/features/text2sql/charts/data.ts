// Turns query rows into chart data. `prepare` is the same algorithm as backend/common/charts/prepare.py (null rules,
// filter, aggregate, top N with "Khác", sort, limit) and both sides run tests/fixtures/chart_cases.json against it.
// The builders after it shape the prepared cells for each renderer. Pure functions: also run by `node --test`.

import { EMPTY_LABEL, isFiniteNumber, isNonFinite } from "./format.ts"
import type { ChartField, ChartSpec, ChartType, FilterSpec, Measure, PaletteToken, TimeUnit } from "./spec.ts"

export type Row = unknown[]
export type Stats = { points: number; groups: number; series: number; dropped_null: number }

export type Cell = { dims: Record<string, string>; values: Record<string, number | null> }

export type Prepared = {
  rows: Row[]
  dropped_null: number
  aggregated: boolean
  duplicate: boolean
  cells: Cell[]
  x_values: string[]
  other: string | null
  aggregates: Record<string, string>
  stats: Stats
}

const DIMENSION_ROLES = ["x", "row", "path", "source", "target", "series"] as const
const MEASURE_ROLES = ["size", "color", "goal", "compare"] as const
const RAW_REQUIRED: Partial<Record<ChartType, string[]>> = {
  scatter: ["x", "y0"],
  bubble: ["x", "y0", "size"],
  histogram: ["x"],
  box_plot: ["y0"],
}
const NO_AGGREGATE = new Set<ChartType>(["histogram", "box_plot", "scatter", "bubble", "table"])
const CATEGORY_TYPES = new Set(["text", "boolean", "other"])
const TEMPORAL_TYPES = new Set(["date", "datetime"])
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

type Ref = { field: string; label?: string | null; time_unit?: TimeUnit | null }

export const numberOf = (value: unknown): number | null => (isFiniteNumber(value) ? value : null)

export function categoryKey(value: unknown): string {
  if (value === null || value === undefined) return EMPTY_LABEL
  if (typeof value === "boolean") return value ? "true" : "false"
  if (typeof value === "number") {
    if (Number.isInteger(value)) return Math.abs(value) < 1e21 ? String(value) : BigInt(value).toString()
    return String(value)
  }
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

export const temporalKey = (value: unknown): string | null =>
  typeof value === "string" && ISO_DATE.test(value.slice(0, 10)) ? value : null

const pad = (value: number) => String(value).padStart(2, "0")

export function bucket(value: string, unit: TimeUnit): string {
  const text = value.slice(0, 10)
  if (unit === "day") return text
  if (unit === "month") return text.slice(0, 7)
  if (unit === "year") return text.slice(0, 4)
  if (unit === "quarter") return `${text.slice(0, 4)}-Q${Math.floor((Number(text.slice(5, 7)) - 1) / 3) + 1}`
  const [year, month, day] = text.split("-").map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7))
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`
}

// Number columns default to the dimension role, like ChartField.
export const isMeasureField = (field: ChartField) => field.type === "number" && field.role === "measure"
export const isCategorical = (field: ChartField) =>
  CATEGORY_TYPES.has(field.type) || (field.type === "number" && field.role !== "measure")
export const isTemporal = (field: ChartField) => TEMPORAL_TYPES.has(field.type)
const isPositional = (field: ChartField) => TEMPORAL_TYPES.has(field.type) || field.type === "number"

function isMissing(value: unknown, field: ChartField): boolean {
  if (value === null || value === undefined) return true
  if (field.type === "number") return numberOf(value) === null
  if (TEMPORAL_TYPES.has(field.type)) return temporalKey(value) === null
  return false
}

export function dimensionKey(value: unknown, field: ChartField, unit: TimeUnit | null | undefined): string {
  if (TEMPORAL_TYPES.has(field.type)) {
    const key = temporalKey(value)
    if (key === null) return categoryKey(value)
    return unit && unit !== field.time_unit ? bucket(key, unit) : key
  }
  return categoryKey(value)
}

export function measureSlots(spec: ChartSpec): [string, Measure][] {
  const encoding = spec.encoding ?? {}
  const slots: [string, Measure][] = (encoding.y ?? []).map((item, index) => [`y${index}`, item])
  for (const role of MEASURE_ROLES) {
    const item = encoding[role]
    if (item) slots.push([role, item])
  }
  return slots
}

export function dimensionRefs(spec: ChartSpec): [string, Ref][] {
  const encoding = spec.encoding ?? {}
  const refs: [string, Ref][] = []
  for (const role of DIMENSION_ROLES) {
    if (role === "path") (encoding.path ?? []).forEach((item, index) => refs.push([`path${index}`, item]))
    else if (encoding[role]) refs.push([role, encoding[role] as Ref])
  }
  return refs
}

type Comparable = string | number | null

function compare(cell: unknown, field: ChartField, rule: FilterSpec): boolean {
  if (cell === null || cell === undefined || isNonFinite(cell)) return rule.op === "ne" || rule.op === "not_in"
  const wanted = Array.isArray(rule.value) ? rule.value : [rule.value]
  let left: Comparable
  let rights: Comparable[]
  if (field.type === "number") {
    left = numberOf(cell)
    rights = wanted.map(numberOf)
  } else if (TEMPORAL_TYPES.has(field.type)) {
    left = String(cell)
    rights = wanted.map((value) => (value === null || value === undefined ? null : String(value)))
    if (rights.every((right) => typeof right === "string" && right.length === 10)) left = left.slice(0, 10)
  } else {
    left = categoryKey(cell)
    rights = wanted.map(categoryKey)
  }
  if (left === null) return rule.op === "ne" || rule.op === "not_in"
  if (rule.op === "eq") return left === rights[0]
  if (rule.op === "ne") return left !== rights[0]
  if (rule.op === "in") return rights.includes(left)
  if (rule.op === "not_in") return !rights.includes(left)
  const right = rights[0]
  if (right === null || right === undefined || typeof right !== typeof left) return false
  if (rule.op === "gt") return left > right
  if (rule.op === "gte") return left >= right
  if (rule.op === "lt") return left < right
  return left <= right
}

export function resolvedAggregate(item: Measure, field: ChartField | undefined, duplicate: boolean): string {
  const how = item.aggregate ?? "auto"
  if (how !== "auto") return how
  if (!duplicate) return "none"
  return field?.additive === true ? "sum" : "avg"
}

function aggregate(values: unknown[], how: string): number | null {
  const kept = () => values.filter((value) => value !== null && value !== undefined && !isNonFinite(value))
  if (how === "count") return kept().length
  if (how === "count_distinct") return new Set(kept().map(categoryKey)).size
  const numbers = values.map(numberOf)
  if (how === "none") return numbers.length ? numbers[0] : null
  const present = numbers.filter((value): value is number => value !== null)
  if (!present.length) return null
  if (how === "sum") return present.reduce((total, value) => total + value, 0)
  if (how === "avg") return present.reduce((total, value) => total + value, 0) / present.length
  if (how === "min") return Math.min(...present)
  return Math.max(...present)
}

type OrderKey = [number, number | string]

function orderKey(value: string, field: ChartField | undefined): OrderKey {
  if (field?.type === "number") {
    const parsed = Number(value)
    return value.trim() !== "" && !Number.isNaN(parsed) ? [0, parsed] : [1, value]
  }
  return [0, value]
}

const compareKeys = (a: OrderKey, b: OrderKey) =>
  a[0] !== b[0] ? a[0] - b[0] : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0

function totalsBy(cells: Cell[], role: string, slot: string | null): Map<string, number> {
  const totals = new Map<string, number>()
  for (const item of cells) {
    const value = slot ? item.values[slot] : null
    if (value !== null && value !== undefined) totals.set(item.dims[role], (totals.get(item.dims[role]) ?? 0) + value)
  }
  return totals
}

function sortedX(spec: ChartSpec, values: string[], xField: ChartField, cells: Cell[], other: string | null): string[] {
  const plain = values.filter((value) => value !== other)
  const tail = other !== null && values.includes(other) ? [other] : []
  const sort = spec.transform?.sort
  const by = sort?.by ?? "none"
  const descending = !!sort && (sort.order ?? "desc") === "desc"
  if (by === "x" || (by === "none" && !isCategorical(xField))) {
    const sign = by === "x" && descending ? -1 : 1
    return [...plain].sort((a, b) => sign * compareKeys(orderKey(a, xField), orderKey(b, xField))).concat(tail)
  }
  if (by === "none") return plain.concat(tail)
  let slot = "y0"
  ;(spec.encoding?.y ?? []).forEach((item, index) => {
    if (by === item.field) slot = `y${index}`
  })
  const totals = totalsBy(cells, "x", slot)
  const missing = descending ? -Infinity : Infinity
  const sign = descending ? -1 : 1
  return [...plain]
    .sort((a, b) => {
      const left = totals.get(a) ?? missing
      const right = totals.get(b) ?? missing
      return left === right ? 0 : sign * (left < right ? -1 : 1)
    })
    .concat(tail)
}

export function prepare(spec: ChartSpec, fields: ChartField[], rows: Row[]): Prepared {
  const index = new Map(fields.map((item, position) => [item.name, position]))
  const byName = new Map(fields.map((item) => [item.name, item]))
  const cellOf = (row: Row, name: string) => {
    const position = index.get(name)
    return position !== undefined && Array.isArray(row) && position < row.length ? row[position] : null
  }
  const encoding = spec.encoding ?? {}
  const slots = measureSlots(spec)
  const dims = dimensionRefs(spec).filter(([, ref]) => byName.has(ref.field))
  const required: string[] = []
  for (const [role, ref] of dims) {
    if ((role === "x" || role === "row") && isPositional(byName.get(ref.field)!)) required.push(ref.field)
  }
  const raw = RAW_REQUIRED[spec.type] ?? []
  const slotFields = new Map(slots.map(([slot, item]) => [slot, item.field]))
  if (raw.includes("x") && encoding.x) required.push(encoding.x.field)
  for (const slot of raw) if (slotFields.has(slot)) required.push(slotFields.get(slot)!)
  let kept: Row[] = []
  let dropped = 0
  for (const row of rows) {
    if (required.some((name) => byName.has(name) && isMissing(cellOf(row, name), byName.get(name)!))) dropped += 1
    else kept.push(row)
  }
  for (const rule of spec.transform?.filter ?? []) {
    const field = byName.get(rule.field)
    if (field) kept = kept.filter((row) => compare(cellOf(row, rule.field), field, rule))
  }
  const xRef = encoding.x ?? null
  if (NO_AGGREGATE.has(spec.type) || !dims.length) {
    const series = encoding.series
    const xField = xRef ? byName.get(xRef.field) : undefined
    const xKeys = () => new Set(kept.map((row) => categoryKey(cellOf(row, xRef!.field))))
    const groups = xField && isCategorical(xField) ? xKeys().size : 0
    const seriesCount = series ? new Set(kept.map((row) => categoryKey(cellOf(row, series.field)))).size : 0
    return {
      rows: kept,
      dropped_null: dropped,
      aggregated: false,
      duplicate: false,
      cells: [],
      x_values: [],
      other: null,
      aggregates: {},
      stats: { points: kept.length, groups, series: seriesCount, dropped_null: dropped },
    }
  }
  const keyed = new Map<string, { dims: Record<string, string>; rows: Row[] }>()
  for (const row of kept) {
    const parts: Record<string, string> = {}
    for (const [role, ref] of dims) {
      parts[role] = dimensionKey(cellOf(row, ref.field), byName.get(ref.field)!, ref.time_unit)
    }
    const key = dims.map(([role]) => parts[role]).join("\u0001")
    const group = keyed.get(key)
    if (group) group.rows.push(row)
    else keyed.set(key, { dims: parts, rows: [row] })
  }
  const duplicate = [...keyed.values()].some((group) => group.rows.length > 1)
  const aggregates = Object.fromEntries(
    slots.map(([slot, item]) => [slot, resolvedAggregate(item, byName.get(item.field), duplicate)]),
  )
  let cells: Cell[] = [...keyed.values()].map((group) => ({
    dims: group.dims,
    values: Object.fromEntries(
      slots.map(([slot, item]) => [
        slot,
        aggregate(
          group.rows.map((row) => cellOf(row, item.field)),
          aggregates[slot],
        ),
      ]),
    ),
  }))
  const xField = xRef && byName.has(xRef.field) ? byName.get(xRef.field)! : null
  let xValues = xField ? [...new Set(cells.map((item) => item.dims.x))] : []
  const rankSlot = slots.length ? slots[0][0] : null
  let other: string | null = null
  const topN = spec.transform?.top_n
  if (xField && topN && isCategorical(xField) && xValues.length > topN.n) {
    const totals = totalsBy(cells, "x", rankSlot)
    const ranked = [...xValues].sort((a, b) => {
      const left = -(totals.get(a) ?? -Infinity)
      const right = -(totals.get(b) ?? -Infinity)
      return left === right ? 0 : left < right ? -1 : 1
    })
    const keep = new Set(ranked.slice(0, topN.n))
    const rest = cells.filter((item) => !keep.has(item.dims.x))
    cells = cells.filter((item) => keep.has(item.dims.x))
    xValues = xValues.filter((value) => keep.has(value))
    if (topN.other ?? true) {
      other = topN.other_label ?? "Khác"
      const merged = new Map<string, Cell>()
      for (const item of rest) {
        const dimsOther: Record<string, string> = { ...item.dims, x: other }
        const key = dims.map(([role]) => dimsOther[role]).join("\u0001")
        let target = merged.get(key)
        if (!target) {
          target = { dims: dimsOther, values: Object.fromEntries(Object.keys(item.values).map((slot) => [slot, null])) }
          merged.set(key, target)
        }
        for (const [slot, value] of Object.entries(item.values)) {
          if (value !== null) target.values[slot] = (target.values[slot] || 0) + value
        }
      }
      cells.push(...merged.values())
      xValues.push(other)
    }
  }
  const limit = spec.transform?.limit
  if (xField) {
    xValues = sortedX(spec, xValues, xField, cells, other)
    if (limit !== null && limit !== undefined) xValues = xValues.slice(0, limit)
    const allowed = new Set(xValues)
    cells = cells.filter((item) => allowed.has(item.dims.x))
  } else if (limit !== null && limit !== undefined) {
    cells = cells.slice(0, limit)
  }
  const points = cells.filter((item) => Object.values(item.values).some((value) => value !== null))
  let groups = 0
  if (xField) {
    const present = new Set(points.map((item) => item.dims.x))
    xValues = xValues.filter((value) => present.has(value))
    groups = xValues.length
  } else if ((encoding.path ?? []).length) {
    groups = new Set(points.map((item) => item.dims[`path${encoding.path!.length - 1}`])).size
  } else if (encoding.source) {
    groups = new Set(points.map((item) => `${item.dims.source}\u0001${item.dims.target}`)).size
  }
  const hasSeries = dims.some(([role]) => role === "series")
  const seriesCount = hasSeries ? new Set(points.map((item) => item.dims.series)).size : (encoding.y ?? []).length
  return {
    rows: kept,
    dropped_null: dropped,
    aggregated: true,
    duplicate,
    cells,
    x_values: xValues,
    other,
    aggregates,
    stats: { points: points.length, groups, series: seriesCount, dropped_null: dropped },
  }
}

export const chartStats = (spec: ChartSpec, fields: ChartField[], rows: Row[]) => prepare(spec, fields, rows).stats

// ---- Shapes for the renderers ----

export type SeriesDef = {
  key: string
  label: string
  color: PaletteToken
  field?: ChartField
  measure?: Measure
  mark?: "bar" | "line" | "area"
}

export type Point = Record<string, unknown> & { x: string }

export type Context = {
  spec: ChartSpec
  fields: ChartField[]
  byName: Map<string, ChartField>
  prepared: Prepared
}

const TOKENS: PaletteToken[] = [
  "series-1", "series-2", "series-3", "series-4", "series-5", "series-6", "series-7", "series-8",
]

export const tokenAt = (index: number): PaletteToken => TOKENS[index % TOKENS.length]

export function context(spec: ChartSpec, fields: ChartField[], rows: Row[]): Context {
  const byName = new Map(fields.map((item) => [item.name, item]))
  return { spec, fields, byName, prepared: prepare(spec, fields, rows) }
}

const measureLabel = (item: Measure, field: ChartField | undefined) => item.label || field?.label || item.field

// Colour follows the entity: series values take palette slots in the order they first appear in all the rows,
// before any filter, so filtering never repaints the survivors. Assigned tokens win and are skipped for others.
export function seriesColors(values: string[], assign: Record<string, PaletteToken> = {}): Map<string, PaletteToken> {
  const taken = new Set(Object.values(assign))
  const free = TOKENS.filter((token) => !taken.has(token))
  const colors = new Map<string, PaletteToken>()
  let next = 0
  for (const value of values) {
    if (colors.has(value)) continue
    if (assign[value]) colors.set(value, assign[value])
    else {
      colors.set(value, free.length ? free[next % free.length] : tokenAt(next))
      next += 1
    }
  }
  return colors
}

export function seriesDefs(ctx: Context, rows: Row[]): SeriesDef[] {
  const { spec, byName } = ctx
  const encoding = spec.encoding ?? {}
  const y = encoding.y ?? []
  const assign = spec.colors?.assign ?? {}
  const series = encoding.series && byName.has(encoding.series.field) ? encoding.series : null
  if (series) {
    const position = ctx.fields.findIndex((item) => item.name === series.field)
    const all = rows.map((row) => categoryKey(row[position]))
    const colors = seriesColors(all, assign)
    const present = new Set(ctx.prepared.cells.map((item) => item.dims.series))
    const field = byName.get(y[0]?.field ?? "")
    return [...colors.keys()]
      .filter((value) => present.has(value))
      .map((value) => ({ key: `s:${value}`, label: value, color: colors.get(value)!, field, measure: y[0] }))
  }
  const used = new Set(y.map((item) => item.color).filter(Boolean))
  const free = TOKENS.filter((token) => !used.has(token))
  let next = 0
  return y.map((item, index) => {
    const field = byName.get(item.field)
    const color = item.color ?? assign[item.field] ?? free[next++ % Math.max(free.length, 1)] ?? tokenAt(index)
    const label = measureLabel(item, field)
    return { key: `y${index}`, label, color, field, measure: item, mark: item.mark ?? undefined }
  })
}

// One object per x value with a value per series: long rows pivot to wide when there is a series column.
export function widePoints(ctx: Context, series: SeriesDef[]): Point[] {
  const { prepared, spec } = ctx
  const hasSeries = series.some((item) => item.key.startsWith("s:"))
  const order = prepared.x_values.length
    ? prepared.x_values
    : [...new Set(prepared.cells.map((item) => item.dims.x ?? ""))]
  const points = new Map<string, Point>(order.map((x) => [x, { x } as Point]))
  for (const item of prepared.cells) {
    const x = item.dims.x ?? ""
    const point = points.get(x)
    if (!point) continue
    if (hasSeries) point[`s:${item.dims.series}`] = item.values.y0 ?? null
    else series.forEach((def) => (point[def.key] = item.values[def.key] ?? null))
  }
  const list = [...points.values()]
  const transform = spec.transform ?? {}
  for (const def of series) {
    if (transform.cumulative) {
      let total = 0
      for (const point of list) {
        const value = point[def.key]
        if (typeof value === "number") {
          total += value
          point[def.key] = total
        }
      }
    }
    if (transform.index_to === "first") {
      const base = list.map((point) => point[def.key]).find((value): value is number => typeof value === "number")
      if (base) {
        for (const point of list) {
          const value = point[def.key]
          if (typeof value === "number") point[def.key] = (value / base) * 100
        }
      }
    }
  }
  return list
}

// Waterfall: each step floats from the running total before it to the one after it, then a total bar.
export type WaterfallStep = { x: string; range: [number, number]; delta: number; kind: "up" | "down" | "total" }

export function waterfallSteps(points: Point[], key: string, total: string | null): WaterfallStep[] {
  let running = 0
  const steps: WaterfallStep[] = []
  for (const point of points) {
    const delta = typeof point[key] === "number" ? (point[key] as number) : 0
    steps.push({ x: point.x, range: [running, running + delta], delta, kind: delta < 0 ? "down" : "up" })
    running += delta
  }
  if (total !== null) steps.push({ x: total, range: [0, running], delta: running, kind: "total" })
  return steps
}

export type Bin = { x: string; start: number; end: number; count: number }

export function histogramBins(values: number[], bins?: number | null, width?: number | null): Bin[] {
  if (!values.length) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const sturges = Math.min(30, Math.max(5, Math.ceil(Math.log2(values.length) + 1)))
  const count = bins ?? (width ? Math.max(1, Math.ceil((max - min) / width) || 1) : sturges)
  const step = width ?? ((max - min) / count || 1)
  const result: Bin[] = Array.from({ length: count }, (_, index) => ({
    x: String(index),
    start: min + index * step,
    end: min + (index + 1) * step,
    count: 0,
  }))
  for (const value of values) {
    const slot = Math.min(count - 1, Math.floor((value - min) / step))
    result[slot].count += 1
  }
  return result
}

export type BoxStats = {
  x: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  outliers: number[]
  count: number
}

const quantile = (sorted: number[], q: number) => {
  const position = (sorted.length - 1) * q
  const low = Math.floor(position)
  const high = Math.ceil(position)
  return sorted[low] + (sorted[high] - sorted[low]) * (position - low)
}

export function boxStats(groups: Map<string, number[]>, whisker: "tukey" | "minmax", outliers: boolean): BoxStats[] {
  return [...groups.entries()].map(([x, values]) => {
    const sorted = [...values].sort((a, b) => a - b)
    const q1 = quantile(sorted, 0.25)
    const q3 = quantile(sorted, 0.75)
    const fence = whisker === "tukey" ? 1.5 * (q3 - q1) : Infinity
    const inside = sorted.filter((value) => value >= q1 - fence && value <= q3 + fence)
    return {
      x,
      min: inside[0] ?? sorted[0],
      q1,
      median: quantile(sorted, 0.5),
      q3,
      max: inside.at(-1) ?? sorted.at(-1)!,
      outliers: outliers ? sorted.filter((value) => value < q1 - fence || value > q3 + fence) : [],
      count: sorted.length,
    }
  })
}

// Least-squares line through the points, for the scatter trend option.
type XY = { x: number; y: number }

export function linearTrend(points: XY[]): [XY, XY] | null {
  if (points.length < 2) return null
  const n = points.length
  const sx = points.reduce((total, point) => total + point.x, 0)
  const sy = points.reduce((total, point) => total + point.y, 0)
  const sxx = points.reduce((total, point) => total + point.x * point.x, 0)
  const sxy = points.reduce((total, point) => total + point.x * point.y, 0)
  const denominator = n * sxx - sx * sx
  if (!denominator) return null
  const slope = (n * sxy - sx * sy) / denominator
  const intercept = (sy - slope * sx) / n
  const xs = points.map((point) => point.x)
  const low = Math.min(...xs)
  const high = Math.max(...xs)
  return [
    { x: low, y: intercept + slope * low },
    { x: high, y: intercept + slope * high },
  ]
}

export type TreeNode = { name: string; value: number; children?: TreeNode[] }

// Treemap and sunburst: path columns are the parents, x (treemap) or the last path column the leaves.
export function tree(cells: Cell[], levels: string[]): TreeNode[] {
  const root: TreeNode = { name: "", value: 0, children: [] }
  for (const item of cells) {
    const value = item.values.y0
    if (value === null || value === undefined || value <= 0) continue
    let node = root
    levels.forEach((role, depth) => {
      const name = item.dims[role] ?? EMPTY_LABEL
      const leaf = depth === levels.length - 1
      node.children ??= []
      let child = node.children.find((entry) => entry.name === name)
      if (!child) {
        child = { name, value: 0, ...(leaf ? {} : { children: [] }) }
        node.children.push(child)
      }
      child.value += value
      node = child
    })
  }
  return root.children ?? []
}

export type SankeyData = { nodes: { name: string }[]; links: { source: number; target: number; value: number }[] }

export function sankeyData(cells: Cell[]): SankeyData {
  const names: string[] = []
  const indexOf = (name: string) => {
    let position = names.indexOf(name)
    if (position === -1) position = names.push(name) - 1
    return position
  }
  const links = cells
    .filter((item) => typeof item.values.y0 === "number" && item.values.y0 > 0)
    .map((item) => ({
      source: indexOf(`${item.dims.source}`),
      // A node that is both a source and a target stays one node; sankey has no cycles (validator V32).
      target: indexOf(`${item.dims.target}`),
      value: item.values.y0 as number,
    }))
  return { nodes: names.map((name) => ({ name })), links }
}

export type GridCell = { x: string; row: string; value: number | null }

export function heatGrid(cells: Cell[], xValues: string[]): { xs: string[]; rows: string[]; cells: GridCell[] } {
  const rows = [...new Set(cells.map((item) => item.dims.row))]
  const xs = xValues.length ? xValues : [...new Set(cells.map((item) => item.dims.x))]
  return {
    xs,
    rows,
    cells: cells.map((item) => ({ x: item.dims.x, row: item.dims.row, value: item.values.color ?? null })),
  }
}

// The full chart data with the stats the backend computes for the same spec.
export function buildChartData(spec: ChartSpec, fields: ChartField[], rows: Row[]) {
  const ctx = context(spec, fields, rows)
  const series = ctx.prepared.aggregated ? seriesDefs(ctx, rows) : []
  const wide = ctx.prepared.aggregated && (spec.encoding?.x || !spec.encoding?.path?.length)
  const points = wide ? widePoints(ctx, series) : []
  return { ctx, series, points, stats: ctx.prepared.stats }
}
