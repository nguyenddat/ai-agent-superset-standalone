"use client"

import { useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import { BookTextIcon, CircleXIcon, LinkIcon, PlusIcon } from "lucide-react"

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

import { useBusinessModel } from "../business-model/api"
import { domainNames, DomainDot, groupByDomain, NO_DOMAIN, type DomainRef } from "../business-model/domains"
import type { ModelTable } from "../business-model/types"
import { useConnectionId } from "../database-connections/detail/connection-layout"
import { useMetrics } from "../metric-management/api"
import type { Metric } from "../metric-management/types"
import { refreshGlossary, useGlossary } from "./api"
import { termState } from "./labels"
import { useLinkTargets } from "./link-targets"
import { TermDetail } from "./term-detail"
import { TermEditor } from "./term-editor"
import { TermStatus } from "./term-status"
import type { GlossaryTerm } from "./types"

type StateFilter = "all" | "pending" | "serving" | "revoked"
type Panel = { termId: string | null; mode: "view" | "edit"; domainId: string | null; nonce: number }
type Group = { domain: DomainRef | null; items: GlossaryTerm[] }

const matchesFilter = (term: GlossaryTerm, filter: StateFilter) =>
  filter === "all" ||
  (filter === "pending" && term.current.status === "draft") ||
  (filter === "serving" && !!term.serving) ||
  (filter === "revoked" && term.current.status === "revoked")

export function GlossaryWorkspace() {
  const connectionId = useConnectionId()
  const model = useBusinessModel(connectionId)
  const metrics = useMetrics(connectionId)
  const glossary = useGlossary(connectionId)
  const error = glossary.error ?? model.error ?? metrics.error

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!glossary.data || !model.data || !metrics.data) {
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
    <GlossaryList connectionId={connectionId} terms={glossary.data} tables={model.data.tables} metrics={metrics.data} />
  )
}

