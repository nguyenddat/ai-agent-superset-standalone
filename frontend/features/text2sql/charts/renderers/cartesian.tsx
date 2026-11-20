"use client"

import { useMemo, type ReactElement } from "react"
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  type TooltipContentProps,
} from "recharts"

import {
  boxStats,
  buildChartData,
  histogramBins,
  linearTrend,
  numberOf,
  categoryKey,
  seriesColors,
  waterfallSteps,
  type Context,
  type Point,
  type SeriesDef,
  type WaterfallStep,
} from "../data"
import { formatMeasure, viNumber } from "../format"
import { scaleColor, tokenColor } from "../palette"
import type { AxisSpec, ChartSpec, ChartType } from "../spec"
import {
  AXIS_LINE,
  AXIS_TICK,
  axisText,
  chartHeight,
  dimensionLabels,
  dimensionTitle,
  Empty,
  GRID,
  labelIndexes,
  measureText,
  TipBox,
  useToday,
  WithLegend,
  type LegendItem,
  type RendererProps,
} from "./common"

const BAR_TYPES = new Set<ChartType>([
  "bar", "bar_horizontal", "bar_grouped", "bar_stacked", "bar_stacked_100", "diverging_bar", "waterfall", "histogram",
])
const STACKED = new Set<ChartType>(["bar_stacked", "bar_stacked_100", "area_stacked", "area_stacked_100"])
const EXPAND = new Set<ChartType>(["bar_stacked_100", "area_stacked_100"])
const ORIENTABLE = new Set<ChartType>([
  "bar_grouped", "bar_stacked", "bar_stacked_100", "lollipop", "dumbbell", "diverging_bar", "waterfall",
])
const GAP = "var(--card)"

type ShapeProps = { x?: number; y?: number; width?: number; height?: number; payload?: Point; index?: number }
type Size = number | string
type LabelProps = { x?: Size; y?: Size; width?: Size; height?: Size; value?: unknown; index?: number }

const num = (value: number | string | undefined) => (typeof value === "number" ? value : Number(value ?? 0))

const truncate = (text: string, size: number) => (text.length > size ? `${text.slice(0, size - 1)}…` : text)

type Bound = number | "auto" | "dataMin" | "dataMax" | ((value: number) => number)

// Bars and areas always start at zero: their length is the value. A line only needs a readable range, so its
// axis stays automatic, or hugs the data when the spec turns zero off.
// Rounds away from zero to an even step of the value's second digit, so the axis ends on a readable tick.
function roundOut(value: number) {
  if (!Number.isFinite(value) || value === 0) return 0
  const unit = 10 ** (Math.floor(Math.log10(Math.abs(value))) - 1) * 2
  return Number((Math.sign(value) * Math.ceil(Math.abs(value) / unit) * unit).toPrecision(12))
}

function valueDomain(axis: AxisSpec | undefined, filled: boolean): [Bound, Bound] {
  const tight = axis?.zero === false
  const low = axis?.min ?? (filled ? (value: number) => roundOut(Math.min(0, value)) : tight ? "dataMin" : "auto")
  const high = axis?.max ?? (filled ? (value: number) => roundOut(Math.max(0, value)) : tight ? "dataMax" : "auto")
  return [low, high]
}

const NOTE_TEXT = { fontSize: 11, fill: "var(--muted-foreground)" }

const STEP_FILL = { total: "var(--chart-seq-600)", down: "var(--chart-div-neg)", up: "var(--chart-div-pos)" }

const outlierText = (count: number) => (count ? `, ${count} ngoại lai` : "")

const filledType = (type: ChartType) =>
  BAR_TYPES.has(type) || type === "lollipop" || type.startsWith("area") || type === "combo"

export function isHorizontal(spec: ChartSpec) {
  return spec.type === "bar_horizontal" || (ORIENTABLE.has(spec.type) && spec.orientation === "horizontal")
}

type ReferenceProps = { spec: ChartSpec; horizontal: boolean; label: (key: string) => string }

