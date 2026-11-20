// Default spec of each chart type for a result: the same builders as backend/common/charts/suggest.py (BUILDERS),
// so switching type gives the spec the backend already checked when it listed the type in `chart_types`.

import { categoryKey, isCategorical, isMeasureField, isTemporal } from "./data.ts"
import type { Row } from "./data.ts"
import type { ChartField, ChartSpec, ChartType, Measure } from "./spec.ts"

type Column = { field: ChartField; distinct: number }
type Profile = { times: Column[]; texts: Column[]; numbers: Column[]; rows: number }

const GOAL_WORDS = ["muc tieu", "target", "ke hoach", "chi tieu", "goal"]

const folded = (value: string) =>
  value
    .toLowerCase()
    .replaceAll("đ", "d")
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ")

export function profile(fields: ChartField[], rows: Row[]): Profile {
  const columns = fields.map((field, index) => ({
    field,
    distinct: new Set(rows.map((row) => categoryKey(Array.isArray(row) ? row[index] : null))).size,
  }))
  return {
    times: columns.filter((item) => isTemporal(item.field)),
    texts: columns.filter((item) => isCategorical(item.field)),
    numbers: columns.filter((item) => isMeasureField(item.field)),
    rows: rows.length,
  }
}

const ref = (column: Column) => ({ field: column.field.name })
const measure = (column: Column, extra: Partial<Measure> = {}): Measure => ({ field: column.field.name, ...extra })

const unitsDiffer = (columns: Column[]) =>
  new Set(columns.map((item) => item.field.unit || (item.field.percent ? "%" : null)).filter(Boolean)).size > 1

const top = (column: Column, limit: number, other: boolean) =>
  column.distinct <= limit ? {} : { top_n: { n: limit, other } }

function sortedBar(type: ChartType, data: Profile, limit: number): ChartSpec | null {
  const { times, texts, numbers } = data
  if (!numbers.length) return null
  if (texts.length) {
    return {
      type,
      encoding: { x: ref(texts[0]), y: [measure(numbers[0])] },
      transform: { sort: { by: "y", order: "desc" }, ...top(texts[0], limit, numbers[0].field.additive === true) },
    }
  }
  if (times.length && type !== "bar_horizontal") {
    return { type, encoding: { x: ref(times[0]), y: [measure(numbers[0])] } }
  }
  return null
}

function xOne(type: ChartType, data: Profile): ChartSpec | null {
  const x = data.texts[0] ?? data.times[0]
  return x && data.numbers.length ? { type, encoding: { x: ref(x), y: [measure(data.numbers[0])] } } : null
}

function multi(type: ChartType, data: Profile, limit: number): ChartSpec | null {
  const { times, texts, numbers } = data
  const x = times[0] ?? texts[0]
  if (!x || !numbers.length) return null
  const others = texts.filter((item) => item !== x)
  if (others.length && numbers.length === 1) {
    return { type, encoding: { x: ref(x), y: [measure(numbers[0])], series: ref(others[0]) } }
  }
  if (numbers.length >= 2) {
    return { type, encoding: { x: ref(x), y: numbers.slice(0, limit).map((item) => measure(item)) } }
  }
  return null
}

function kpi(data: Profile): ChartSpec | null {
  const { times, numbers } = data
  if (data.rows === 1 && numbers.length) {
    return { type: "kpi", encoding: { y: numbers.slice(0, 4).map((item) => measure(item)) } }
  }
  if (times.length && numbers.length) return { type: "kpi", encoding: { x: ref(times[0]), y: [measure(numbers[0])] } }
  return null
}

function bullet(data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  const goals = numbers.filter((item) =>
    GOAL_WORDS.some((word) => folded(`${item.field.name} ${item.field.label}`.replaceAll("_", " ")).includes(word)),
  )
  const values = numbers.filter((item) => !goals.includes(item))
  if (!goals.length || !values.length) return null
  return {
    type: "bullet",
    encoding: {
      y: [measure(values[0])],
      goal: measure(goals[0]),
      ...(texts.length && data.rows > 1 ? { x: ref(texts[0]) } : {}),
    },
  }
}

function dumbbell(data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  if (!texts.length || !numbers.length) return null
  if (numbers.length === 2) {
    return { type: "dumbbell", encoding: { x: ref(texts[0]), y: numbers.map((item) => measure(item)) } }
  }
  if (texts.length >= 2 && texts[1].distinct === 2) {
    return { type: "dumbbell", encoding: { x: ref(texts[0]), y: [measure(numbers[0])], series: ref(texts[1]) } }
  }
  return null
}

function radar(data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  if (!texts.length || !numbers.length) return null
  if (texts.length >= 2) {
    return { type: "radar", encoding: { x: ref(texts[0]), y: [measure(numbers[0])], series: ref(texts[1]) } }
  }
  return { type: "radar", encoding: { x: ref(texts[0]), y: numbers.slice(0, 3).map((item) => measure(item)) } }
}

function pie(type: ChartType, data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  if (!texts.length || !numbers.length) return null
  return {
    type,
    encoding: { x: ref(texts[0]), y: [measure(numbers[0])] },
    transform: { sort: { by: "y", order: "desc" }, ...(texts[0].distinct > 6 ? { top_n: { n: 5, other: true } } : {}) },
  }
}

