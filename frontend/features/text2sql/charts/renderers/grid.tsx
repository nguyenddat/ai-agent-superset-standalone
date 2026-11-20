"use client"

import { useMemo } from "react"

import { buildChartData, heatGrid, numberOf } from "../data"
import { isoDay, parseDay } from "../format"
import { scaleColor } from "../palette"
import {
  colorMeasure,
  dimensionLabels,
  dimensionTitle,
  Empty,
  measureText,
  useToday,
  type RendererProps,
} from "./common"

type ScaleProps = {
  min: number
  max: number
  text: (value: number) => string
  scheme?: string
  midpoint?: number | null
}

function Scale({ min, max, text, scheme, midpoint }: ScaleProps) {
  const kind = scheme === "diverging" ? "diverging" : "sequential"
  const stops = [0, 0.25, 0.5, 0.75, 1].map((ratio) => scaleColor(kind, min + (max - min) * ratio, min, max, midpoint))
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted-foreground" aria-hidden>
      <span className="tabular-nums">{text(min)}</span>
      <span
        className="h-2 w-28 rounded-full"
        style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }}
      />
      <span className="tabular-nums">{text(max)}</span>
    </div>
  )
}

// A grid of cells, each a focusable button whose label reads the value, so the colour is never the only cue.
export function HeatmapRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const grid = heatGrid(built.ctx.prepared.cells, built.ctx.prepared.x_values)
  if (!grid.cells.length) return <Empty />
  const xLabels = dimensionLabels(built.ctx, "x", today)
  const rowLabels = dimensionLabels(built.ctx, "row", today)
  const def = colorMeasure(spec, fields)
  const values = grid.cells.map((cell) => cell.value).filter((value): value is number => value !== null)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const scheme = spec.colors?.scheme === "diverging" ? "diverging" : "sequential"
  const midpoint = numberOf(spec.options?.midpoint)
  const lookup = new Map(grid.cells.map((cell) => [`${cell.row}\u0001${cell.x}`, cell.value]))
  const timed = rowLabels.field?.type === "date" || rowLabels.field?.type === "datetime"
  const rowsOrder = [...grid.rows].sort((a, b) => (timed ? (a < b ? -1 : 1) : 0))
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-[11px]">
          <caption className="sr-only">
            {dimensionTitle(built.ctx, "row")} × {dimensionTitle(built.ctx, "x")}
          </caption>
          <thead>
            <tr>
              <th />
              {grid.xs.map((x) => (
                <th
                  key={x}
                  scope="col"
                  className="max-w-16 truncate px-0.5 font-normal text-muted-foreground"
                  title={xLabels.long(x)}
                >
                  {xLabels.short(x)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rowsOrder.map((row) => (
              <tr key={row}>
                <th
                  scope="row"
                  className="max-w-32 truncate pr-2 text-left font-normal text-muted-foreground"
                  title={rowLabels.long(row)}
                >
                  {rowLabels.short(row)}
                </th>
                {grid.xs.map((x) => {
                  const value = lookup.get(`${row}\u0001${x}`) ?? null
                  const shown = value === null ? "không có" : measureText(spec, def, value)
                  const label = `${rowLabels.long(row)}, ${xLabels.long(x)}: ${shown}`
                  return (
                    <td key={x} className="p-0">
                      <div
                        tabIndex={0}
                        role="img"
                        aria-label={label}
                        title={label}
                        className="h-6 min-w-6 rounded-[3px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        style={{ background: scaleColor(scheme, value, min, max, midpoint) }}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Scale min={min} max={max} text={(value) => measureText(spec, def, value)} scheme={scheme} midpoint={midpoint} />
    </div>
  )
}

const WEEKDAY_SHORT = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]

export function CalendarHeatmapRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const def = colorMeasure(spec, fields)
  const values = new Map<string, number | null>()
  for (const cell of built.ctx.prepared.cells) values.set(cell.dims.x.slice(0, 10), cell.values.color ?? null)
  const days = [...values.keys()].filter((key) => parseDay(key)).sort()
  if (!days.length) return <Empty />
  const numbers = [...values.values()].filter((value): value is number => value !== null)
  const min = Math.min(...numbers)
  const max = Math.max(...numbers)
  const scheme = spec.colors?.scheme === "diverging" ? "diverging" : "sequential"
  const midpoint = numberOf(spec.options?.midpoint)
  const first = parseDay(days[0])!
  const start = new Date(Date.UTC(first.year, first.month - 1, first.day))
  start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7))
  const last = parseDay(days.at(-1)!)!
  const end = Date.UTC(last.year, last.month - 1, last.day)
  const weeks: string[][] = []
  for (let cursor = new Date(start); cursor.getTime() <= end; cursor.setUTCDate(cursor.getUTCDate() + 7)) {
    weeks.push(
      Array.from({ length: 7 }, (_, offset) => {
        const day = new Date(cursor.getTime() + offset * 86400000)
        return isoDay({ year: day.getUTCFullYear(), month: day.getUTCMonth() + 1, day: day.getUTCDate() })
      }),
    )
  }
  const labels = dimensionLabels(built.ctx, "x", today)
  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <div className="inline-grid grid-flow-col gap-0.5" style={{ gridTemplateRows: "auto repeat(7, 1rem)" }}>
          <span />
          {WEEKDAY_SHORT.map((name) => (
            <span key={name} className="pr-1 text-[10px] leading-4 text-muted-foreground">
              {name}
            </span>
          ))}
          {weeks.map((week, index) => {
            const monthStart = index === 0 ? week[6] : week.find((day) => day.slice(8) === "01")
            return (
            <div key={week[0]} className="contents">
              <span className="text-[10px] leading-4 whitespace-nowrap text-muted-foreground">
                {monthStart ? `Th${Number(monthStart.slice(5, 7))}` : ""}
              </span>
              {week.map((day) => {
                const has = values.has(day)
                const value = values.get(day) ?? null
                const shown = has && value !== null ? measureText(spec, def, value) : "không có dữ liệu"
                const label = `${labels.long(day)}: ${shown}`
                return (
                  <div
                    key={day}
                    tabIndex={has ? 0 : -1}
                    role="img"
                    aria-label={label}
                    title={label}
                    className="size-4 rounded-[3px] outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    style={{
                      background: has ? scaleColor(scheme, value, min, max, midpoint) : "transparent",
                      boxShadow: has ? undefined : "inset 0 0 0 1px var(--border)",
                    }}
                  />
                )
              })}
            </div>
            )
          })}
        </div>
      </div>
      <Scale min={min} max={max} text={(value) => measureText(spec, def, value)} scheme={scheme} midpoint={midpoint} />
    </div>
  )
}
