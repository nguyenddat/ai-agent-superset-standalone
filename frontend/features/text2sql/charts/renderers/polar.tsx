"use client"

import { useMemo } from "react"

import {
  Cell,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  RadialBar,
  RadialBarChart,
  Tooltip,
  type TooltipContentProps,
} from "recharts"

import { cn } from "@/lib/utils"

import { buildChartData, categoryKey, numberOf, seriesColors, type Point } from "../data"
import { viNumber } from "../format"
import { tokenColor } from "../palette"
import type { PaletteToken } from "../spec"
import {
  AXIS_TICK,
  axisText,
  chartHeight,
  dimensionLabels,
  Empty,
  measureText,
  TipBox,
  useToday,
  ValueTip,
  WithLegend,
  type LegendItem,
  type RendererProps,
} from "./common"

// Slices are entities: their colours follow the order they first appear in the rows; "Khác" is always muted.
function sliceColors(props: RendererProps, keys: string[], other: string | null): Map<string, PaletteToken> {
  const position = props.fields.findIndex((item) => item.name === props.spec.encoding?.x?.field)
  const all = position >= 0 ? props.rows.map((row) => categoryKey(row[position])) : keys
  const colors = seriesColors([...all, ...keys].filter((key) => key !== other), props.spec.colors?.assign)
  if (other) colors.set(other, "muted")
  return colors
}

function useSlices(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const first = built.series[0]
  const labels = dimensionLabels(built.ctx, "x", today)
  const slices = built.points
    .map((point: Point) => ({
      key: point.x,
      label: labels.short(point.x),
      long: labels.long(point.x),
      value: numberOf(point[first?.key ?? "y0"]),
    }))
    .filter((item): item is { key: string; label: string; long: string; value: number } => item.value !== null)
  const colors = sliceColors(props, slices.map((item) => item.key), built.ctx.prepared.other)
  return { built, first, slices, colors }
}

export function PieRenderer(props: RendererProps) {
  const { spec } = props
  const { first, slices, colors } = useSlices(props)
  if (!slices.length) return <Empty />
  const total = slices.reduce((sum, item) => sum + item.value, 0)
  const percent = spec.options?.show_percent !== false
  const height = chartHeight(props, 260)
  const items: LegendItem[] = slices.map((item) => ({
    key: item.key,
    label: percent && total ? `${item.label} · ${viNumber((item.value / total) * 100, 1)}%` : item.label,
    color: colors.get(item.key) ?? "series-1",
  }))
  const donut = spec.type === "donut"
  return (
    <WithLegend
      spec={{ ...spec, legend: { show: "show", position: spec.legend?.position ?? "right" } }}
      items={props.compact ? [] : items}
    >
      <div className="relative">
        <PieChart responsive style={{ width: "100%", height }} accessibilityLayer>
          <Tooltip
            content={({ active, payload }: TooltipContentProps) => {
              const item = payload?.[0]?.payload as (typeof slices)[number] | undefined
              if (!active || !item) return null
              const share = total ? ` (${viNumber((item.value / total) * 100, 1)}%)` : ""
              const value = `${measureText(spec, first, item.value)}${share}`
              return <TipBox title={item.long} rows={[{ key: "v", label: first?.label ?? "", value }]} />
            }}
          />
          <Pie
            data={slices}
            dataKey="value"
            nameKey="label"
            innerRadius={donut ? "58%" : 0}
            outerRadius="88%"
            paddingAngle={slices.length > 1 ? 1 : 0}
            stroke="var(--card)"
            strokeWidth={2}
            isAnimationActive={false}
          >
            {slices.map((item) => (
              <Cell key={item.key} fill={tokenColor(colors.get(item.key))} />
            ))}
          </Pie>
        </PieChart>
        {donut && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            <span className="text-xs text-muted-foreground">Tổng</span>
            <span className="text-base font-semibold tabular-nums">{measureText(spec, first, total)}</span>
          </div>
        )}
      </div>
    </WithLegend>
  )
}

