"use client"

import { useState } from "react"
import { CircleXIcon, RefreshCwIcon } from "lucide-react"
import { Bar, BarChart, CartesianGrid, LabelList, XAxis, YAxis } from "recharts"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"

import { ModelStatsCard } from "../../business-model/model-stats"
import { DictionaryCoverageCard, DictionaryRankCards } from "../../data-dictionary/dictionary-stats"
import { LineageStatsCard } from "../../data-lineage/lineage-stats"
import { MetricStatsCard } from "../../metric-management/metric-stats"

import { useConnection, useSchemaTables } from "../api"
import { dateFormat, StatusBadge } from "../connection-format"
import { syncWithToast } from "../sync-with-toast"
import type { DatabaseTable } from "../types"
import { useConnectionId } from "./connection-layout"

const chartConfig = {
  tables: { label: "Bảng", color: "var(--chart-1)" },
  views: { label: "View", color: "var(--chart-2)" },
} satisfies ChartConfig

const isView = (table: DatabaseTable) => table.table_type.toLowerCase().includes("view")

function InfoRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2 last:border-b-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate text-right">{children}</dd>
    </div>
  )
}

export function ConnectionOverview() {
  const id = useConnectionId()
  const { data: connection } = useConnection(id)
  const { data: groups, error } = useSchemaTables(id)
  const [syncing, setSyncing] = useState(false)

  const rows = (groups ?? []).map(({ schema, tables }) => ({
    schema: schema.name,
    tables: tables.filter((t) => !isView(t)).length,
    views: tables.filter(isView).length,
  }))
  const total = rows.reduce((sum, r) => sum + r.tables + r.views, 0)
  const series = (["tables", "views"] as const).filter((key) => rows.some((r) => r[key] > 0))
  const lastSynced = groups
    ?.map((g) => g.schema.last_synced_at)
    .sort()
    .at(-1)

  async function handleSync() {
    if (!connection) return
    setSyncing(true)
    await syncWithToast(connection)
    setSyncing(false)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Card size="sm">
          <CardHeader>
            <CardTitle>Thông tin kết nối</CardTitle>
            <CardAction>{connection && <StatusBadge active={connection.is_active} />}</CardAction>
          </CardHeader>
          <CardContent>
            {connection ? (
              <dl className="text-sm">
                <InfoRow label="Loại database">{connection.dialect}</InfoRow>
                <InfoRow label="Driver">{connection.driver ?? "—"}</InfoRow>
                <InfoRow label="Tạo lúc">{dateFormat.format(new Date(connection.created_at))}</InfoRow>
                <InfoRow label="Cập nhật lúc">{dateFormat.format(new Date(connection.updated_at))}</InfoRow>
              </dl>
            ) : (
              <Skeleton className="h-36" />
            )}
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
            <CardDescription>
              {lastSynced ? `Đồng bộ lần cuối ${dateFormat.format(new Date(lastSynced))}.` : "Chưa đồng bộ metadata."}
            </CardDescription>
            {groups && groups.length > 0 && (
              <CardAction>
                <Badge variant="secondary" className="font-mono">
                  {rows.length} schema · {total} đối tượng
                </Badge>
              </CardAction>
            )}
          </CardHeader>
          <CardContent className="flex-1">
            {error ? (
              <Alert variant="destructive">
                <CircleXIcon />
                <AlertDescription>{error.message}</AlertDescription>
              </Alert>
            ) : !groups ? (
              <Skeleton className="h-44" />
            ) : groups.length === 0 ? (
              <Empty className="p-4">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <RefreshCwIcon />
                  </EmptyMedia>
                  <EmptyTitle>Chưa có dữ liệu metadata</EmptyTitle>
                  <EmptyDescription>Đồng bộ để đọc schema, bảng và view từ database nguồn.</EmptyDescription>
                </EmptyHeader>
                {connection?.is_active && (
                  <EmptyContent>
                    <Button disabled={syncing} onClick={handleSync}>
                      {syncing ? <Spinner data-icon="inline-start" /> : <RefreshCwIcon data-icon="inline-start" />}
                      Đồng bộ ngay
                    </Button>
                  </EmptyContent>
                )}
              </Empty>
            ) : (
              <ChartContainer config={chartConfig} className="h-52 w-full">
                <BarChart data={rows} margin={{ top: 20, left: -16, right: 8 }} barGap={0}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="schema" tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  {series.map((key) => (
                    <Bar key={key} dataKey={key} fill={`var(--color-${key})`} radius={[4, 4, 0, 0]} maxBarSize={32}>
                      <LabelList dataKey={key} position="top" className="fill-foreground font-mono text-xs" />
                    </Bar>
                  ))}
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>
        <DictionaryCoverageCard connectionId={id} />
      </div>
      <DictionaryRankCards connectionId={id} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <ModelStatsCard connectionId={id} />
        <LineageStatsCard connectionId={id} />
        <MetricStatsCard connectionId={id} />
      </div>
    </div>
  )
}
