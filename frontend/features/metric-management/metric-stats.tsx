"use client"

import Link from "next/link"
import { ArrowRightIcon, CircleXIcon, SigmaIcon } from "lucide-react"

import { Coverage, RankList } from "@/components/stat-bars"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { useBusinessModel } from "../business-model/api"
import { useMetrics } from "./api"

const TOP = 8

export function MetricStatsCard({ connectionId }: { connectionId: string }) {
  const { data: model, error: modelError } = useBusinessModel(connectionId)
  const { data: metrics, error: metricsError } = useMetrics(connectionId)
  const error = modelError ?? metricsError
  const base = `/connections/${connectionId}`

  const tables = new Map(model?.tables.map((table) => [table.table_id, table]))
  const perTable = new Map<string, number>()
  for (const metric of metrics ?? []) {
    if (metric.table_id && metric.is_active && tables.has(metric.table_id)) {
      perTable.set(metric.table_id, (perTable.get(metric.table_id) ?? 0) + 1)
    }
  }
  const top = [...perTable].sort(([, a], [, b]) => b - a).slice(0, TOP)

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Bảng đã có metric</CardTitle>
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`${base}/metrics`}>
              Mở metric
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        {error ? (
          <Alert variant="destructive">
            <CircleXIcon />
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ) : !model || !metrics ? (
          <Skeleton className="h-56" />
        ) : (
          <>
            <Coverage label="Bảng" unit="bảng" doneLabel="đã có metric" done={perTable.size} total={model.tables.length} large />
            <div className="flex flex-1 flex-col gap-2 border-t pt-4">
              <h3 className="text-sm font-medium">Top {TOP} bảng nhiều metric nhất</h3>
              {top.length ? (
                <RankList
                  unit="metric"
                  items={top.map(([id, count]) => {
                    const table = tables.get(id)!
                    return {
                      id,
                      label: table.display_name,
                      title: `${table.schema_name}.${table.table_name}`,
                      value: count,
                      href: `${base}/metrics?table=${id}`,
                    }
                  })}
                />
              ) : (
                <Empty className="flex-1 p-4">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <SigmaIcon />
                    </EmptyMedia>
                    <EmptyTitle>Chưa có metric</EmptyTitle>
                    <EmptyDescription>Định nghĩa con số dùng chung như Tổng doanh thu, hoặc lấy metric từ Superset.</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Button size="sm" variant="outline" asChild>
                      <Link href={`${base}/metrics`}>Thêm metric</Link>
                    </Button>
                  </EmptyContent>
                </Empty>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
