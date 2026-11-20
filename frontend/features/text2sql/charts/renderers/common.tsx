"use client"

import { useMemo, type ReactNode } from "react"

import { cn } from "@/lib/utils"

import type { Context, Row, SeriesDef } from "../data"
import { formatAxis, formatMeasure, keyText, todayIso } from "../format"
import { tokenColor } from "../palette"
import type { ChartField, ChartSpec, LabelMode, Measure, NumberFormat, PaletteToken } from "../spec"

export type RendererProps = {
  spec: ChartSpec
  fields: ChartField[]
  rows: Row[]
  // Smaller charts (facets, sparklines) leave out titles and legends.
  compact?: boolean
  height?: number
}

export const useToday = () => useMemo(() => todayIso(), [])

// Recessive axes and grid: thin, light, text in muted ink.
export const AXIS_TICK = { fontSize: 11, fill: "var(--muted-foreground)" }
export const AXIS_LINE = { stroke: "var(--border)" }
export const GRID = { stroke: "var(--border)", strokeDasharray: "0", vertical: false }

export const numberFormatOf = (spec: ChartSpec, measure?: Measure | null): NumberFormat | null | undefined =>
  measure?.format ?? spec.format?.number

export function measureText(spec: ChartSpec, def: Pick<SeriesDef, "field" | "measure"> | undefined, value: unknown) {
  return formatMeasure(value, def?.field, numberFormatOf(spec, def?.measure))
}

export function axisText(spec: ChartSpec, def: Pick<SeriesDef, "field" | "measure"> | undefined, value: unknown) {
  return formatAxis(value, def?.field, numberFormatOf(spec, def?.measure))
}

// How a dimension key reads on an axis (short) and in a tooltip (long, with the weekday).
export function dimensionLabels(ctx: Context, role: "x" | "row" | "series" | "source" | "target", today: string) {
  const ref = ctx.spec.encoding?.[role] as { field: string; time_unit?: ChartField["time_unit"] } | null | undefined
  const field = ref ? ctx.byName.get(ref.field) : undefined
  const style = ctx.spec.format?.date?.style
  const other = ctx.prepared.other
  return {
    field,
    short: (key: string) => (key === other ? key : keyText(key, field, today, ref?.time_unit, style)),
    long: (key: string) => (key === other ? key : keyText(key, field, today, ref?.time_unit, style, true)),
  }
}

// The measure a single-measure chart reads from its first y or its color role, with the column behind it.
export const yMeasure = (spec: ChartSpec, fields: ChartField[]) => ({
  field: fields.find((item) => item.name === spec.encoding?.y?.[0]?.field),
  measure: spec.encoding?.y?.[0],
})

export const colorMeasure = (spec: ChartSpec, fields: ChartField[]) => ({
  field: fields.find((item) => item.name === spec.encoding?.color?.field),
  measure: spec.encoding?.color ?? undefined,
})

export const dimensionTitle = (ctx: Context, role: "x" | "row" | "series") => {
  const ref = ctx.spec.encoding?.[role] as { field: string; label?: string | null } | null | undefined
  return ref ? ref.label || ctx.byName.get(ref.field)?.label || ref.field : ""
}

// Selective direct labels: never a number on every point unless asked for.
type AutoLabels = "all" | "endpoints" | "none"

export function labelIndexes(mode: LabelMode | undefined, values: (number | null | undefined)[], auto: AutoLabels) {
  const chosen = mode === undefined || mode === "auto" ? (values.length > 12 && auto === "all" ? "none" : auto) : mode
  const indexes = new Set<number>()
  const present = values.map((value, index) => [value, index] as const).filter(([value]) => typeof value === "number")
  if (chosen === "all") present.forEach(([, index]) => indexes.add(index))
  if (chosen === "endpoints" && present.length) {
    indexes.add(present[0][1])
    indexes.add(present.at(-1)![1])
  }
  if (chosen === "extremes" && present.length) {
    const sorted = [...present].sort((a, b) => (a[0] as number) - (b[0] as number))
    indexes.add(sorted[0][1])
    indexes.add(sorted.at(-1)![1])
  }
  return indexes
}

