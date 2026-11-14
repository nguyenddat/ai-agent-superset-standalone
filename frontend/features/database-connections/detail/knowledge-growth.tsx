"use client"

import { CircleXIcon } from "lucide-react"
import { CartesianGrid, LabelList, Line, LineChart, XAxis, YAxis } from "recharts"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"

import { useRules } from "../../expert-rule-management/api"
import { useGlossary } from "../../glossary-management/api"
import { useMetrics } from "../../metric-management/api"

const SERIES = ["metrics", "terms", "rules"] as const
type Series = (typeof SERIES)[number]

const config = {
  metrics: { label: "Metric", color: "var(--chart-1)" },
  terms: { label: "Thuật ngữ", color: "var(--chart-2)" },
  rules: { label: "Quy tắc", color: "var(--chart-3)" },
} satisfies ChartConfig

const HOUR = 3_600_000
const DAY = 24 * HOUR
// Short histories are drawn by the hour, long ones by the week, so the line always has room to move.
const STEPS = [
  { size: HOUR, upTo: 2 * DAY, format: { hour: "2-digit", minute: "2-digit" } },
  { size: DAY, upTo: 120 * DAY, format: { day: "2-digit", month: "2-digit" } },
  { size: 7 * DAY, upTo: Infinity, format: { day: "2-digit", month: "2-digit", year: "2-digit" } },
] as const

// vi-VN writes a short date as "28-10"; the rest of the app writes "28/10".
const dateLabel = (format: Intl.DateTimeFormat) => (value: number) => format.format(value).replaceAll("-", "/")

type Point = { at: number } & Record<Series, number>

function cumulative(created: Record<Series, number[]>, now: number) {
  const first = Math.min(...SERIES.flatMap((key) => created[key]))
  const step = STEPS.find((candidate) => now - first <= candidate.upTo)!
  const start = Math.floor(first / step.size) * step.size
  const points: Point[] = []
  for (let at = start; at < now + step.size; at += step.size) {
    const end = Math.min(at + step.size, now)
    points.push({
      at: end,
      metrics: created.metrics.filter((time) => time <= end).length,
      terms: created.terms.filter((time) => time <= end).length,
      rules: created.rules.filter((time) => time <= end).length,
    })
  }
  return { points, label: dateLabel(new Intl.DateTimeFormat("vi-VN", step.format)), hourly: step.size === HOUR }
}

export function KnowledgeGrowthCard({ connectionId }: { connectionId: string }) {
  const { data: metrics, error: metricsError } = useMetrics(connectionId)
  const { data: terms, error: termsError } = useGlossary(connectionId)
  const { data: rules, error: rulesError } = useRules(connectionId)
  const error = metricsError ?? termsError ?? rulesError
  const ready = metrics && terms && rules

  const created: Record<Series, number[]> = {
    metrics: (metrics ?? []).map((metric) => Date.parse(metric.created_at)),
    terms: (terms ?? []).map((term) => Date.parse(term.created_at)),
    rules: (rules ?? []).map((rule) => Date.parse(rule.created_at)),
  }
  const total = SERIES.reduce((sum, key) => sum + created[key].length, 0)
  // Rendered on the client only, so reading the clock here does not risk a hydration mismatch.
  // eslint-disable-next-line react-hooks/purity
  const chart = ready && total ? cumulative(created, Date.now()) : null
  const last = chart ? chart.points.length - 1 : -1

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Kho tri thức cho AI theo thời gian</CardTitle>
        <CardDescription>
          Số metric, thuật ngữ và quy tắc đã tạo, cộng dồn{chart ? (chart.hourly ? " theo giờ" : " theo ngày") : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <Alert variant="destructive">
            <CircleXIcon />
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ) : !ready ? (
          <Skeleton className="h-64" />
        ) : !chart ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Chưa có metric, thuật ngữ hay quy tắc nào cho kết nối này.
          </p>
        ) : (
          <div className="flex flex-col gap-4 lg:flex-row">
            <dl className="grid grid-cols-3 gap-3 lg:w-44 lg:shrink-0 lg:grid-cols-1 lg:content-start">
              {SERIES.map((key) => (
                <div key={key} className="flex flex-col gap-0.5 border-l-2 pl-3" style={{ borderColor: config[key].color }}>
                  <dt className="text-sm text-muted-foreground">{config[key].label}</dt>
                  <dd className="text-2xl font-semibold tracking-tight">{created[key].length}</dd>
                </div>
              ))}
            </dl>
            <ChartContainer config={config} className="aspect-auto h-64 w-full min-w-0">
              <LineChart data={chart.points} margin={{ top: 12, right: 28, bottom: 0, left: -20 }}>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="at"
                  type="number"
                  scale="time"
                  domain={["dataMin", "dataMax"]}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={32}
                  tick={{ fontSize: 11 }}
                  tickFormatter={chart.label}
                />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 11 }} />
                <ChartTooltip
                  cursor={{ stroke: "var(--border)" }}
                  content={<ChartTooltipContent labelFormatter={(_, payload) => chart.label(payload?.[0]?.payload.at)} />}
                />
                <ChartLegend content={<ChartLegendContent />} itemSorter={null} />
                {SERIES.map((key) => (
                  <Line
                    key={key}
                    dataKey={key}
                    type="stepAfter"
                    stroke={`var(--color-${key})`}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
                    isAnimationActive={false}
                  >
                    <LabelList
                      dataKey={key}
                      content={({ index, x, y, value }) =>
                        index === last ? (
                          <text x={Number(x) + 6} y={Number(y) + 4} className="fill-foreground text-xs tabular-nums">
                            {value}
                          </text>
                        ) : null
                      }
                    />
                  </Line>
                ))}
              </LineChart>
            </ChartContainer>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
