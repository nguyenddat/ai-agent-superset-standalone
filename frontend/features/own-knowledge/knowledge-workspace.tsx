"use client"

import { useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { CircleXIcon, CopyIcon, TriangleAlertIcon } from "lucide-react"

import { Badge as StatusBadge } from "@/components/badge"
import { EmptyState } from "@/components/empty-state"
import { SearchInput } from "@/components/search-input"
import { SegmentedControl } from "@/components/segmented-control"
import { StatTile } from "@/components/stat-tile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

import { useBusinessModel } from "../business-model/api"
import type { ModelTable } from "../business-model/types"
import { useConnectionId } from "../database-connections/detail/connection-layout"
import { useRules } from "../expert-rule-management/api"
import type { ExpertRule } from "../expert-rule-management/types"
import { useGlossary } from "../glossary-management/api"
import type { GlossaryTerm } from "../glossary-management/types"
import { useMetrics } from "../metric-management/api"
import type { Metric } from "../metric-management/types"
import { SYSTEM_STATES, analyze, systemCatalog, type EntryGroup, type Findings } from "./analysis"
import { setReviewPassword, useOwnEntries } from "./api"
import { EntryDetail, type PromoteRequest } from "./entry-detail"
import { KIND_ORDER, KINDS, REVIEW_STATES } from "./labels"
import { PromotePanel } from "./promote-panel"
import type { KnowledgeKind, OwnEntry, ReviewStatus } from "./types"

type StatusFilter = ReviewStatus | "all"
type Panel = { entryId: string; promote: PromoteRequest | null; nonce: number }

export function KnowledgeWorkspace() {
  const connectionId = useConnectionId()
  const [password, setPassword] = useState("")
  const [draftPassword, setDraftPassword] = useState("")
  const entries = useOwnEntries(connectionId, password)
  const glossary = useGlossary(connectionId)
  const metrics = useMetrics(connectionId)
  const rules = useRules(connectionId)
  const model = useBusinessModel(connectionId)

  if (!password || (entries.error instanceof ApiError && entries.error.status === 401)) {
    return (
      <form
        className="mx-auto flex w-full max-w-sm flex-col gap-3 rounded-xl border p-5"
        onSubmit={(event) => {
          event.preventDefault()
          setReviewPassword(draftPassword)
          setPassword(draftPassword)
        }}
      >
        <h2 className="font-medium">Duyệt tri thức riêng</h2>
        <p className="text-sm text-muted-foreground">Nhập mật khẩu admin để xem và duyệt tri thức riêng.</p>
        <Input
          type="password"
          aria-label="Mật khẩu duyệt"
          autoComplete="current-password"
          value={draftPassword}
          onChange={(event) => setDraftPassword(event.target.value)}
          required
        />
        {entries.error instanceof ApiError && entries.error.status === 401 ? (
          <p role="alert" className="text-sm text-destructive">Mật khẩu không đúng hoặc khóa admin backend không khớp.</p>
        ) : null}
        <Button type="submit">Mở danh sách</Button>
      </form>
    )
  }

  if (entries.error instanceof ApiError && entries.error.status === 503) {
    return (
      <div className="rounded-xl border">
        <EmptyState
          scene="offline"
          title="Chưa bật duyệt tri thức riêng"
          description={entries.error.message}
        />
      </div>
    )
  }

  const error = entries.error ?? glossary.error ?? metrics.error ?? rules.error ?? model.error
  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!entries.data || !glossary.data || !metrics.data || !rules.data || !model.data) {
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

  return (
    <KnowledgeList
      connectionId={connectionId}
      entries={entries.data}
      terms={glossary.data}
      metrics={metrics.data}
      rules={rules.data}
      tables={model.data.tables}
      onReload={() => void entries.mutate()}
    />
  )
}

function KnowledgeList({
  connectionId,
  entries,
  terms,
  metrics,
  rules,
  tables,
  onReload,
}: {
  connectionId: string
  entries: OwnEntry[]
  terms: GlossaryTerm[]
  metrics: Metric[]
  rules: ExpertRule[]
  tables: ModelTable[]
  onReload: () => void
}) {
  const params = useSearchParams()
  // `?entry=<id>` opens one entry, so a notification or another screen can link straight to it.
  const requested = params.get("entry")
  const [query, setQuery] = useState("")
  const [status, setStatus] = useState<StatusFilter>(requested ? "all" : "pending")
  const [kind, setKind] = useState<KnowledgeKind | "all">("all")
  const [attentionOnly, setAttentionOnly] = useState(false)
  const [panel, setPanel] = useState<Panel | null>(requested ? { entryId: requested, promote: null, nonce: 0 } : null)

  const tableById = useMemo(() => new Map(tables.map((table) => [table.table_id, table])), [tables])
  const { findings, groups } = useMemo(
    () => analyze(entries, systemCatalog(connectionId, terms, metrics, rules)),
    [connectionId, entries, terms, metrics, rules],
  )
  const selected = panel ? entries.find((entry) => entry.id === panel.entryId) ?? null : null

  const pending = entries.filter((entry) => entry.review_status === "pending")
  const counts: Record<StatusFilter, number> = {
    all: entries.length,
    pending: pending.length,
    kept_own: entries.filter((entry) => entry.review_status === "kept_own").length,
    promoted: entries.filter((entry) => entry.review_status === "promoted").length,
  }
  const visible = useMemo(() => {
    const text = query.trim().toLocaleLowerCase("vi")
    const keep = (entry: OwnEntry) =>
      (status === "all" || entry.review_status === status) &&
      (kind === "all" || entry.kind === kind) &&
      (!attentionOnly || findings.get(entry.id)!.conflicts > 0 || findings.get(entry.id)!.duplicates > 0) &&
      (!text ||
        [entry.name, entry.definition, entry.user_id, entry.source_question]
          .filter(Boolean)
          .some((value) => value!.toLocaleLowerCase("vi").includes(text)))
    // Groups are judged on every entry, so a conflict still shows when the other side is filtered out.
    return groups
      .map((group) => ({ group, shown: group.entries.filter(keep) }))
      .filter((item) => item.shown.length)
      .sort(
        (a, b) =>
          Number(b.group.conflicts) - Number(a.group.conflicts) ||
          Number(b.group.duplicates) - Number(a.group.duplicates) ||
          b.shown.length - a.shown.length ||
          a.group.name.localeCompare(b.group.name, "vi"),
      )
  }, [groups, findings, query, status, kind, attentionOnly])

  const open = (entryId: string, promote: PromoteRequest | null = null) =>
    setPanel((current) => ({ entryId, promote, nonce: (current?.nonce ?? 0) + 1 }))
  const filtered = !!query.trim() || status !== "pending" || kind !== "all" || attentionOnly
  const clearFilters = () => {
    setQuery("")
    setStatus("all")
    setKind("all")
    setAttentionOnly(false)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Chờ duyệt" value={counts.pending} total={counts.all} />
        <StatTile label="Chờ duyệt, có mâu thuẫn" value={pending.filter((entry) => findings.get(entry.id)!.conflicts > 0).length} />
        <StatTile label="Chờ duyệt, có bản trùng" value={pending.filter((entry) => findings.get(entry.id)!.duplicates > 0).length} />
        <StatTile label="Người dùng đóng góp" value={new Set(entries.map((entry) => entry.user_id)).size} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          aria-label="Tìm tri thức riêng"
          placeholder="Tìm tên, nội dung, người dùng"
          className="w-full sm:w-80"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={setQuery}
          shortcut="/"
        />
        <div className="max-w-full overflow-x-auto [scrollbar-width:none]">
          <SegmentedControl
            label="Trạng thái duyệt"
            size="sm"
            value={status}
            onValueChange={(value) => setStatus(value as StatusFilter)}
            options={[
              { value: "pending", label: `Chờ duyệt ${counts.pending}` },
              { value: "kept_own", label: `Giữ riêng ${counts.kept_own}` },
              { value: "promoted", label: `Đã vào kho ${counts.promoted}` },
              { value: "all", label: `Tất cả ${counts.all}` },
            ]}
          />
        </div>
        <Select value={kind} onValueChange={(value) => setKind(value as KnowledgeKind | "all")}>
          <SelectTrigger size="sm" aria-label="Loại" className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">Mọi loại</SelectItem>
              {KIND_ORDER.map((value) => (
                <SelectItem key={value} value={value}>
                  {KINDS[value].label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2">
          <Switch id="attention-only" checked={attentionOnly} onCheckedChange={setAttentionOnly} />
          <Label htmlFor="attention-only" className="font-normal">
            Chỉ mục trùng hoặc mâu thuẫn
          </Label>
        </div>
      </div>

      <div className={cn("grid items-start gap-3", selected && "lg:grid-cols-[minmax(0,1fr)_36rem]")}>
        <div className="flex min-w-0 flex-col gap-3">
          {entries.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="inbox"
                title="Chưa có tri thức riêng"
                description="Khi AI hỏi lại người dùng về một khái niệm chưa có trong kho và họ xác nhận cách hiểu, mục đó sẽ hiện ở đây để bạn duyệt."
              />
            </div>
          ) : visible.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene={status === "pending" && !filtered ? "done" : "search"}
                title={status === "pending" && !filtered ? "Đã duyệt hết" : "Không có mục khớp"}
                description={
                  status === "pending" && !filtered
                    ? "Không còn tri thức riêng nào chờ duyệt cho kết nối này."
                    : "Không có mục nào khớp bộ lọc."
                }
                secondaryAction={{ label: "Xem tất cả", onAction: clearFilters }}
              />
            </div>
          ) : (
            visible.map(({ group, shown }) => (
              <GroupCard
                key={group.key}
                group={group}
                shown={shown}
                findings={findings}
                selectedId={selected?.id ?? null}
                onOpen={(id) => open(id)}
              />
            ))
          )}
        </div>

        {panel && selected ? (
          <div className="order-first overflow-hidden rounded-xl border lg:sticky lg:top-[4.5rem] lg:order-none lg:h-[calc(100svh-5.5rem)]">
            {panel.promote ? (
              <PromotePanel
                key={panel.nonce}
                connectionId={connectionId}
                entry={selected}
                request={panel.promote}
                terms={terms}
                metrics={metrics}
                rules={rules}
                tables={tables}
                onClose={() => open(selected.id)}
                onDone={() => open(selected.id)}
              />
            ) : (
              <EntryDetail
                key={panel.nonce}
                connectionId={connectionId}
                entry={selected}
                findings={findings.get(selected.id)!}
                table={selected.table_id ? tableById.get(selected.table_id) : undefined}
                onClose={() => setPanel(null)}
                onOpenEntry={(id) => {
                  // Opening the other side of a conflict should not land on an empty, filtered list.
                  if (!entries.some((entry) => entry.id === id && (status === "all" || entry.review_status === status))) {
                    setStatus("all")
                  }
                  open(id)
                }}
                onPromote={(request) => open(selected.id, request)}
                onReload={() => {
                  onReload()
                  open(selected.id)
                }}
              />
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}

function GroupCard({
  group,
  shown,
  findings,
  selectedId,
  onOpen,
}: {
  group: EntryGroup
  shown: OwnEntry[]
  findings: Map<string, Findings>
  selectedId: string | null
  onOpen: (id: string) => void
}) {
  const users = new Set(group.entries.map((entry) => entry.user_id)).size
  const live = group.system.filter((item) => item.state !== "revoked" && item.state !== "inactive")

  return (
    <section className="overflow-hidden rounded-xl border" aria-label={group.name}>
      <header className="flex flex-wrap items-center gap-2 border-b bg-muted/40 px-4 py-2.5">
        <h3 className="mr-auto truncate text-sm font-medium">{group.name}</h3>
        {group.meanings > 1 ? (
          <StatusBadge tone="danger" size="sm" dot>{`${group.meanings} cách hiểu khác nhau`}</StatusBadge>
        ) : null}
        {group.againstCatalog ? (
          <StatusBadge tone="danger" size="sm" dot>
            Khác với kho
          </StatusBadge>
        ) : null}
        {group.meanings === 1 && group.entries.length > 1 ? (
          <StatusBadge tone="primary" size="sm">
            Cùng một cách hiểu
          </StatusBadge>
        ) : null}
        {live.map((item) => {
          const Icon = KINDS[item.kind].icon
          return (
            <Badge key={item.id} variant="outline" className="gap-1" title={SYSTEM_STATES[item.state].label}>
              <Icon />
              Trong kho: {item.name}
            </Badge>
          )
        })}
        <Badge variant="outline" className="tabular-nums">
          {users} người dùng
        </Badge>
      </header>
      <ul className="flex flex-col divide-y">
        {shown.map((entry) => (
          <li key={entry.id}>
            <EntryRow entry={entry} findings={findings.get(entry.id)!} selected={entry.id === selectedId} onOpen={() => onOpen(entry.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function EntryRow({
  entry,
  findings,
  selected,
  onOpen,
}: {
  entry: OwnEntry
  findings: Findings
  selected: boolean
  onOpen: () => void
}) {
  const kind = KINDS[entry.kind]
  const status = REVIEW_STATES[entry.review_status]

  return (
    <button
      type="button"
      aria-current={selected || undefined}
      onClick={onOpen}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.6fr)_auto]",
        selected && "bg-muted",
      )}
    >
      <span className="flex size-8 items-center justify-center rounded-lg border bg-background text-muted-foreground">
        <kind.icon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">{entry.user_id}</span>
          {findings.conflicts ? (
            <TriangleAlertIcon className="size-3.5 shrink-0 text-destructive" aria-label={`${findings.conflicts} chỗ khác`} />
          ) : findings.duplicates ? (
            <CopyIcon className="size-3.5 shrink-0 text-muted-foreground" aria-label={`${findings.duplicates} bản trùng`} />
          ) : null}
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {kind.label} · {entry.name}
        </span>
      </span>
      <span className="hidden truncate text-sm text-muted-foreground md:block" title={entry.definition}>
        {entry.definition}
      </span>
      <StatusBadge tone={status.tone} size="sm" dot>
        {status.label}
      </StatusBadge>
    </button>
  )
}