function References({ spec, horizontal, label }: ReferenceProps) {
  // Spec axes are roles: "y" is the value axis and "x" the category axis, whichever way the bars run.
  const at = (axis: "x" | "y", value: number | string) =>
    axis === "y" ? (horizontal ? { x: Number(value) } : { y: Number(value) }) : horizontal ? { y: value } : { x: value }
  const lines = (spec.reference_lines ?? []).map((line, index) => {
    return (
      <ReferenceLine
        key={`line-${index}`}
        {...at(line.axis, line.value)}
        stroke={tokenColor(line.color ?? "muted")}
        strokeDasharray="4 3"
        ifOverflow="extendDomain"
        label={line.label ? { value: line.label, position: "insideTopRight", ...NOTE_TEXT } : undefined}
      />
    )
  })
  const bands = (spec.reference_bands ?? []).map((band, index) => {
    const onValue = band.axis === "y"
    const range = onValue
      ? horizontal
        ? { x1: Number(band.start), x2: Number(band.end) }
        : { y1: Number(band.start), y2: Number(band.end) }
      : horizontal
        ? { y1: band.start, y2: band.end }
        : { x1: band.start, x2: band.end }
    return (
      <ReferenceArea
        key={`band-${index}`}
        {...range}
        fill="var(--chart-muted)"
        fillOpacity={0.18}
        ifOverflow="extendDomain"
        label={band.label ? { value: band.label, position: "insideTop", ...NOTE_TEXT } : undefined}
      />
    )
  })
  const notes = (spec.annotations ?? []).map((note, index) => {
    const key = String(note.x)
    if (typeof note.y === "number") {
      const position = horizontal ? { x: note.y, y: key } : { x: key, y: note.y }
      return (
        <ReferenceDot
          key={`note-${index}`}
          {...(position as unknown as { x: number; y: number })}
          r={4}
          fill="var(--foreground)"
          stroke={GAP}
          strokeWidth={2}
          label={{ value: note.text, position: "top", fontSize: 11, fill: "var(--foreground)" }}
        />
      )
    }
    return (
      <ReferenceLine
        key={`note-${index}`}
        {...(horizontal ? { y: key } : { x: key })}
        stroke="var(--muted-foreground)"
        strokeDasharray="2 3"
        label={{
          value: `${label(key)}: ${note.text}`,
          position: "insideTopLeft",
          fontSize: 11,
          fill: "var(--foreground)",
        }}
      />
    )
  })
  return [...bands, ...lines, ...notes]
}

function seriesTip(spec: ChartSpec, series: SeriesDef[], label: (key: string) => string, expand: boolean) {
  return function Tip({ active, payload, label: key }: TooltipContentProps) {
    if (!active || !payload?.length) return null
    const point = payload[0]?.payload as Point | undefined
    if (!point) return null
    const total = expand ? series.reduce((sum, def) => sum + (numberOf(point[def.key]) ?? 0), 0) : 0
    const rows = series
      .filter((def) => point[def.key] !== undefined)
      .map((def) => {
        const value = point[def.key]
        const share = expand && total && typeof value === "number" ? ` (${viNumber((value / total) * 100, 1)}%)` : ""
        const text = `${measureText(spec, def, value)}${share}`
        return { key: def.key, label: def.label, value: text, color: tokenColor(def.color) }
      })
    return <TipBox title={label(String(key ?? point.x))} rows={rows} />
  }
}

function barRadius(horizontal: boolean, stacked: boolean): [number, number, number, number] {
  if (stacked) return [0, 0, 0, 0]
  return horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]
}

// A point colour other than the series colour: emphasis, sequential magnitude, or sign for diverging bars.
function pointFill(spec: ChartSpec, def: SeriesDef, points: Point[]) {
  const scheme = spec.colors?.scheme ?? "categorical"
  const values = points.map((point) => numberOf(point[def.key])).filter((value): value is number => value !== null)
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (spec.type === "diverging_bar") {
    const baseline = numberOf(spec.options?.baseline) ?? 0
    return (point: Point) => {
      const value = numberOf(point[def.key]) ?? baseline
      return value >= baseline ? "var(--chart-div-pos)" : "var(--chart-div-neg)"
    }
  }
  if (scheme === "emphasis") {
    const highlight = new Set(spec.colors?.highlight ?? [])
    return (point: Point) => (highlight.has(point.x) ? tokenColor(def.color) : "var(--chart-muted)")
  }
  if (scheme === "sequential" || scheme === "diverging") {
    return (point: Point) => scaleColor(scheme, numberOf(point[def.key]), min, max, numberOf(spec.options?.midpoint))
  }
  return null
}

type LabelOptions = { spec: ChartSpec; def: SeriesDef; indexes: Set<number>; horizontal: boolean; count: number }

