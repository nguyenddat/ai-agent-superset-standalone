"use client"

import { useMemo } from "react"
import { ArrowDownRightIcon, ArrowUpRightIcon, MinusIcon } from "lucide-react"
import { Bar, BarChart, Line, LineChart, Tooltip, YAxis, type TooltipContentProps } from "recharts"

import { cn } from "@/lib/utils"

import { buildChartData, categoryKey, numberOf, seriesColors, type Point } from "../data"
import { tokenColor } from "../palette"
import type { ChartField, Measure } from "../spec"
import { ResultTable } from "../result-table"
import { dimensionLabels, dimensionTitle, Empty, measureText, TipBox, useToday, type RendererProps } from "./common"

const fieldOf = (fields: ChartField[], measure?: Measure | null) => fields.find((item) => item.name === measure?.field)
const labelOf = (fields: ChartField[], measure?: Measure | null) =>
  measure ? measure.label || fieldOf(fields, measure)?.label || measure.field : ""

type DeltaProps = { value: number; compare: number; good: "up" | "down"; text: (value: number) => string }

function Delta({ value, compare, good, text }: DeltaProps) {
  const diff = value - compare
  const better = diff === 0 ? null : (diff > 0) === (good === "up")
  const Icon = diff > 0 ? ArrowUpRightIcon : diff < 0 ? ArrowDownRightIcon : MinusIcon
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
        better === null && "text-muted-foreground",
        better === true && "text-emerald-700 dark:text-emerald-400",
        better === false && "text-red-700 dark:text-red-400",
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {diff > 0 ? "+" : ""}
      {text(diff)}
      <span className="sr-only">{better === null ? "không đổi" : better ? "tốt hơn" : "kém hơn"}</span>
    </span>
  )
}

type SparkProps = { points: { x: string; value: number | null }[]; color: string; label: (key: string) => string }

function Spark({ points, color, label }: SparkProps) {
  return (
    <LineChart
      responsive
      style={{ width: "100%", height: 44 }}
      data={points}
      margin={{ top: 4, right: 2, bottom: 2, left: 2 }}
    >
      <YAxis hide domain={["dataMin", "dataMax"]} />
      <Line dataKey="value" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
      <Tooltip
        cursor={{ stroke: "var(--muted-foreground)" }}
        content={({ active, payload }: TooltipContentProps) => {
          const point = payload?.[0]?.payload as { x: string; text: string } | undefined
          if (!active || !point) return null
          return <TipBox title={label(point.x)} rows={[{ key: "v", label: "", value: point.text }]} />
        }}
      />
    </LineChart>
  )
}