const SWATCH = { line: "h-0.5 w-3 rounded-full", dot: "size-2 rounded-full", square: "size-2.5 rounded-[3px]" }

export function Swatch({ color, shape = "square" }: { color: string; shape?: "square" | "line" | "dot" }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block shrink-0", SWATCH[shape])}
      style={{ background: color }}
    />
  )
}

export type LegendItem = { key: string; label: string; color: PaletteToken | string; shape?: "square" | "line" | "dot" }

const colorOf = (color: PaletteToken | string) =>
  color.startsWith("series-") || color === "muted" ? tokenColor(color as PaletteToken) : color

// A legend whenever there are two or more series; the text stays in text colours, the swatch carries identity.
export function ChartLegend({ items, spec, className }: { items: LegendItem[]; spec: ChartSpec; className?: string }) {
  const show = spec.legend?.show ?? "auto"
  if (show === "hide" || (show === "auto" && items.length < 2) || !items.length) return null
  return (
    <ul
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground", className)}
      aria-label="Chú giải"
    >
      {items.map((item) => (
        <li key={item.key} className="flex min-w-0 items-center gap-1.5">
          <Swatch color={colorOf(item.color)} shape={item.shape} />
          <span className="truncate">{item.label}</span>
        </li>
      ))}
    </ul>
  )
}

export function legendSide(spec: ChartSpec) {
  return spec.legend?.position ?? "bottom"
}

export function WithLegend({ spec, items, children }: { spec: ChartSpec; items: LegendItem[]; children: ReactNode }) {
  const side = legendSide(spec)
  const stacked = side === "right" ? "flex-col items-start" : undefined
  const legend = <ChartLegend items={items} spec={spec} className={stacked} />
  if (side === "right") {
    return (
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="min-w-0 flex-1">{children}</div>
        <div className="sm:w-40 sm:shrink-0 sm:pt-2">{legend}</div>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      {side === "top" && legend}
      {children}
      {side === "bottom" && legend}
    </div>
  )
}

export type TipRow = { key: string; label: string; value: string; color?: string; shape?: "square" | "line" | "dot" }

export function TipBox({ title, rows, footer }: { title?: ReactNode; rows: TipRow[]; footer?: ReactNode }) {
  return (
    <div className={cn(
      "min-w-36 max-w-72 rounded-lg border bg-popover px-2.5 py-1.5 text-xs",
      "text-popover-foreground shadow-md",
    )}>
      {title !== undefined && <div className="mb-1 font-medium">{title}</div>}
      <ul className="flex flex-col gap-0.5">
        {rows.map((row) => (
          <li key={row.key} className="flex items-center gap-2">
            {row.color && <Swatch color={row.color} shape={row.shape} />}
            <span className="min-w-0 flex-1 truncate text-muted-foreground">{row.label}</span>
            <span className="font-medium tabular-nums">{row.value}</span>
          </li>
        ))}
      </ul>
      {footer && <div className="mt-1 text-muted-foreground">{footer}</div>}
    </div>
  )
}

type MeasureDef = Pick<SeriesDef, "field" | "measure">

// A tooltip with one value: the measure's label and the formatted number.
type ValueTipProps = { title?: ReactNode; spec: ChartSpec; def?: MeasureDef; value: unknown }

export function ValueTip({ title, spec, def, value }: ValueTipProps) {
  const label = (def as Partial<SeriesDef> | undefined)?.label || def?.measure?.label || def?.field?.label || ""
  return <TipBox title={title} rows={[{ key: "v", label, value: measureText(spec, def, value) }]} />
}

export const chartHeight = (props: RendererProps, fallback = 280) => props.height ?? (props.compact ? 180 : fallback)

export function Empty({ text = "Không có dữ liệu để vẽ." }: { text?: string }) {
  return <p className="py-6 text-center text-sm text-muted-foreground">{text}</p>
}