// Point labels at the ends of a line lean inwards so the first one clears the value axis and the last one the edge.
function LabelText({ spec, def, indexes, horizontal, count }: LabelOptions) {
  return function Label(props: LabelProps) {
    if (props.index === undefined || !indexes.has(props.index) || typeof props.value !== "number") return null
    const point = !horizontal && !num(props.width)
    const edge = point && props.index === 0 ? "start" : point && props.index === count - 1 ? "end" : "middle"
    const anchor = horizontal ? "start" : edge
    const offset = horizontal ? num(props.width) + 4 : num(props.width) / 2
    const x = num(props.x) + offset + (anchor === "start" && point ? 4 : 0)
    const y = num(props.y) + (horizontal ? num(props.height) / 2 : -8)
    return (
      <text
        x={x}
        y={y}
        fontSize={11}
        fill="var(--foreground)"
        textAnchor={anchor}
        dominantBaseline={horizontal ? "middle" : "auto"}
      >
        {measureText(spec, def, props.value)}
      </text>
    )
  }
}

function lollipopShape(color: string, horizontal: boolean) {
  return function Lollipop(props: unknown): ReactElement {
    const { x = 0, y = 0, width = 0, height = 0 } = props as ShapeProps
    if (horizontal) {
      const cy = y + height / 2
      const end = width >= 0 ? x + width : x + width
      return (
        <g>
          <line x1={x} x2={end} y1={cy} y2={cy} stroke={color} strokeWidth={2} />
          <circle cx={end} cy={cy} r={5} fill={color} stroke={GAP} strokeWidth={2} />
        </g>
      )
    }
    const cx = x + width / 2
    return (
      <g>
        <line x1={cx} x2={cx} y1={y + height} y2={y} stroke={color} strokeWidth={2} />
        <circle cx={cx} cy={y} r={5} fill={color} stroke={GAP} strokeWidth={2} />
      </g>
    )
  }
}

function dumbbellShape(first: string, second: string, horizontal: boolean) {
  return function Dumbbell(props: unknown): ReactElement {
    const { x = 0, y = 0, width = 0, height = 0, payload } = props as ShapeProps
    const range = (payload?.range as [number, number] | undefined) ?? [0, 0]
    const ascending = range[0] <= range[1]
    if (horizontal) {
      const cy = y + height / 2
      const low = x
      const high = x + width
      return (
        <g>
          <line x1={low} x2={high} y1={cy} y2={cy} stroke="var(--chart-muted)" strokeWidth={2} />
          <circle cx={ascending ? low : high} cy={cy} r={5} fill={first} stroke={GAP} strokeWidth={2} />
          <circle cx={ascending ? high : low} cy={cy} r={5} fill={second} stroke={GAP} strokeWidth={2} />
        </g>
      )
    }
    const cx = x + width / 2
    const bottom = y + height
    return (
      <g>
        <line x1={cx} x2={cx} y1={bottom} y2={y} stroke="var(--chart-muted)" strokeWidth={2} />
        <circle cx={cx} cy={ascending ? bottom : y} r={5} fill={first} stroke={GAP} strokeWidth={2} />
        <circle cx={cx} cy={ascending ? y : bottom} r={5} fill={second} stroke={GAP} strokeWidth={2} />
      </g>
    )
  }
}