export function RadialBarRenderer(props: RendererProps) {
  const { spec } = props
  const { first, slices, colors } = useSlices(props)
  if (!slices.length) return <Empty />
  const data = slices.map((item) => ({ ...item, fill: tokenColor(colors.get(item.key)) }))
  const items: LegendItem[] = slices.map((item) => ({
    key: item.key,
    label: `${item.label}: ${measureText(spec, first, item.value)}`,
    color: colors.get(item.key) ?? "series-1",
  }))
  return (
    <WithLegend
      spec={{ ...spec, legend: { show: "show", position: spec.legend?.position ?? "right" } }}
      items={props.compact ? [] : items}
    >
      <RadialBarChart
        responsive
        style={{ width: "100%", height: chartHeight(props, 260) }}
        data={data}
        innerRadius="22%"
        outerRadius="95%"
        startAngle={90}
        endAngle={-270}
        barSize={12}
        accessibilityLayer
      >
        <PolarAngleAxis type="number" domain={[0, Math.max(...slices.map((item) => item.value))]} tick={false} />
        <RadialBar dataKey="value" background={{ fill: "var(--muted)" }} cornerRadius={6} isAnimationActive={false} />
        <Tooltip
          content={({ active, payload }: TooltipContentProps) => {
            const item = payload?.[0]?.payload as (typeof slices)[number] | undefined
            if (!active || !item) return null
            return <ValueTip title={item.long} spec={spec} def={first} value={item.value} />
          }}
        />
      </RadialBarChart>
    </WithLegend>
  )
}

export function RadarRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const today = useToday()
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const { series, points } = built
  if (!points.length || !series.length) return <Empty />
  const labels = dimensionLabels(built.ctx, "x", today)
  const fill = spec.options?.fill !== false
  const items: LegendItem[] = series.map((def) => ({ key: def.key, label: def.label, color: def.color, shape: "line" }))
  return (
    <WithLegend spec={spec} items={props.compact ? [] : items}>
      <RadarChart
        responsive
        style={{ width: "100%", height: chartHeight(props, 300) }}
        data={points}
        outerRadius="72%"
        accessibilityLayer
      >
        <PolarGrid stroke="var(--border)" />
        <PolarAngleAxis dataKey="x" tick={AXIS_TICK} tickFormatter={(key: string) => labels.short(key)} />
        <PolarRadiusAxis
          tick={{ ...AXIS_TICK, fontSize: 10 }}
          axisLine={false}
          tickFormatter={(tick: number) => axisText(spec, series[0], tick)}
        />
        <Tooltip
          content={({ active, payload }: TooltipContentProps) => {
            const point = payload?.[0]?.payload as Point | undefined
            if (!active || !point) return null
            return (
              <TipBox
                title={labels.long(point.x)}
                rows={series.map((def) => ({
                  key: def.key,
                  label: def.label,
                  value: measureText(spec, def, point[def.key]),
                  color: tokenColor(def.color),
                }))}
              />
            )
          }}
        />
        {series.map((def) => (
          <Radar
            key={def.key}
            dataKey={def.key}
            name={def.label}
            stroke={tokenColor(def.color)}
            strokeWidth={2}
            fill={tokenColor(def.color)}
            fillOpacity={fill ? 0.12 : 0}
            dot={{ r: 3, fill: tokenColor(def.color) }}
            isAnimationActive={false}
          />
        ))}
      </RadarChart>
    </WithLegend>
  )
}

// Funnel stages keep the row order; each stage is centred, its width proportional to the first stage.
export function FunnelRenderer(props: RendererProps) {
  const { spec } = props
  const { first, slices } = useSlices(props)
  if (!slices.length) return <Empty />
  const top = Math.max(...slices.map((item) => item.value), 0) || 1
  const conversion = spec.options?.show_conversion !== false
  return (
    <ol className="flex flex-col gap-1.5" aria-label="Phễu">
      {slices.map((item, index) => {
        const width = Math.max(4, (item.value / top) * 100)
        const previous = index > 0 ? slices[index - 1].value : null
        const rate = previous ? (item.value / previous) * 100 : null
        return (
          <li key={item.key} className="flex flex-col gap-0.5">
            {conversion && rate !== null && (
              <span className={cn(
                "text-center text-[11px] text-muted-foreground",
              )}>↓ {viNumber(rate, 1)}% từ bước trước</span>
            )}
            <div className="grid grid-cols-[minmax(0,7rem)_1fr] items-center gap-2 sm:grid-cols-[minmax(0,10rem)_1fr]">
              <span className="truncate text-xs text-muted-foreground" title={item.long}>
                {item.label}
              </span>
              <div className="flex justify-center">
                <div
                  className={cn(
                    "flex h-7 items-center justify-center rounded-md text-xs font-medium",
                    "tabular-nums text-white",
                  )}
                  style={{
                    width: `${width}%`,
                    background: tokenColor("series-1"),
                    opacity: 1 - index * (0.5 / slices.length),
                  }}
                  title={`${item.long}: ${measureText(spec, first, item.value)}`}
                >
                  <span className={cn(
                    "truncate px-1 mix-blend-normal [text-shadow:0_0_2px_rgb(0_0_0/0.45)]",
                  )}>{measureText(spec, first, item.value)}</span>
                </div>
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
