"use client"

import Link from "next/link"
import { ArrowRightIcon, CircleXIcon, WorkflowIcon } from "lucide-react"

import { Coverage, RankList } from "@/components/stat-bars"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { useBusinessModel } from "../business-model/api"
import { useLineageGraph } from "./api"
import { downstreamCounts } from "./graph"

const TOP = 8

export function LineageStatsCard({ connectionId }: { connectionId: string }) {
  const { data: model, error: modelError } = useBusinessModel(connectionId)
  const { data: graph, error: graphError } = useLineageGraph(connectionId)
  const error = modelError ?? graphError
  const base = `/connections/${connectionId}`

  const tables = new Map(model?.tables.map((table) => [table.table_id, table]))
  const linked = new Set(
    graph?.edges.flatMap((edge) => [edge.source_table_id, edge.target_table_id]).filter((id) => tables.has(id)),
  )
  const impact = [...downstreamCounts(graph?.edges ?? [])]
    .filter(([id]) => tables.has(id))
    .sort(([, a], [, b]) => b.all - a.all || b.direct - a.direct)
    .slice(0, TOP)

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Bảng đã có dòng dữ liệu</CardTitle>
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`${base}/lineage`}>
              Mở dòng dữ liệu
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
        ) : !model || !graph ? (
          <Skeleton className="h-56" />
        ) : (
          <>
            <Coverage label="Bảng" unit="bảng" doneLabel="đã có dòng dữ liệu" done={linked.size} total={model.tables.length} large />
            <div className="flex flex-1 flex-col gap-2 border-t pt-4">
              <h3 className="text-sm font-medium">Top {TOP} bảng ảnh hưởng rộng nhất</h3>
              {impact.length ? (
                <RankList
                  unit="bảng"
                  items={impact.map(([id, count]) => {
                    const table = tables.get(id)!
                    return {
                      id,
                      label: table.display_name,
                      title: `${table.schema_name}.${table.table_name} · ${count.direct} bảng nhận trực tiếp, ${count.all} bảng tính cả gián tiếp`,
                      value: count.all,
                      href: `${base}/lineage?table=${id}`,
                    }
                  })}
                />
              ) : (
                <Empty className="flex-1 p-4">
                  <EmptyHeader>
                    <EmptyMedia variant="icon">
                      <WorkflowIcon />
                    </EmptyMedia>
                    <EmptyTitle>Chưa có dòng dữ liệu</EmptyTitle>
                    <EmptyDescription>Khai báo bảng nào tạo ra bảng nào để biết sửa một bảng sẽ ảnh hưởng tới đâu.</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Button size="sm" variant="outline" asChild>
                      <Link href={`${base}/lineage`}>Khai báo phép biến đổi</Link>
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