function CartesianPlot({ ctx, series, points, spec, height, compact }: {
  ctx: Context
  series: SeriesDef[]
  points: Point[]
  spec: ChartSpec
  height: number
  compact?: boolean
}) {
  const today = useToday()
  const type = spec.type
  const horizontal = isHorizontal(spec)
  const stacked = STACKED.has(type)
  const expand = EXPAND.has(type)
  const labels = dimensionLabels(ctx, "x", today)
  const options = spec.options ?? {}
  const valueAxis = spec.axes?.y
  const categoryAxis = spec.axes?.x
  const first = series[0]
  const logScale = valueAxis?.scale === "log"

  let data: Point[] = points
  let dataKeyRange = false
  if (type === "waterfall" && first) {
    const total = (options.total ?? true) ? String(options.total_label ?? "Tổng") : null
    data = waterfallSteps(points, first.key, total).map((step) => ({ ...step, x: step.x }))
    dataKeyRange = true
  }
  if (type === "dumbbell" && series.length >= 2) {
    const [from, to] = [series[0].key, series[1].key]
    data = points.map((point) => ({ ...point, range: [numberOf(point[from]) ?? 0, numberOf(point[to]) ?? 0] }))
    dataKeyRange = true
  }

  const category = {
    dataKey: "x",
    type: "category" as const,
    tick: AXIS_TICK,
    axisLine: AXIS_LINE,
    tickLine: false,
    hide: categoryAxis?.hide,
    tickFormatter: (key: string) => truncate(labels.short(String(key)), horizontal ? 18 : 14),
    interval: "preserveStartEnd" as const,
    angle: categoryAxis?.tick_angle ?? 0,
    textAnchor: (categoryAxis?.tick_angle ?? 0) < 0 ? ("end" as const) : ("middle" as const),
    height: (categoryAxis?.tick_angle ?? 0) < 0 ? 64 : 28,
  }
  const value = {
    type: "number" as const,
    tick: AXIS_TICK,
    axisLine: false,
    tickLine: false,
    hide: valueAxis?.hide,
    scale: logScale ? ("log" as const) : ("auto" as const),
    domain: expand ? ([0, 1] as [number, number]) : valueDomain(valueAxis, filledType(type)),
    allowDataOverflow: valueAxis?.min !== undefined || valueAxis?.max !== undefined,
    tickFormatter: (tick: number) => (expand ? `${viNumber(tick * 100, 0)}%` : axisText(spec, first, tick)),
    width: horizontal ? undefined : 56,
  }
  const Tip = seriesTip(spec, series, labels.long, expand)
  const marks = series.map((def, index) => {
    const color = tokenColor(def.color)
    const own = type.startsWith("line") ? "line" : type.startsWith("area") ? "area" : "bar"
    const mark = type === "combo" ? (def.mark ?? (index === 0 ? "bar" : "line")) : own
    const values = data.map((point) => numberOf(point[def.key]))
    const single = mark === "bar" && series.length === 1
    const auto = single ? "all" : series.length <= 4 && mark !== "bar" ? "endpoints" : "none"
    const indexes = labelIndexes(spec.labels?.show, values, auto)
    const content = LabelText({ spec, def, indexes, horizontal, count: data.length })
    const label = compact ? null : <LabelList dataKey={def.key} content={content} />
    if (mark === "line") {
      const curve = (options.curve as string) ?? "linear"
      const showPoints = (options.points as string) ?? "auto"
      const visible = showPoints === "show" || (showPoints === "auto" && data.length <= 24)
      const dot = visible ? { r: 3, strokeWidth: 2, stroke: GAP, fill: color } : false
      return (
        <Line
          key={def.key}
          dataKey={def.key}
          name={def.label}
          type={curve === "step" ? "step" : curve === "monotone" ? "monotone" : "linear"}
          stroke={color}
          strokeWidth={2}
          dot={dot}
          activeDot={{ r: 5, strokeWidth: 2, stroke: GAP }}
          connectNulls={Boolean(options.connect_nulls)}
          isAnimationActive={false}
        >
          {label}
        </Line>
      )
    }
    if (mark === "area") {
      return (
        <Area
          key={def.key}
          dataKey={def.key}
          name={def.label}
          type={options.curve === "monotone" ? "monotone" : options.curve === "step" ? "step" : "linear"}
          stroke={color}
          strokeWidth={2}
          fill={color}
          fillOpacity={stacked ? 0.55 : 0.1}
          stackId={stacked ? "stack" : undefined}
          connectNulls={Boolean(options.connect_nulls)}
          isAnimationActive={false}
        >
          {label}
        </Area>
      )
    }
    if (type === "lollipop") {
      return (
        <Bar
          key={def.key}
          dataKey={def.key}
          name={def.label}
          fill={color}
          barSize={14}
          shape={lollipopShape(color, horizontal)}
          isAnimationActive={false}
        >
          {label}
        </Bar>
      )
    }
    const fill = pointFill(spec, def, data)
    return (
      <Bar
        key={def.key}
        dataKey={def.key}
        name={def.label}
        fill={color}
        maxBarSize={24}
        radius={barRadius(horizontal, stacked)}
        stackId={stacked ? "stack" : undefined}
        stroke={stacked ? GAP : undefined}
        strokeWidth={stacked ? 1 : 0}
        isAnimationActive={false}
      >
        {fill && data.map((point) => <Cell key={point.x} fill={fill(point)} />)}
        {label}
      </Bar>
    )
  })

  let rangeMark: ReactElement | null = null
  if (dataKeyRange && type === "waterfall" && first) {
    rangeMark = (
      <Bar dataKey="range" name={first.label} maxBarSize={24} radius={[2, 2, 2, 2]} isAnimationActive={false}>
        {data.map((step) => (
          <Cell key={step.x} fill={STEP_FILL[step.kind as WaterfallStep["kind"]]} />
        ))}
      </Bar>
    )
  }
  if (dataKeyRange && type === "dumbbell") {
    rangeMark = (
      <Bar
        dataKey="range"
        name="Khoảng"
        barSize={14}
        shape={dumbbellShape(tokenColor(series[0].color), tokenColor(series[1].color), horizontal)}
        isAnimationActive={false}
      />
    )
  }

  const WaterfallTip = ({ active, payload }: TooltipContentProps) => {
    const step = payload?.[0]?.payload as (Point & { delta: number; kind: string }) | undefined
    if (!active || !step) return null
    return (
      <TipBox
        title={labels.long(step.x)}
        rows={[
          {
            key: "delta",
            label: step.kind === "total" ? "Tổng" : "Biến động",
            value: measureText(spec, first, step.delta),
          },
        ]}
      />
    )
  }

  return (
    <ComposedChart
      responsive
      style={{ width: "100%", height }}
      data={data}
      layout={horizontal ? "vertical" : "horizontal"}
      stackOffset={expand ? "expand" : undefined}
      margin={{ top: 20, right: horizontal ? 48 : 16, bottom: 4, left: 4 }}
      accessibilityLayer
    >
      <CartesianGrid {...GRID} vertical={horizontal} horizontal={!horizontal} />
      {horizontal ? (
        <>
          <XAxis {...value} />
          <YAxis {...category} width={categoryAxis?.hide ? 0 : 120} angle={0} textAnchor="end" height={undefined} />
        </>
      ) : (
        <>
          <XAxis {...category} />
          <YAxis {...value} />
        </>
      )}
      <Tooltip
        content={type === "waterfall" ? WaterfallTip : Tip}
        cursor={
          BAR_TYPES.has(type) || type === "lollipop" || type === "dumbbell"
            ? { fill: "var(--muted)", opacity: 0.6 }
            : { stroke: "var(--muted-foreground)", strokeWidth: 1 }
        }
      />
      {type === "diverging_bar" && (
        <ReferenceLine
          {...(horizontal ? { x: numberOf(options.baseline) ?? 0 } : { y: numberOf(options.baseline) ?? 0 })}
          stroke="var(--muted-foreground)"
        />
      )}
      {References({ spec, horizontal, label: labels.short })}
      {rangeMark ?? marks}
    </ComposedChart>
  )
}

