"use client"

import { useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { CircleXIcon, PlusIcon, ScaleIcon, TriangleAlertIcon, XIcon } from "lucide-react"

import { EmptyState } from "@/components/empty-state"
import { SearchInput } from "@/components/search-input"
import { SegmentedControl } from "@/components/segmented-control"
import { StatTile } from "@/components/stat-tile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

import { domainNames } from "../business-model/domains"
import { useConnectionId } from "../database-connections/detail/connection-layout"
import { refreshRules, useRules } from "./api"
import { describeCondition, ruleState, servingIsStale } from "./labels"
import { RuleDetail } from "./rule-detail"
import { RuleEditor } from "./rule-editor"
import { useRuleRefs, type RuleRefs, type TableRef } from "./rule-refs"
import { RuleStatus } from "./rule-status"
import type { ExpertRule } from "./types"

type StateFilter = "all" | "pending" | "active" | "stale" | "revoked"
type Panel = { ruleId: string | null; mode: "view" | "edit"; table: string | null; nonce: number }
type Group = { id: string; table: TableRef | undefined; rules: ExpertRule[] }

const matchesFilter = (rule: ExpertRule, filter: StateFilter) =>
  filter === "all" ||
  (filter === "pending" && rule.current.status === "draft") ||
  (filter === "active" && rule.is_discoverable) ||
  (filter === "stale" && servingIsStale(rule)) ||
  (filter === "revoked" && rule.current.status === "revoked")

export function RuleWorkspace() {
  const connectionId = useConnectionId()
  const rules = useRules(connectionId)
  const { refs, error: refsError } = useRuleRefs(connectionId)
  const error = rules.error ?? refsError

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!rules.data || !refs) {
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

  return <RuleList connectionId={connectionId} rules={rules.data} refs={refs} />
}

function RuleList({ connectionId, rules, refs }: { connectionId: string; rules: ExpertRule[]; refs: RuleRefs }) {
  const router = useRouter()
  const params = useSearchParams()
  // `?table=<id>` opens on that table's rules and `?rule=<id>` on one rule, so other screens can link here.
  const requestedTable = params.get("table")
  const requestedRule = params.get("rule")
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<StateFilter>("all")
  const [tableFilter, setTableFilter] = useState<string | null>(requestedTable)
  const [panel, setPanel] = useState<Panel | null>(
    requestedRule ? { ruleId: requestedRule, mode: "view", table: null, nonce: 0 } : null,
  )

  const selected = panel?.ruleId ? rules.find((rule) => rule.id === panel.ruleId) ?? null : null
  const counts = {
    all: rules.length,
    pending: rules.filter((rule) => matchesFilter(rule, "pending")).length,
    active: rules.filter((rule) => matchesFilter(rule, "active")).length,
    stale: rules.filter((rule) => matchesFilter(rule, "stale")).length,
    revoked: rules.filter((rule) => matchesFilter(rule, "revoked")).length,
  }

  const groups = useMemo(() => {
    const text = query.trim().toLocaleLowerCase("vi")
    const map = new Map<string, Group>()
    for (const rule of rules) {
      if (!matchesFilter(rule, filter)) continue
      if (tableFilter && rule.table_id !== tableFilter) continue
      const table = refs.tableById.get(rule.table_id)
      if (
        text &&
        ![
          rule.name,
          ...domainNames(rule.business_domains),
          rule.current.description,
          table?.displayName,
          table?.name,
          ...rule.current.examples.map((example) => example.question),
        ]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase("vi").includes(text))
      ) {
        continue
      }
      const group = map.get(rule.table_id) ?? { id: rule.table_id, table, rules: [] }
      group.rules.push(rule)
      map.set(rule.table_id, group)
    }
    return [...map.values()]
      .map((group) => ({ ...group, rules: group.rules.sort((a, b) => a.name.localeCompare(b.name, "vi")) }))
      .sort((a, b) => (a.table?.displayName ?? "").localeCompare(b.table?.displayName ?? "", "vi"))
  }, [rules, query, filter, tableFilter, refs])

  const open = (ruleId: string | null, mode: Panel["mode"], table: string | null = null) =>
    setPanel({ ruleId, mode, table, nonce: Date.now() })
  const filtered = !!query.trim() || filter !== "all" || !!tableFilter
  const clearFilters = () => {
    setQuery("")
    setFilter("all")
    setTableFilter(null)
    if (requestedTable) router.replace(`/connections/${connectionId}/rules`)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Tổng quy tắc" value={counts.all} />
        <StatTile label="AI đang áp dụng" value={counts.active} total={counts.all} />
        <StatTile label="Chờ duyệt" value={counts.pending} />
        <StatTile label="Cần cập nhật" value={counts.stale} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          aria-label="Tìm quy tắc"
          placeholder="Tìm theo tên, mô tả, bảng, câu hỏi"
          className="w-full sm:w-80"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={setQuery}
          shortcut="/"
        />
        <div className="max-w-full overflow-x-auto [scrollbar-width:none]">
          <SegmentedControl
            label="Trạng thái quy tắc"
            size="sm"
            value={filter}
            onValueChange={(value) => setFilter(value as StateFilter)}
            options={[
              { value: "all", label: `Tất cả ${counts.all}` },
              { value: "pending", label: `Chờ duyệt ${counts.pending}` },
              { value: "active", label: `Đang áp dụng ${counts.active}` },
              { value: "stale", label: `Cần cập nhật ${counts.stale}` },
              { value: "revoked", label: `Đã thu hồi ${counts.revoked}` },
            ]}
          />
        </div>
        {tableFilter ? (
          <Badge variant="secondary" className="h-7 gap-1 pr-1">
            Bảng: {refs.tableById.get(tableFilter)?.displayName ?? "không rõ"}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Bỏ lọc theo bảng"
              onClick={() => {
                setTableFilter(null)
                if (requestedTable) router.replace(`/connections/${connectionId}/rules`)
              }}
            >
              <XIcon />
            </Button>
          </Badge>
        ) : null}
        <Button className="ml-auto" onClick={() => open(null, "edit", tableFilter)}>
          <PlusIcon data-icon="inline-start" />
          Thêm quy tắc
        </Button>
      </div>

      <div className={cn("grid items-start gap-3", panel && "lg:grid-cols-[minmax(0,1fr)_36rem]")}>
        <div className="flex min-w-0 flex-col gap-3">
          {rules.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="inbox"
                title="Chưa có quy tắc"
                description="Ghi lại kinh nghiệm của chuyên gia, như ngày nào được tính là nắng nóng, để AI trả lời theo đúng cách đội bạn hiểu dữ liệu."
                action={
                  <Button onClick={() => open(null, "edit")}>
                    <PlusIcon data-icon="inline-start" />
                    Thêm quy tắc
                  </Button>
                }
              />
            </div>
          ) : groups.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="search"
                title="Không có quy tắc khớp"
                description={query.trim() ? `Không thấy quy tắc nào khớp "${query.trim()}".` : "Không có quy tắc nào khớp bộ lọc."}
                secondaryAction={filtered ? { label: "Xóa bộ lọc", onAction: clearFilters } : undefined}
              />
            </div>
          ) : (
            groups.map((group) => (
              <RuleGroup
                key={group.id}
                group={group}
                refs={refs}
                selectedId={panel?.ruleId ?? null}
                onOpen={(id) => open(id, "view")}
                onCreate={() => open(null, "edit", group.id)}
              />
            ))
          )}
        </div>

        {panel && (panel.mode === "edit" || selected) ? (
          <div className="order-first overflow-hidden rounded-xl border lg:sticky lg:top-[4.5rem] lg:order-none lg:h-[calc(100svh-5.5rem)]">
            {panel.mode === "edit" ? (
              <RuleEditor
                key={panel.nonce}
                connectionId={connectionId}
                rules={rules}
                refs={refs}
                rule={selected}
                initialTable={panel.table}
                onClose={() => (selected ? open(selected.id, "view") : setPanel(null))}
                onSaved={(saved) => open(saved.id, "view")}
                onReload={async () => {
                  await refreshRules(connectionId)
                  open(panel.ruleId, "edit")
                }}
              />
            ) : (
              <RuleDetail
                key={panel.nonce}
                connectionId={connectionId}
                rule={selected!}
                refs={refs}
                onClose={() => setPanel(null)}
                onEdit={() => open(selected!.id, "edit")}
                onDeleted={() => setPanel(null)}
              />
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function RuleGroup({
  group,
  refs,
  selectedId,
  onOpen,
  onCreate,
}: {
  group: Group
  refs: RuleRefs
  selectedId: string | null
  onOpen: (id: string) => void
  onCreate: () => void
}) {
  const title = group.table?.displayName ?? "Bảng đã xóa"

  return (
    <section className="overflow-hidden rounded-xl border" aria-label={title}>
      <header className="flex items-center gap-3 border-b bg-muted/40 px-4 py-2.5">
        <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2">
          <h3 className="truncate text-sm font-medium">{title}</h3>
          {group.table ? (
            <span className="truncate font-mono text-xs text-muted-foreground">
              {group.table.schemaName ? `${group.table.schemaName}.` : ""}
              {group.table.name}
            </span>
          ) : null}
        </div>
        <Badge variant="outline" className="tabular-nums">
          {group.rules.length} quy tắc
        </Badge>
        {group.table ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Thêm quy tắc cho bảng này" onClick={onCreate}>
                <PlusIcon />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Thêm quy tắc cho bảng này</TooltipContent>
          </Tooltip>
        ) : null}
      </header>
      <ul className="flex flex-col divide-y">
        {group.rules.map((rule) => (
          <li key={rule.id}>
            <RuleRow rule={rule} refs={refs} selected={rule.id === selectedId} onOpen={() => onOpen(rule.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function RuleRow({
  rule,
  refs,
  selected,
  onOpen,
}: {
  rule: ExpertRule
  refs: RuleRefs
  selected: boolean
  onOpen: () => void
}) {
  const { conditions, description } = rule.current
  const first = conditions[0]
  const summary =
    description ??
    (first ? describeCondition(first, refs.columnById.get(first.column_id)?.name ?? "cột đã xóa") : "")

  return (
    <button
      type="button"
      aria-current={selected || undefined}
      onClick={onOpen}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.4fr)_auto]",
        selected && "bg-muted",
        ruleState(rule) === "revoked" && "opacity-60",
      )}
    >
      <span className="flex size-8 items-center justify-center rounded-lg border bg-background text-muted-foreground">
        <ScaleIcon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">{rule.name}</span>
          {ruleState(rule) === "changed" && servingIsStale(rule) ? (
            <TriangleAlertIcon className="size-3.5 shrink-0 text-muted-foreground" aria-label="Bản đang dùng tạm ngừng" />
          ) : null}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {[...domainNames(rule.business_domains), `${conditions.length} điều kiện`].join(" · ")}
        </span>
      </span>
      <span className="hidden truncate text-sm text-muted-foreground md:block" title={summary}>
        {summary}
      </span>
      <RuleStatus rule={rule} size="sm" />
    </button>
  )
}