function hierarchy(type: ChartType, data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  if (!numbers.length || !texts.length) return null
  const ordered = [...texts].sort((a, b) => a.distinct - b.distinct)
  if (type === "sunburst") {
    if (ordered.length < 2) return null
    return { type, encoding: { path: ordered.slice(0, 3).map(ref), y: [measure(numbers[0])] } }
  }
  return {
    type,
    encoding: {
      x: ref(ordered.at(-1)!),
      y: [measure(numbers[0])],
      ...(ordered.length >= 2 ? { path: [ref(ordered[0])] } : {}),
    },
  }
}

function line(type: ChartType, data: Profile): ChartSpec | null {
  const { times, texts, numbers } = data
  const x = times[0]
  if (!x || !numbers.length) return null
  if (texts.length && numbers.length === 1 && type !== "area") {
    return { type, encoding: { x: ref(x), y: [measure(numbers[0])], series: ref(texts[0]) } }
  }
  const limit = type === "area" ? 3 : 8
  if ((type === "area_stacked" || type === "area_stacked_100") && numbers.length < 2) return null
  const spec: ChartSpec = { type, encoding: { x: ref(x), y: numbers.slice(0, limit).map((item) => measure(item)) } }
  if (numbers.length > 1 && unitsDiffer(numbers.slice(0, limit))) {
    if (type !== "line") return null
    spec.facet = { by: "measure" }
  }
  return spec
}

function combo(data: Profile): ChartSpec | null {
  const { times, texts, numbers } = data
  const x = times[0] ?? texts[0]
  if (!x || numbers.length < 2) return null
  const y = numbers.slice(0, 4).map((item, index) => measure(item, { mark: index === 0 ? "bar" : "line" }))
  const transform = unitsDiffer(numbers.slice(0, 4)) ? { transform: { index_to: "first" as const } } : {}
  return { type: "combo", encoding: { x: ref(x), y }, ...transform }
}

const BUILDERS: Record<ChartType, (data: Profile) => ChartSpec | null> = {
  kpi,
  bullet,
  bar: (data) => sortedBar("bar", data, 40),
  bar_horizontal: (data) => sortedBar("bar_horizontal", data, 15),
  bar_grouped: (data) => multi("bar_grouped", data, 4),
  lollipop: (data) => sortedBar("lollipop", data, 15),
  dumbbell,
  diverging_bar: (data) => xOne("diverging_bar", data),
  radial_bar: (data) => xOne("radial_bar", data),
  radar,
  bar_stacked: (data) => multi("bar_stacked", data, 8),
  bar_stacked_100: (data) => multi("bar_stacked_100", data, 8),
  pie: (data) => pie("pie", data),
  donut: (data) => pie("donut", data),
  treemap: (data) => hierarchy("treemap", data),
  sunburst: (data) => hierarchy("sunburst", data),
  waterfall: (data) => xOne("waterfall", data),
  funnel: (data) => xOne("funnel", data),
  line: (data) => line("line", data),
  area: (data) => line("area", data),
  area_stacked: (data) => line("area_stacked", data),
  area_stacked_100: (data) => line("area_stacked_100", data),
  combo,
  sparkline_table: ({ times, texts, numbers }) =>
    times.length && texts.length && numbers.length
      ? { type: "sparkline_table", encoding: { x: ref(times[0]), y: [measure(numbers[0])], series: ref(texts[0]) } }
      : null,
  calendar_heatmap: ({ times, numbers }) => {
    const days = times.filter(
      (item) => item.field.type === "date" && (!item.field.time_unit || item.field.time_unit === "day"),
    )
    if (!days.length || !numbers.length) return null
    return { type: "calendar_heatmap", encoding: { x: ref(days[0]), color: measure(numbers[0]) } }
  },
  histogram: ({ numbers }) => (numbers.length ? { type: "histogram", encoding: { x: ref(numbers[0]) } } : null),
  box_plot: ({ texts, numbers }) =>
    numbers.length
      ? { type: "box_plot", encoding: { y: [measure(numbers[0])], ...(texts.length ? { x: ref(texts[0]) } : {}) } }
      : null,
  heatmap: ({ times, texts, numbers }) => {
    const dims = [...texts, ...times]
    return dims.length >= 2 && numbers.length
      ? { type: "heatmap", encoding: { x: ref(dims[0]), row: ref(dims[1]), color: measure(numbers[0]) } }
      : null
  },
  scatter: (data) => scatter("scatter", data),
  bubble: (data) => scatter("bubble", data),
  sankey: ({ texts, numbers }) =>
    texts.length >= 2 && numbers.length
      ? { type: "sankey", encoding: { source: ref(texts[0]), target: ref(texts[1]), y: [measure(numbers[0])] } }
      : null,
  table: () => ({ type: "table" }),
}

function scatter(type: ChartType, data: Profile): ChartSpec | null {
  const { texts, numbers } = data
  if (numbers.length < (type === "bubble" ? 3 : 2)) return null
  const labels = texts.filter((item) => !item.field.pii)
  return {
    type,
    encoding: {
      x: ref(numbers[0]),
      y: [measure(numbers[1])],
      ...(type === "bubble" ? { size: measure(numbers[2]) } : {}),
      ...(labels.length ? { label: ref(labels[0]) } : {}),
    },
  }
}

// The spec for another type: the backend's default for that type, keeping the title the result already had.
export function defaultSpecFor(
  type: ChartType,
  fields: ChartField[],
  rows: Row[],
  current?: ChartSpec | null,
): ChartSpec {
  const spec = BUILDERS[type](profile(fields, rows)) ?? { type }
  return current?.title ? { ...spec, title: current.title } : spec
}