// Stat tiles: the headline number, with a trend line when there is a time axis and a delta when there is a compare.
export function KpiRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const encoding = spec.encoding ?? {}
  const y = encoding.y ?? []
  const good = spec.options?.delta_good === "down" ? "down" : "up"
  const sparkline = spec.options?.sparkline !== false
  const labels = dimensionLabels(built.ctx, "x", today)
  type Trend = { x: string; value: number | null; text: string }[]
  type Tile = { key: string; label: string; value: unknown; compare: number | null; measure: Measure; trend?: Trend }
  let tiles: Tile[] = []
  if (encoding.x && built.ctx.prepared.aggregated) {
    const { x_values, cells: all } = built.ctx.prepared
    const cells = x_values.map((x) => all.find((cell) => cell.dims.x === x)!).filter(Boolean)
    const last = cells.at(-1)
    tiles = y.map((measure, index) => ({
      key: `y${index}`,
      label: labelOf(fields, measure),
      value: last?.values[`y${index}`] ?? null,
      compare: last?.values.compare ?? null,
      measure,
      trend: cells.map((cell) => ({
        x: cell.dims.x,
        value: cell.values[`y${index}`] ?? null,
        text: measureText(spec, { field: fieldOf(fields, measure), measure }, cell.values[`y${index}`]),
      })),
    }))
  } else {
    const row = built.ctx.prepared.rows[0]
    const position = (name?: string) => fields.findIndex((item) => item.name === name)
    tiles = row
      ? y.map((measure, index) => ({
          key: `y${index}`,
          label: labelOf(fields, measure),
          value: row[position(measure.field)],
          compare: encoding.compare ? numberOf(row[position(encoding.compare.field)]) : null,
          measure,
        }))
      : []
  }
  if (!tiles.length) return <Empty />
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, 11rem), 1fr))` }}>
      {tiles.map((tile, index) => {
        const def = { field: fieldOf(fields, tile.measure), measure: tile.measure }
        const value = numberOf(tile.value)
        return (
          <div key={tile.key} className="flex min-w-0 flex-col gap-1 rounded-lg border bg-card p-3">
            <span className="truncate text-xs text-muted-foreground" title={tile.label}>
              {tile.label}
            </span>
            <span className="text-2xl font-semibold tabular-nums">{measureText(spec, def, tile.value)}</span>
            {value !== null && tile.compare !== null && (
              <span className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Delta value={value} compare={tile.compare} good={good} text={(diff) => measureText(spec, def, diff)} />
                so với {labelOf(fields, encoding.compare)} {measureText(spec, def, tile.compare)}
              </span>
            )}
            {sparkline && tile.trend && tile.trend.length > 1 && (
              <>
                <Spark
                  points={tile.trend}
                  color={tokenColor(tile.measure.color ?? `series-${(index % 8) + 1}` as never)}
                  label={labels.long}
                />
                <span className="text-[11px] text-muted-foreground">
                  {labels.short(tile.trend[0].x)} – {labels.short(tile.trend.at(-1)!.x)}
                </span>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}

// A bar against its target and up to three qualitative bands; the target is a dark tick.
export function BulletRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const encoding = spec.encoding ?? {}
  const measure = encoding.y?.[0]
  const def = { field: fieldOf(fields, measure), measure }
  const target = numberOf(spec.options?.target_value)
  const goalText = (goal: number | null) => (goal !== null ? `, mục tiêu ${measureText(spec, def, goal)}` : "")
  const rawRanges = Array.isArray(spec.options?.ranges) ? (spec.options.ranges as unknown[]) : []
  const ranges = rawRanges.map(numberOf).filter((value): value is number => value !== null)
  const labels = dimensionLabels(built.ctx, "x", today)
  let items: { key: string; label: string; value: number | null; goal: number | null }[]
  if (built.ctx.prepared.aggregated) {
    items = built.points.map((point: Point) => {
      const cell = built.ctx.prepared.cells.find((entry) => entry.dims.x === point.x)
      const goal = cell?.values.goal ?? target
      return { key: point.x, label: labels.short(point.x), value: numberOf(point.y0), goal }
    })
  } else {
    const row = built.ctx.prepared.rows[0]
    const at = (name?: string) => fields.findIndex((item) => item.name === name)
    items = row
      ? [
          {
            key: "one",
            label: labelOf(fields, measure),
            value: numberOf(row[at(measure?.field)]),
            goal: encoding.goal ? numberOf(row[at(encoding.goal.field)]) : target,
          },
        ]
      : []
  }
  if (!items.length) return <Empty />
  const top = Math.max(...items.flatMap((item) => [item.value ?? 0, item.goal ?? 0]), ...ranges, 0) * 1.08 || 1
  const percent = (value: number) => `${Math.max(0, Math.min(100, (value / top) * 100))}%`
  return (
    <ul className="flex flex-col gap-3">
      {items.map((item) => (
        <li
          key={item.key}
          className="grid grid-cols-[minmax(0,7rem)_1fr] items-center gap-3 sm:grid-cols-[minmax(0,10rem)_1fr]"
        >
          <span className="truncate text-xs text-muted-foreground" title={item.label}>
            {item.label}
          </span>
          <div className="flex flex-col gap-1">
            <div
              className="relative h-5 overflow-hidden rounded-[4px] bg-muted"
              role="img"
              aria-label={`${item.label}: ${measureText(spec, def, item.value)}${goalText(item.goal)}`}
            >
              {ranges.map((range, index) => (
                <span
                  key={range}
                  className="absolute inset-y-0 left-0"
                  style={{
                    width: percent(range),
                    background: "var(--chart-muted)",
                    opacity: 0.25 + (ranges.length - index) * 0.12,
                    zIndex: ranges.length - index,
                  }}
                />
              ))}
              {item.value !== null && (
                <span
                  className="absolute inset-y-1 left-0 z-10 rounded-r-[4px]"
                  style={{ width: percent(item.value), background: tokenColor("series-1") }}
                />
              )}
              {item.goal !== null && <span className={cn(
                "absolute inset-y-0 z-20 w-0.5 bg-foreground",
              )} style={{ left: percent(item.goal) }} />}
            </div>
            <span className="text-[11px] text-muted-foreground tabular-nums">
              <span className="font-medium text-foreground">{measureText(spec, def, item.value)}</span>
              {item.goal !== null && <> · mục tiêu {measureText(spec, def, item.goal)}</>}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}

// One row per series with its own small trend, so many series stay readable without a legend.
export function SparklineTableRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const measure = spec.encoding?.y?.[0]
  const def = { field: fieldOf(fields, measure), measure }
  const labels = dimensionLabels(built.ctx, "x", today)
  const seriesField = spec.encoding?.series?.field
  const position = fields.findIndex((item) => item.name === seriesField)
  const order = [...seriesColors(rows.map((row) => categoryKey(row[position]))).keys()]
  const bars = spec.options?.sparkline === "bar"
  const showLast = spec.options?.show_last !== false
  const lines = order
    .map((name) => ({
      name,
      points: built.ctx.prepared.x_values.map((x) => {
        const cell = built.ctx.prepared.cells.find((entry) => entry.dims.x === x && entry.dims.series === name)
        const value = cell?.values.y0 ?? null
        return { x, value, text: measureText(spec, def, value) }
      }),
    }))
    .filter((line) => line.points.some((point) => point.value !== null))
  if (!lines.length) return <Empty />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th className="py-1 pr-3 font-medium">{dimensionTitle(built.ctx, "series")}</th>
            <th className="py-1 pr-3 font-medium">
              {labels.short(built.ctx.prepared.x_values[0] ?? "")} –{" "}
              {labels.short(built.ctx.prepared.x_values.at(-1) ?? "")}
            </th>
            {showLast && <th className="py-1 text-right font-medium">Mới nhất</th>}
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => {
            const last = [...line.points].reverse().find((point) => point.value !== null)
            return (
              <tr key={line.name} className="border-t">
                <td className="max-w-40 truncate py-1 pr-3">{line.name}</td>
                <td className="w-1/2 min-w-28 py-1 pr-3">
                  {bars ? (
                    <BarChart
                      responsive
                      style={{ width: "100%", height: 32 }}
                      data={line.points}
                      margin={{ top: 2, right: 0, bottom: 0, left: 0 }}
                    >
                      <Bar
                        dataKey="value"
                        fill={tokenColor("series-1")}
                        radius={[2, 2, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  ) : (
                    <Spark points={line.points} color={tokenColor("series-1")} label={labels.long} />
                  )}
                </td>
                {showLast && <td className="py-1 text-right tabular-nums">{last?.text ?? "—"}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function TableRenderer({ spec, fields, rows }: RendererProps) {
  const columns = Array.isArray(spec.options?.columns) ? (spec.options.columns as string[]) : undefined
  const heat = typeof spec.options?.heat === "string" ? spec.options.heat : null
  return <ResultTable fields={fields} rows={rows} label={spec.title ?? "Kết quả"} columns={columns} heat={heat} />
}