function legendItems(series: SeriesDef[], type: ChartType): LegendItem[] {
  return series.map((def) => ({
    key: def.key,
    label: def.label,
    color: def.color,
    shape: type.startsWith("line") || (type === "combo" && def.mark === "line")
      ? "line"
      : type === "dumbbell"
        ? "dot"
        : "square",
  }))
}

// Axis titles sit outside the plot as plain text: the value title above it, the category title below it.
function AxisTitles({ spec, children }: { spec: ChartSpec; children: ReactElement }) {
  const horizontal = isHorizontal(spec)
  const valueTitle = spec.axes?.y?.title
  const categoryTitle = spec.axes?.x?.title
  const above = horizontal ? categoryTitle : valueTitle
  const below = horizontal ? valueTitle : categoryTitle
  return (
    <div className="flex flex-col gap-1">
      {above && <span className="text-xs text-muted-foreground">{above}</span>}
      {children}
      {below && <span className="self-center text-xs text-muted-foreground">{below}</span>}
    </div>
  )
}

export function CartesianRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const { ctx, series, points } = built
  if (!points.length || !series.length) return <Empty />
  const horizontal = isHorizontal(spec)
  const groups = points.length + (spec.type === "waterfall" ? 1 : 0)
  const height = props.height ?? (horizontal ? Math.min(900, Math.max(160, groups * 28 + 40)) : chartHeight(props))
  const facet = spec.facet
  if (facet && series.length > 1 && !props.compact) {
    const columns = Math.min(facet.columns ?? 2, series.length)
    return (
      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${columns > 1 ? 240 : 320}px), 1fr))` }}
      >
        {series.map((def) => (
          <figure key={def.key} className="flex min-w-0 flex-col gap-1">
            <figcaption className="text-xs font-medium">{def.label}</figcaption>
            <CartesianPlot
              ctx={ctx}
              series={[def]}
              points={points}
              spec={{ ...spec, facet: null }}
              height={200}
              compact
            />
          </figure>
        ))}
      </div>
    )
  }
  const shown = spec.type === "dumbbell" ? series.slice(0, 2) : series
  const items = spec.type === "waterfall" ? [] : legendItems(shown, spec.type)
  return (
    <WithLegend spec={spec} items={props.compact ? [] : items}>
      <AxisTitles spec={spec}>
        <CartesianPlot ctx={ctx} series={series} points={points} spec={spec} height={height} compact={props.compact} />
      </AxisTitles>
    </WithLegend>
  )
}

// ---- Distributions ----

export function HistogramRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const field = fields.find((item) => item.name === spec.encoding?.x?.field)
  const position = fields.findIndex((item) => item.name === spec.encoding?.x?.field)
  const values = built.ctx.prepared.rows
    .map((row) => numberOf(row[position]))
    .filter((value): value is number => value !== null)
  const bins = histogramBins(values, numberOf(spec.options?.bins), numberOf(spec.options?.bin_width))
  if (!bins.length) return <Empty />
  const label = (bin: { start: number; end: number }) =>
    `${formatMeasure(bin.start, field)}–${formatMeasure(bin.end, field)}`
  const data = bins.map((bin) => ({ ...bin, x: label(bin) }))
  return (
    <ComposedChart
      responsive
      style={{ width: "100%", height: chartHeight(props) }}
      data={data}
      margin={{ top: 16, right: 12, bottom: 4, left: 4 }}
      accessibilityLayer
    >
      <CartesianGrid {...GRID} />
      <XAxis
        dataKey="x"
        tick={AXIS_TICK}
        axisLine={AXIS_LINE}
        tickLine={false}
        interval="preserveStartEnd"
        tickFormatter={(text: string) => truncate(text, 16)}
      />
      <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} width={40} />
      <Tooltip
        cursor={{ fill: "var(--muted)", opacity: 0.6 }}
        content={({ active, payload }: TooltipContentProps) => {
          const bin = payload?.[0]?.payload as (typeof data)[number] | undefined
          if (!active || !bin) return null
          return <TipBox title={bin.x} rows={[{ key: "count", label: "Số dòng", value: viNumber(bin.count, 0) }]} />
        }}
      />
      <Bar
        dataKey="count"
        name="Số dòng"
        fill={tokenColor("series-1")}
        radius={[4, 4, 0, 0]}
        isAnimationActive={false}
      />
    </ComposedChart>
  )
}

function boxShape(color: string) {
  return function BoxShape(props: unknown): ReactElement {
    const { x = 0, y = 0, width = 0, height = 0, payload } = props as ShapeProps
    type Stats = { range: [number, number]; min: number; q1: number; median: number; q3: number; max: number }
    const stats = payload as unknown as Stats & { outliers: number[] }
    const [low, high] = stats.range
    const scale = (value: number) => (high === low ? y + height / 2 : y + ((high - value) / (high - low)) * height)
    const cx = x + width / 2
    const half = Math.min(width / 2, 14)
    return (
      <g>
        <line
          x1={cx}
          x2={cx}
          y1={scale(stats.max)}
          y2={scale(stats.q3)}
          stroke="var(--muted-foreground)"
          strokeWidth={1.5}
        />
        <line
          x1={cx}
          x2={cx}
          y1={scale(stats.q1)}
          y2={scale(stats.min)}
          stroke="var(--muted-foreground)"
          strokeWidth={1.5}
        />
        <line
          x1={cx - half / 2}
          x2={cx + half / 2}
          y1={scale(stats.max)}
          y2={scale(stats.max)}
          stroke="var(--muted-foreground)"
          strokeWidth={1.5}
        />
        <line
          x1={cx - half / 2}
          x2={cx + half / 2}
          y1={scale(stats.min)}
          y2={scale(stats.min)}
          stroke="var(--muted-foreground)"
          strokeWidth={1.5}
        />
        <rect
          x={cx - half}
          y={scale(stats.q3)}
          width={half * 2}
          height={Math.max(1, scale(stats.q1) - scale(stats.q3))}
          rx={3}
          fill={color}
          fillOpacity={0.25}
          stroke={color}
          strokeWidth={1.5}
        />
        <line
          x1={cx - half}
          x2={cx + half}
          y1={scale(stats.median)}
          y2={scale(stats.median)}
          stroke={color}
          strokeWidth={2}
        />
        {stats.outliers.map((value, index) => (
          <circle key={index} cx={cx} cy={scale(value)} r={3} fill="none" stroke={color} strokeWidth={1.5} />
        ))}
      </g>
    )
  }
}

export function BoxPlotRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const yName = spec.encoding?.y?.[0]?.field
  const xName = spec.encoding?.x?.field
  const yIndex = fields.findIndex((item) => item.name === yName)
  const xIndex = xName ? fields.findIndex((item) => item.name === xName) : -1
  const groups = new Map<string, number[]>()
  for (const row of built.ctx.prepared.rows) {
    const value = numberOf(row[yIndex])
    if (value === null) continue
    const key = xIndex >= 0 ? categoryKey(row[xIndex]) : dimensionTitle(built.ctx, "x") || "Tất cả"
    groups.set(key, [...(groups.get(key) ?? []), value])
  }
  const whisker = spec.options?.whisker === "minmax" ? "minmax" : "tukey"
  const stats = boxStats(groups, whisker, spec.options?.outliers !== false)
  if (!stats.length) return <Empty />
  const yField = fields[yIndex]
  const def = { field: yField, measure: spec.encoding?.y?.[0] }
  const labels = dimensionLabels(built.ctx, "x", today)
  const data = stats.map((item) => ({
    ...item,
    range: [Math.min(item.min, ...item.outliers), Math.max(item.max, ...item.outliers)] as [number, number],
  }))
  const colors = seriesColors(data.map((item) => item.x))
  return (
    <ComposedChart
      responsive
      style={{ width: "100%", height: chartHeight(props) }}
      data={data}
      margin={{ top: 16, right: 12, bottom: 4, left: 4 }}
      accessibilityLayer
    >
      <CartesianGrid {...GRID} />
      <XAxis
        dataKey="x"
        tick={AXIS_TICK}
        axisLine={AXIS_LINE}
        tickLine={false}
        tickFormatter={(key: string) => truncate(labels.short(key), 14)}
      />
      <YAxis
        tick={AXIS_TICK}
        axisLine={false}
        tickLine={false}
        width={56}
        domain={["auto", "auto"]}
        tickFormatter={(tick: number) => axisText(spec, def, tick)}
      />
      <Tooltip
        cursor={{ fill: "var(--muted)", opacity: 0.6 }}
        content={({ active, payload }: TooltipContentProps) => {
          const item = payload?.[0]?.payload as (typeof data)[number] | undefined
          if (!active || !item) return null
          const text = (value: number) => measureText(spec, def, value)
          return (
            <TipBox
              title={labels.long(item.x)}
              rows={[
                { key: "max", label: "Lớn nhất (trong râu)", value: text(item.max) },
                { key: "q3", label: "Tứ phân vị trên", value: text(item.q3) },
                { key: "median", label: "Trung vị", value: text(item.median) },
                { key: "q1", label: "Tứ phân vị dưới", value: text(item.q1) },
                { key: "min", label: "Nhỏ nhất (trong râu)", value: text(item.min) },
              ]}
              footer={`${viNumber(item.count, 0)} giá trị${outlierText(item.outliers.length)}`}
            />
          )
        }}
      />
      <Bar
        dataKey="range"
        barSize={28}
        shape={boxShape(tokenColor(colors.get(data[0].x) ?? "series-1"))}
        isAnimationActive={false}
      />
    </ComposedChart>
  )
}

// ---- Relationships ----

export function ScatterRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const encoding = spec.encoding ?? {}
  const at = (name?: string | null) => (name ? fields.findIndex((item) => item.name === name) : -1)
  const xIndex = at(encoding.x?.field)
  const yIndex = at(encoding.y?.[0]?.field)
  const sizeIndex = at(encoding.size?.field)
  const seriesIndex = at(encoding.series?.field)
  const labelIndex = at(encoding.label?.field)
  const xDef = { field: fields[xIndex], measure: undefined }
  const yDef = { field: fields[yIndex], measure: encoding.y?.[0] }
  const sizeDef = { field: fields[sizeIndex], measure: encoding.size ?? undefined }
  const allSeries = seriesIndex >= 0 ? rows.map((row) => categoryKey(row[seriesIndex])) : ["all"]
  const colors = seriesColors(allSeries, spec.colors?.assign)
  const points = built.ctx.prepared.rows.map((row) => ({
    x: numberOf(row[xIndex]) ?? 0,
    y: numberOf(row[yIndex]) ?? 0,
    size: sizeIndex >= 0 ? (numberOf(row[sizeIndex]) ?? 0) : 1,
    series: seriesIndex >= 0 ? categoryKey(row[seriesIndex]) : "all",
    label: labelIndex >= 0 ? categoryKey(row[labelIndex]) : null,
  }))
  if (!points.length) return <Empty />
  const groups = [...colors.keys()].filter((key) => points.some((point) => point.series === key))
  const trend = spec.options?.trend === "linear" ? linearTrend(points) : null
  const labelMode = spec.labels?.show ?? "auto"
  const showLabels = labelIndex >= 0 && labelMode !== "none" && (points.length <= 12 || labelMode === "all")
  const items: LegendItem[] =
    seriesIndex >= 0 ? groups.map((key) => ({ key, label: key, color: colors.get(key)!, shape: "dot" })) : []
  const xTitle = spec.axes?.x?.title ?? encoding.x?.label ?? fields[xIndex]?.label
  const yTitle = spec.axes?.y?.title ?? encoding.y?.[0]?.label ?? fields[yIndex]?.label
  return (
    <WithLegend spec={spec} items={props.compact ? [] : items}>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted-foreground">{yTitle}</span>
        <ScatterChart
          responsive
          style={{ width: "100%", height: chartHeight(props) }}
          margin={{ top: 12, right: 16, bottom: 4, left: 4 }}
          accessibilityLayer
        >
          <CartesianGrid {...GRID} vertical />
          <XAxis
            dataKey="x"
            type="number"
            name={xTitle}
            tick={AXIS_TICK}
            axisLine={AXIS_LINE}
            tickLine={false}
            scale={spec.axes?.x?.scale === "log" ? "log" : "auto"}
            domain={[spec.axes?.x?.min ?? "auto", spec.axes?.x?.max ?? "auto"]}
            tickFormatter={(tick: number) => axisText(spec, xDef, tick)}
          />
          <YAxis
            dataKey="y"
            type="number"
            name={yTitle}
            tick={AXIS_TICK}
            axisLine={false}
            tickLine={false}
            width={56}
            scale={spec.axes?.y?.scale === "log" ? "log" : "auto"}
            domain={[spec.axes?.y?.min ?? "auto", spec.axes?.y?.max ?? "auto"]}
            tickFormatter={(tick: number) => axisText(spec, yDef, tick)}
          />
          <ZAxis dataKey="size" type="number" range={spec.type === "bubble" ? [60, 900] : [64, 64]} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3", stroke: "var(--muted-foreground)" }}
            content={({ active, payload }: TooltipContentProps) => {
              const point = payload?.[0]?.payload as (typeof points)[number] | undefined
              if (!active || !point) return null
              const rowsOut = [
                { key: "x", label: xTitle ?? "x", value: measureText(spec, xDef, point.x) },
                { key: "y", label: yTitle ?? "y", value: measureText(spec, yDef, point.y) },
                ...(sizeIndex >= 0
                  ? [{ key: "size", label: fields[sizeIndex].label, value: measureText(spec, sizeDef, point.size) }]
                  : []),
              ]
              return <TipBox title={point.label ?? (seriesIndex >= 0 ? point.series : undefined)} rows={rowsOut} />
            }}
          />
          {groups.map((key) => {
            const color = tokenColor(colors.get(key))
            return (
              <Scatter
                key={key}
                name={key}
                data={points.filter((point) => point.series === key)}
                fill={color}
                fillOpacity={spec.type === "bubble" ? 0.55 : 0.85}
                stroke={GAP}
                strokeWidth={1.5}
                isAnimationActive={false}
              >
                {showLabels && <LabelList dataKey="label" position="top" fontSize={11} fill="var(--foreground)" />}
              </Scatter>
            )
          })}
          {trend && (
            <ReferenceLine
              segment={trend}
              stroke="var(--muted-foreground)"
              strokeDasharray="5 4"
              ifOverflow="hidden"
              label={{ value: "Xu hướng", position: "insideTopRight", ...NOTE_TEXT }}
            />
          )}
        </ScatterChart>
        <span className="self-center text-xs text-muted-foreground">{xTitle}</span>
      </div>
    </WithLegend>
  )
}