function GlossaryList({
  connectionId,
  terms,
  tables,
  metrics,
}: {
  connectionId: string
  terms: GlossaryTerm[]
  tables: ModelTable[]
  metrics: Metric[]
}) {
  // `?term=<id>` opens that term, so other screens can link straight to a definition.
  const requestedTerm = useSearchParams().get("term")
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<StateFilter>("all")
  const [panel, setPanel] = useState<Panel | null>(
    requestedTerm ? { termId: requestedTerm, mode: "view", domainId: null, nonce: 0 } : null,
  )

  const selected = panel?.termId ? terms.find((term) => term.id === panel.termId) ?? null : null
  const showsColumns =
    panel?.mode === "edit" ||
    !!selected &&
      [...selected.current.links, ...(selected.serving?.links ?? [])].some((link) => link.kind === "column")
  const targets = useLinkTargets(connectionId, tables, metrics, showsColumns)

  const counts = {
    all: terms.length,
    pending: terms.filter((term) => matchesFilter(term, "pending")).length,
    serving: terms.filter((term) => matchesFilter(term, "serving")).length,
    revoked: terms.filter((term) => matchesFilter(term, "revoked")).length,
  }
  const linked = terms.filter((term) => term.current.links.length > 0).length

  const groups = useMemo(() => {
    const text = query.trim().toLocaleLowerCase("vi")
    const shown = terms
      .filter((term) => matchesFilter(term, filter))
      .filter(
        (term) =>
          !text ||
          [term.canonical_name, ...domainNames(term.business_domains), term.current.definition, ...term.current.synonyms]
            .some((value) => value.toLocaleLowerCase("vi").includes(text)),
      )
      .sort((a, b) => a.canonical_name.localeCompare(b.canonical_name, "vi"))
    return groupByDomain(shown, (term) => term.business_domains)
  }, [terms, query, filter])

  const open = (termId: string | null, mode: Panel["mode"], domainId: string | null = null) =>
    setPanel({ termId, mode, domainId, nonce: Date.now() })
  const filtered = !!query.trim() || filter !== "all"

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Tổng thuật ngữ" value={counts.all} />
        <StatTile label="AI đang dùng" value={counts.serving} total={counts.all} />
        <StatTile label="Chờ duyệt" value={counts.pending} />
        <StatTile label="Đã liên kết dữ liệu" value={linked} total={counts.all} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          aria-label="Tìm thuật ngữ"
          placeholder="Tìm theo tên, từ đồng nghĩa, định nghĩa"
          className="w-full sm:w-80"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onSearch={setQuery}
          shortcut="/"
        />
        <SegmentedControl
          label="Trạng thái thuật ngữ"
          size="sm"
          value={filter}
          onValueChange={(value) => setFilter(value as StateFilter)}
          options={[
            { value: "all", label: `Tất cả ${counts.all}` },
            { value: "pending", label: `Chờ duyệt ${counts.pending}` },
            { value: "serving", label: `Đang dùng ${counts.serving}` },
            { value: "revoked", label: `Đã thu hồi ${counts.revoked}` },
          ]}
        />
        <Button className="ml-auto" onClick={() => open(null, "edit")}>
          <PlusIcon data-icon="inline-start" />
          Thêm thuật ngữ
        </Button>
      </div>

      <div className={cn("grid items-start gap-3", panel && "lg:grid-cols-[minmax(0,1fr)_32rem]")}>
        <div className="flex min-w-0 flex-col gap-3">
          {terms.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="inbox"
                title="Chưa có thuật ngữ"
                description="Định nghĩa những từ nghiệp vụ như Doanh thu thuần hay Khách hàng hoạt động, để mọi người và AI hiểu cùng một nghĩa."
                action={
                  <Button onClick={() => open(null, "edit")}>
                    <PlusIcon data-icon="inline-start" />
                    Thêm thuật ngữ
                  </Button>
                }
              />
            </div>
          ) : groups.length === 0 ? (
            <div className="rounded-xl border">
              <EmptyState
                scene="search"
                title="Không có thuật ngữ khớp"
                description={
                  query.trim() ? `Không thấy thuật ngữ nào khớp "${query.trim()}".` : "Không có thuật ngữ nào ở trạng thái này."
                }
                secondaryAction={
                  filtered
                    ? {
                        label: "Xóa bộ lọc",
                        onAction: () => {
                          setQuery("")
                          setFilter("all")
                        },
                      }
                    : undefined
                }
              />
            </div>
          ) : (
            groups.map((group) => (
              <TermGroup
                key={group.domain?.id ?? ""}
                group={group}
                selectedId={panel?.termId ?? null}
                onOpen={(id) => open(id, "view")}
                onCreate={() => open(null, "edit", group.domain?.id ?? null)}
              />
            ))
          )}
        </div>

        {panel && (panel.mode === "edit" || selected) ? (
          <div className="order-first overflow-hidden rounded-xl border lg:sticky lg:top-[4.5rem] lg:order-none lg:h-[calc(100svh-5.5rem)]">
            {panel.mode === "edit" ? (
              <TermEditor
                key={panel.nonce}
                connectionId={connectionId}
                terms={terms}
                term={selected}
                initialDomainId={panel.domainId}
                targets={targets}
                onClose={() => (selected ? open(selected.id, "view") : setPanel(null))}
                onSaved={(saved) => open(saved.id, "view")}
                onReload={async () => {
                  await refreshGlossary(connectionId)
                  open(panel.termId, "edit")
                }}
              />
            ) : (
              <TermDetail
                key={panel.nonce}
                connectionId={connectionId}
                term={selected!}
                targets={targets}
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

function TermGroup({
  group,
  selectedId,
  onOpen,
  onCreate,
}: {
  group: Group
  selectedId: string | null
  onOpen: (id: string) => void
  onCreate: () => void
}) {
  const title = group.domain?.name ?? NO_DOMAIN
  const label = group.domain ? "Thêm thuật ngữ vào miền này" : "Thêm thuật ngữ chưa phân miền"

  return (
    <section className="overflow-hidden rounded-xl border" aria-label={title}>
      <header className="flex items-center gap-3 border-b bg-muted/40 px-4 py-2.5">
        {group.domain ? <DomainDot color={group.domain.color} /> : null}
        <h3 className={cn("min-w-0 flex-1 truncate text-sm font-medium", !group.domain && "text-muted-foreground")}>
          {title}
        </h3>
        <Badge variant="outline" className="tabular-nums">
          {group.items.length} thuật ngữ
        </Badge>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onCreate}>
              <PlusIcon />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      </header>
      <ul className="flex flex-col divide-y">
        {group.items.map((term) => (
          <li key={term.id}>
            <TermRow term={term} selected={term.id === selectedId} onOpen={() => onOpen(term.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

function TermRow({ term, selected, onOpen }: { term: GlossaryTerm; selected: boolean; onOpen: () => void }) {
  const { synonyms, links, definition } = term.current

  return (
    <button
      type="button"
      aria-current={selected || undefined}
      onClick={onOpen}
      className={cn(
        "grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1.4fr)_auto]",
        selected && "bg-muted",
        termState(term) === "revoked" && "opacity-60",
      )}
    >
      <span className="flex size-8 items-center justify-center rounded-lg border bg-background text-muted-foreground">
        <BookTextIcon className="size-4" />
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-sm font-medium">{term.canonical_name}</span>
        <span className="truncate text-xs text-muted-foreground">
          {synonyms.length ? synonyms.join(" · ") : "Chưa có từ đồng nghĩa"}
        </span>
      </span>
      <span className="hidden truncate text-sm text-muted-foreground md:block" title={definition}>
        {definition}
      </span>
      <span className="flex items-center justify-end gap-2">
        <span
          className={cn(
            "hidden items-center gap-1 text-xs tabular-nums sm:flex",
            links.length ? "text-muted-foreground" : "text-muted-foreground/60",
          )}
          title={links.length ? `${links.length} liên kết dữ liệu` : "Chưa liên kết dữ liệu"}
        >
          <LinkIcon className="size-3.5" aria-hidden />
          {links.length}
        </span>
        <TermStatus term={term} size="sm" />
      </span>
    </button>
  )
}
