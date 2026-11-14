"use client"

import { CircleAlertIcon, ExternalLinkIcon, LockIcon, TriangleAlertIcon, XIcon } from "lucide-react"

import { CodeBlock } from "@/components/code-block"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"

import type { ModelTable } from "../business-model/types"
import { dateFormat } from "../database-connections/connection-format"
import { useSupersetDatabases, useSupersetUsers } from "./api"
import { formatSample, metricTitle } from "./labels"
import type { Metric, SupersetUser } from "./types"

const userName = (user: SupersetUser | undefined) =>
  user ? [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username : null

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

/** A metric synced from Superset: everything it says, read-only, with the way back to where it can be edited. */
export function MetricDetail({
  metric,
  table,
  onClose,
}: {
  metric: Metric
  table: ModelTable | undefined
  onClose: () => void
}) {
  const { data: databases } = useSupersetDatabases()
  const { data: users } = useSupersetUsers()
  const database = databases?.find((item) => item.id === metric.source_database_id)
  const creator = userName(users?.find((item) => item.id === metric.source_user_id))
  const owner = userName(users?.find((item) => item.id === metric.source_dataset_owner_id))
  const sample = formatSample(metric.format, metric.currency)
  const exploreUrl =
    metric.source_url && metric.source_dataset_id
      ? `${metric.source_url.replace(/\/$/, "")}/explore/?datasource_type=table&datasource_id=${metric.source_dataset_id}`
      : null

  return (
    <section aria-label="Chi tiết metric" className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-1">
          <h2 className="truncate text-base font-medium">{metricTitle(metric)}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate font-mono text-xs text-muted-foreground">{metric.name}</span>
            <Badge variant="secondary">Superset</Badge>
            {!metric.is_active ? <Badge variant="destructive">Đã gỡ khỏi Superset</Badge> : null}
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-5 px-5 py-5">
          {!metric.is_active ? (
            <Alert variant="destructive">
              <CircleAlertIcon />
              <AlertTitle>Không còn trên Superset</AlertTitle>
              <AlertDescription>Lần đồng bộ gần nhất không thấy metric này nữa. Nó được giữ lại để tra cứu.</AlertDescription>
            </Alert>
          ) : null}
          {metric.warning_text ? (
            <Alert>
              <TriangleAlertIcon />
              <AlertTitle>Cảnh báo khi dùng</AlertTitle>
              <AlertDescription>{metric.warning_text}</AlertDescription>
            </Alert>
          ) : null}
          {metric.description ? <p className="text-sm">{metric.description}</p> : null}

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Biểu thức</h3>
            <CodeBlock code={metric.expression} language="sql" collapseAfter={8} className="text-xs" />
          </div>

          <dl className="flex flex-col">
            <Row label="Bảng">
              {table ? (
                <>
                  {table.display_name}{" "}
                  <span className="font-mono text-xs text-muted-foreground">
                    {table.schema_name}.{table.table_name}
                  </span>
                </>
              ) : (
                <span className="text-muted-foreground">Chưa khớp bảng nào trong metadata</span>
              )}
            </Row>
            {sample ? (
              <Row label="Hiển thị">
                <span className="font-mono tabular-nums">{sample}</span>
                {metric.format ? <span className="ml-2 font-mono text-xs text-muted-foreground">{metric.format}</span> : null}
              </Row>
            ) : metric.format ? (
              <Row label="Định dạng">
                <span className="font-mono">{metric.format}</span>
              </Row>
            ) : null}
            {metric.metric_type ? <Row label="Loại metric">{metric.metric_type}</Row> : null}
          </dl>

          <Separator />

          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Nguồn trên Superset</h3>
            <dl className="flex flex-col">
              <Row label="Database">
                {database ? (
                  <>
                    {database.name}
                    {database.backend ? <span className="ml-2 text-xs text-muted-foreground">{database.backend}</span> : null}
                  </>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Dataset">
                {metric.source_schema || metric.source_table ? (
                  <span className="font-mono text-xs">
                    {[metric.source_schema, metric.source_table].filter(Boolean).join(".")}
                  </span>
                ) : metric.source_sql ? (
                  "Dataset ảo"
                ) : (
                  "—"
                )}
                {metric.source_dataset_id ? (
                  <span className="ml-2 text-xs text-muted-foreground">#{metric.source_dataset_id}</span>
                ) : null}
              </Row>
              {creator ? <Row label="Người tạo metric">{creator}</Row> : null}
              {owner ? <Row label="Người tạo dataset">{owner}</Row> : null}
              <Row label="Đồng bộ lúc">{dateFormat.format(new Date(metric.updated_at))}</Row>
            </dl>
          </div>

          {metric.source_sql ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">SQL của dataset ảo</h3>
              <CodeBlock code={metric.source_sql} language="sql" collapseAfter={8} className="text-xs" />
            </div>
          ) : null}
        </div>
      </ScrollArea>

      <footer className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
        <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <LockIcon className="size-3.5" />
          Chỉ sửa tại Superset, rồi đồng bộ lại.
        </span>
        {exploreUrl ? (
          <Button variant="outline" size="sm" className="ml-auto" asChild>
            <a href={exploreUrl} target="_blank" rel="noreferrer">
              Mở trong Superset
              <ExternalLinkIcon data-icon="inline-end" />
            </a>
          </Button>
        ) : null}
      </footer>
    </section>
  )
}
