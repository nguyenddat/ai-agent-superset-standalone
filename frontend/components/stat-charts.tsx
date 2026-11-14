"use client"

import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"

import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"

export type BarRow = { name: string; value: number }

const ROW = 28
const OTHER = "Khác"

/** One series ranked as horizontal bars, the tail past `limit` folded into "Khác". */
export function GroupBars({ title, unit, rows, limit = 6 }: { title: string; unit: string; rows: BarRow[]; limit?: number }) {
  const sorted = [...rows].sort((a, b) => b.value - a.value || a.name.localeCompare(b.name, "vi"))
  const shown =
    sorted.length > limit
      ? [...sorted.slice(0, limit - 1), { name: OTHER, value: sorted.slice(limit - 1).reduce((sum, row) => sum + row.value, 0) }]
      : sorted
  const config = { value: { label: unit, color: "var(--chart-1)" } } satisfies ChartConfig

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height: shown.length * ROW + 8 }}>
        <BarChart data={shown} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={6}>
          <XAxis type="number" hide allowDecimals={false} domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="name"
            width={112}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 12 }}
            tickFormatter={(value: string) => (value.length > 16 ? `${value.slice(0, 15)}…` : value)}
          />
          <ChartTooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltipContent hideIndicator />} />
          <Bar dataKey="value" fill="var(--color-value)" radius={[0, 4, 4, 0]} maxBarSize={16}>
            <LabelList dataKey="value" position="right" className="fill-foreground text-xs tabular-nums" />
          </Bar>
        </BarChart>
      </ChartContainer>
    </figure>
  )
}

/** One series as columns over a few named categories or days; every column carries its value. */
export function ColumnBars({
  title,
  unit,
  rows,
  height = 150,
  tickFormatter,
}: {
  title: string
  unit: string
  rows: BarRow[]
  height?: number
  tickFormatter?: (value: string) => string
}) {
  const config = { value: { label: unit, color: "var(--chart-1)" } } satisfies ChartConfig
  const labelled = rows.length <= 16

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height }}>
        <BarChart data={rows} margin={{ top: 18, right: 4, bottom: 0, left: -24 }} barCategoryGap={2}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            tick={{ fontSize: 11 }}
            tickFormatter={tickFormatter}
          />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
          <ChartTooltip
            cursor={{ fill: "var(--muted)" }}
            content={<ChartTooltipContent hideIndicator labelFormatter={(value) => (tickFormatter ? tickFormatter(String(value)) : value)} />}
          />
          <Bar dataKey="value" fill="var(--color-value)" radius={[4, 4, 0, 0]} maxBarSize={24}>
            {labelled ? (
              <LabelList
                dataKey="value"
                position="top"
                className="fill-foreground text-xs tabular-nums"
                formatter={(value: unknown) => (value ? String(value) : "")}
              />
            ) : null}
          </Bar>
        </BarChart>
      </ChartContainer>
    </figure>
  )
}
