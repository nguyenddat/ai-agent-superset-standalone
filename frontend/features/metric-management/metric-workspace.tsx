"use client"

import { useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  CircleXIcon,
  CloudDownloadIcon,
  LinkIcon,
  PlusIcon,
  SigmaIcon,
  TriangleAlertIcon,
  XIcon,
} from "lucide-react"

import { EmptyState } from "@/components/empty-state"
import { SearchInput } from "@/components/search-input"
import { SegmentedControl } from "@/components/segmented-control"
import { StatTile } from "@/components/stat-tile"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

import { useBusinessModel } from "../business-model/api"
import type { ModelTable } from "../business-model/types"
import { useConnectionId } from "../database-connections/detail/connection-layout"
import { useMetrics, useSupersetDatabases } from "./api"
import { metricTitle } from "./labels"
import { MetricDetail } from "./metric-detail"
import { MetricEditor } from "./metric-editor"
import { SupersetDialog } from "./superset-dialog"
import type { Metric, MetricOrigin } from "./types"

type OriginFilter = "all" | MetricOrigin
type Panel = { metricId: string | null; table: string | null; nonce: number }

const UNMATCHED = "__unmatched__"

export function MetricWorkspace() {
  const connectionId = useConnectionId()
  const model = useBusinessModel(connectionId)
  const metrics = useMetrics(connectionId)
  const error = model.error ?? metrics.error

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!model.data || !metrics.data) {
    return (
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((key) => (
            <Skeleton key={key} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }

  return <MetricList connectionId={connectionId} tables={model.data.tables} metrics={metrics.data} />
}

type Group = { id: string; table: ModelTable | undefined; metrics: Metric[] }

function MetricList({ connectionId, tables, metrics }: { connectionId: string; tables: ModelTable[]; metrics: Metric[] }) {
  const router = useRouter()
  // `?table=<id>` (from the overview) opens on that table's metrics.
  const requestedTable = useSearchParams().get("table")
  const { data: databases } = useSupersetDatabases()
  const [query, setQuery] = useState("")
  const [origin, setOrigin] = useState<OriginFilter>("all")
  const [tableFilter, setTableFilter] = useState<string | null>(requestedTable)
  const [panel, setPanel] = useState<Panel | null>(null)
  const [supersetOpen, setSupersetOpen] = useState(false)

  const byId = useMemo(() => new Map(tables.map((table) => [table.table_id, table])), [tables])
  const counts = {
    all: metrics.length,
    manual: metrics.filter((metric) => metric.origin === "manual").length,
    superset: metrics.filter((metric) => metric.origin === "superset").length,
  }
  const coveredTables = new Set(metrics.flatMap((metric) => (metric.table_id ? [metric.table_id] : []))).size

  const groups = useMemo(() => {
    const term = query.trim().toLowerCase()
    const shown = metrics.filter((metric) => {
      if (origin !== "all" && metric.origin !== origin) return false
      if (tableFilter && metric.table_id !== tableFilter) return false
      if (!term) return true
      const table = metric.table_id ? byId.get(metric.table_id) : undefined
      return [metric.name, metric.label, metric.expression, metric.description, table?.display_name, table?.table_name]
        .filter(Boolean)
        .some((text) => text!.toLowerCase().includes(term))
    })
    const map = new Map<string, Group>()
    for (const metric of shown) {
      const id = metric.table_id ?? UNMATCHED
      const group = map.get(id) ?? { id, table: metric.table_id ? byId.get(metric.table_id) : undefined, metrics: [] }
      group.metrics.push(metric)
      map.set(id, group)
    }
    return [...map.values()]
      .map((group) => ({
        ...group,
        metrics: group.metrics.sort(
          (a, b) => Number(b.is_active) - Number(a.is_active) || metricTitle(a).localeCompare(metricTitle(b)),
        ),
      }))
      .sort((a, b) =>
        a.id === UNMATCHED ? 1 : b.id === UNMATCHED ? -1 : (a.table?.display_name ?? "").localeCompare(b.table?.display_name ?? ""),
      )
  }, [metrics, query, origin, tableFilter, byId])

  const unlinked = databases?.filter((database) => !database.connection_id) ?? []
  const linkedHere = databases?.some((database) => database.connection_id === connectionId) ?? false
  const filtered = !!query.trim() || origin !== "all" || !!tableFilter
  const selected = panel?.metricId ? metrics.find((metric) => metric.id === panel.metricId) ?? null : null

  const openPanel = (metricId: string | null, table: string | null = null) =>
    setPanel({ metricId, table, nonce: Date.now() })
  const clearFilters = () => {
    setQuery("")
    setOrigin("all")
    setTableFilter(null)
    if (requestedTable) router.replace(`/connections/${connectionId}/metrics`)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Tổng metric" value={counts.all} />
        <StatTile label="Tự tạo" value={counts.manual} />
        <StatTile label="Từ Superset" value={counts.superset} />
        <StatTile label="Bảng đã có metric" value={coveredTables} total={tables.length} />
      </div>

      {databases && unlinked.length > 0 && !linkedHere ? (
        <Alert>
          <LinkIcon />
          <AlertTitle>Có {unlinked.length} database Superset chưa liên kết</AlertTitle>
          <AlertDescription>Liên kết database trỏ tới kết nối này để metric của nó hiện ở đây.</AlertDescription>
          <AlertAction>
            <Button size="sm" variant="outline" onClick={() => setSupersetOpen(true)}>
              Liên kết
            </Button>
          </AlertAction>
        </Alert>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          aria-label="Tìm metric"
          placeholder="Tìm theo tên, biểu thức, bảng"
          className="w-full sm:w-72"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={setQuery}
          shortcut="/"
        />
        <SegmentedControl
          label="Nguồn metric"
          size="sm"
          value={origin}
          onValueChange={(value) => setOrigin(value as OriginFilter)}
          options={[
            { value: "all", label: `Tất cả ${counts.all}` },
            { value: "manual", label: `Tự tạo ${counts.manual}` },
            { value: "superset", label: `Superset ${counts.superset}` },
          ]}
        />
        {tableFilter ? (
          <Badge variant="secondary" className="h-7 gap-1 pr-1">
            Bảng: {byId.get(tableFilter)?.display_name ?? "không rõ"}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Bỏ lọc theo bảng"
              onClick={() => {
                setTableFilter(null)
                if (requestedTable) router.replace(`/connections/${connectionId}/metrics`)
              }}
            >
              <XIcon />
            </Button>
          </Badge>
        ) : null}
        <div className="ml-auto flex gap-2">
          <Button variant="outline" onClick={() => setSupersetOpen(true)}>
            <CloudDownloadIcon data-icon="inline-start" />
            Superset
          </Button>
          <Button onClick={() => openPanel(null, tableFilter)}>
            <PlusIcon data-icon="inline-start" />
            Thêm metric
          </Button>
        </div>
      </div>

      <div className={cn("grid items-start gap-3", panel && "lg:grid-cols-[minmax(0,1fr)_32rem]")}>
        <div className="flex min-w-0 flex-col gap-3">
          {metrics.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="chart"
                title="Chưa có metric"
                description="Định nghĩa con số dùng chung như Tổng doanh thu hay Số khách hàng, hoặc lấy metric sẵn có từ Superset."
                action={
                  <Button onClick={() => openPanel(null)}>
                    <PlusIcon data-icon="inline-start" />
                    Thêm metric
                  </Button>
                }
                secondaryAction={{ label: "Lấy từ Superset", onAction: () => setSupersetOpen(true) }}
              />
            </div>
          ) : groups.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="search"
                title="Không có metric khớp"
                description={query.trim() ? `Không thấy metric nào khớp "${query.trim()}".` : "Không có metric nào khớp bộ lọc."}
                secondaryAction={filtered ? { label: "Xóa bộ lọc", onAction: clearFilters } : undefined}
              />
            </div>
          ) : (
            groups.map((group) => (
              <MetricGroup
                key={group.id}
                group={group}
                selectedId={panel?.metricId ?? null}
                onOpen={(id) => openPanel(id)}
                onCreate={group.table ? () => openPanel(null, group.id) : undefined}
              />
            ))
          )}
        </div>

        {panel ? (
          <div className="order-first overflow-hidden rounded-xl border lg:sticky lg:top-[4.5rem] lg:order-none lg:h-[calc(100svh-5.5rem)]">
            {selected?.origin === "superset" ? (
              <MetricDetail
                key={panel.nonce}
                metric={selected}
                table={selected.table_id ? byId.get(selected.table_id) : undefined}
                onClose={() => setPanel(null)}
              />
            ) : (
              <MetricEditor
                key={panel.nonce}
                connectionId={connectionId}
                tables={tables}
                metrics={metrics}
                metric={selected}
                initialTable={panel.table}
                onClose={() => setPanel(null)}
                onSaved={(saved) => setPanel({ metricId: saved.id, table: null, nonce: panel.nonce })}
                onDeleted={() => setPanel(null)}
              />
            )}
          </div>
        ) : null}
      </div>

      <SupersetDialog connectionId={connectionId} open={supersetOpen} onOpenChange={setSupersetOpen} />
    </div>
  )
}

function MetricGroup({
  group,
  selectedId,
  onOpen,
  onCreate,
}: {
  group: Group
  selectedId: string | null
  onOpen: (id: string) => void
  onCreate?: () => void
}) {
  const unmatched = group.id === UNMATCHED

  return (
    <section className="overflow-hidden rounded-xl border" aria-label={group.table?.display_name ?? "Chưa khớp bảng"}>
      <header className="flex items-center gap-3 border-b bg-muted/40 px-4 py-2.5">
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2">
          <h3 className="truncate text-sm font-medium">{unmatched ? "Chưa khớp bảng" : group.table?.display_name}</h3>
          <span className="truncate font-mono text-xs text-muted-foreground">
            {unmatched
              ? "Dataset Superset không trỏ tới bảng nào đã đồng bộ"
              : `${group.table?.schema_name}.${group.table?.table_name}`}
          </span>
        </div>
        <Badge variant="outline" className="tabular-nums">
          {group.metrics.length} metric
        </Badge>
        {onCreate ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Thêm metric cho bảng này" onClick={onCreate}>
                <PlusIcon />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Thêm metric cho bảng này</TooltipContent>
          </Tooltip>
        ) : null}
      </header>
      <ul className="flex flex-col divide-y">
        {group.metrics.map((metric) => (
          <li key={metric.id}>
            <MetricRow metric={metric} selected={metric.id === selectedId} onOpen={() => onOpen(metric.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function MetricRow({ metric, selected, onOpen }: { metric: Metric; selected: boolean; onOpen: () => void }) {
  const fromSuperset = metric.origin === "superset"
  const Icon = fromSuperset ? CloudDownloadIcon : SigmaIcon

  return (
    <button
      type="button"
      aria-current={selected || undefined}
      onClick={onOpen}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.3fr)_9.5rem]",
        selected && "bg-muted",
        !metric.is_active && "opacity-60",
      )}
    >
      <span className="flex size-8 items-center justify-center rounded-lg border bg-background text-muted-foreground">
        <Icon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">{metricTitle(metric)}</span>
          {metric.warning_text ? (
            <TriangleAlertIcon className="size-3.5 shrink-0 text-muted-foreground" aria-label="Có cảnh báo khi dùng" />
          ) : null}
        </span>
        <span className="truncate font-mono text-xs text-muted-foreground">{metric.name}</span>
      </span>
      <code className="hidden justify-self-start truncate rounded-md bg-muted/60 px-2 py-1 font-mono text-xs md:block md:max-w-full" title={metric.expression}>
        {metric.expression}
      </code>
      <span className="flex items-center justify-end gap-1.5">
        {!metric.is_active ? <Badge variant="destructive">Đã gỡ</Badge> : null}
        {fromSuperset ? <Badge variant="secondary">Superset</Badge> : null}
      </span>
    </button>
  )
}
