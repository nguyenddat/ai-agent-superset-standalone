"use client"

import { useMemo, useState } from "react"
import { ArrowLeftIcon, ArrowRightIcon, ChevronRightIcon, PencilIcon, PlusIcon, WorkflowIcon } from "lucide-react"

import { CodeBlock } from "@/components/code-block"
import { NumberRoll } from "@/components/number-roll"
import { SearchInput } from "@/components/search-input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"

import type { ModelTable } from "../business-model/types"
import { ROLES, originLabel } from "./labels"
import type { GraphEdge, Transformation } from "./types"

export type Selection =
  | { kind: "table"; id: string }
  | { kind: "column"; id: string }
  | { kind: "transformation"; id: string }

type LineageSidebarProps = {
  tables: Map<string, ModelTable>
  transformations: Transformation[]
  edges: GraphEdge[]
  selection: Selection | null
  onSelect: (selection: Selection | null) => void
  onCreate: (targetTableId?: string) => void
  onEdit: (transformationId: string) => void
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-muted/60 px-2.5 py-2">
      <NumberRoll value={value} className="text-lg leading-none font-semibold tabular-nums" />
      <span className="text-[11px] text-muted-foreground">{label}</span>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="px-1 text-xs font-medium text-muted-foreground uppercase">{children}</h3>
}

function TransformationSummary({
  transformation,
  tables,
  onEdit,
  onSelectTable,
}: {
  transformation: Transformation
  tables: Map<string, ModelTable>
  onEdit: () => void
  onSelectTable: (tableId: string) => void
}) {
  const target = tables.get(transformation.target_table_id)
  const counts = ROLES.map((role) => ({
    ...role,
    count: transformation.dependencies.filter((dep) => dep.role === role.value).length,
  })).filter((role) => role.count > 0)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <h3 className="text-sm font-medium break-words">{transformation.name}</h3>
          <Badge variant="secondary" className="w-fit">
            {originLabel(transformation.origin)}
          </Badge>
        </div>
        <Button variant="outline" size="sm" onClick={onEdit}>
          <PencilIcon data-icon="inline-start" />
          Sửa
        </Button>
      </div>
      {transformation.description ? <p className="text-sm text-muted-foreground">{transformation.description}</p> : null}

      <div className="flex flex-col gap-1.5">
        <SectionTitle>Nguồn → đích</SectionTitle>
        <ul className="flex flex-col gap-0.5">
          {transformation.source_table_ids.map((id) => (
            <TableLink key={id} table={tables.get(id)} onClick={() => onSelectTable(id)} />
          ))}
        </ul>
        <div className="flex items-center gap-2 px-1 text-muted-foreground">
          <ArrowRightIcon className="size-3.5" />
          <span className="text-xs">tạo ra</span>
        </div>
        <TableLink table={target} onClick={() => onSelectTable(transformation.target_table_id)} />
      </div>

      {counts.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {counts.map((role) => (
            <Badge key={role.value} variant="outline" title={role.hint}>
              {role.count} {role.label.toLowerCase()}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Chưa khai báo liên kết cột.</p>
      )}

      {transformation.sql_text ? (
        <CodeBlock code={transformation.sql_text} language="sql" collapseAfter={10} className="text-xs" />
      ) : null}
    </div>
  )
}

function TableLink({ table, onClick }: { table: ModelTable | undefined; onClick: () => void }) {
  if (!table) return <li className="px-2 text-xs text-muted-foreground">Bảng ngoài phạm vi</li>
  return (
    <li className="list-none">
      <button
        type="button"
        onClick={onClick}
        className="flex w-full flex-col rounded-md px-2 py-1 text-left hover:bg-muted"
        title={`${table.schema_name}.${table.table_name}`}
      >
        <span className="truncate text-sm">{table.display_name}</span>
        <span className="truncate font-mono text-[11px] text-muted-foreground">{table.table_name}</span>
      </button>
    </li>
  )
}

function TableDetail({
  tableId,
  tables,
  transformations,
  edges,
  onSelect,
  onCreate,
  onEdit,
}: { tableId: string } & Omit<LineageSidebarProps, "selection">) {
  const table = tables.get(tableId)
  const upstream = [...new Set(edges.filter((e) => e.target_table_id === tableId).map((e) => e.source_table_id))]
  const downstream = [...new Set(edges.filter((e) => e.source_table_id === tableId).map((e) => e.target_table_id))]
  const producers = transformations.filter((item) => item.target_table_id === tableId)
  if (!table) return null

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-medium">{table.display_name}</h3>
        <p className="font-mono text-xs text-muted-foreground">
          {table.schema_name}.{table.table_name}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <SectionTitle>Nhận từ ({upstream.length})</SectionTitle>
          <ul>
            {upstream.map((id) => (
              <TableLink key={id} table={tables.get(id)} onClick={() => onSelect({ kind: "table", id })} />
            ))}
          </ul>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <SectionTitle>Cấp cho ({downstream.length})</SectionTitle>
          <ul>
            {downstream.map((id) => (
              <TableLink key={id} table={tables.get(id)} onClick={() => onSelect({ kind: "table", id })} />
            ))}
          </ul>
        </div>
      </div>
      <Separator />
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <SectionTitle>Được tạo bởi ({producers.length})</SectionTitle>
          <Button variant="ghost" size="xs" onClick={() => onCreate(tableId)}>
            <PlusIcon data-icon="inline-start" />
            Khai báo
          </Button>
        </div>
        {producers.length === 0 ? (
          <p className="px-1 text-xs text-muted-foreground">Bảng này là nguồn, chưa có phép biến đổi nào tạo ra nó.</p>
        ) : (
          producers.map((item) => (
            <div key={item.id} className="rounded-lg border p-3">
              <TransformationSummary
                transformation={item}
                tables={tables}
                onEdit={() => onEdit(item.id)}
                onSelectTable={(id) => onSelect({ kind: "table", id })}
              />
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export function LineageSidebar(props: LineageSidebarProps) {
  const { tables, transformations, edges, selection, onSelect, onCreate, onEdit } = props
  const [query, setQuery] = useState("")
  const tableCount = new Set(edges.flatMap((edge) => [edge.source_table_id, edge.target_table_id])).size
  const columnLinks = transformations.reduce((sum, item) => sum + item.dependencies.length, 0)

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const matches = (item: Transformation) => {
      const target = tables.get(item.target_table_id)
      return (
        !needle ||
        [item.name, target?.display_name ?? "", target?.table_name ?? "", ...item.source_table_ids.map((id) => tables.get(id)?.table_name ?? "")]
          .some((text) => text.toLowerCase().includes(needle))
      )
    }
    const byTarget = new Map<string, Transformation[]>()
    for (const item of transformations.filter(matches)) {
      byTarget.set(item.target_table_id, [...(byTarget.get(item.target_table_id) ?? []), item])
    }
    return [...byTarget].sort(([a], [b]) =>
      (tables.get(a)?.display_name ?? "").localeCompare(tables.get(b)?.display_name ?? ""),
    )
  }, [query, tables, transformations])

  const selectedTransformation =
    selection?.kind === "transformation" ? transformations.find((item) => item.id === selection.id) : undefined

  return (
    <aside className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
      <div className="grid grid-cols-3 gap-1.5 p-3">
        <Stat label="Bảng" value={tableCount} />
        <Stat label="Phép biến đổi" value={transformations.length} />
        <Stat label="Liên kết cột" value={columnLinks} />
      </div>
      <div className="px-3 pb-3">
        <Button className="w-full" onClick={() => onCreate()}>
          <PlusIcon data-icon="inline-start" />
          Khai báo phép biến đổi
        </Button>
      </div>
      <Separator />

      {selection?.kind === "table" || selectedTransformation ? (
        <ScrollArea className="min-h-0 flex-1">
          <div className="flex flex-col gap-3 p-3">
            <Button variant="ghost" size="sm" className="w-fit" onClick={() => onSelect(null)}>
              <ArrowLeftIcon data-icon="inline-start" />
              Tất cả phép biến đổi
            </Button>
            {selection?.kind === "table" ? (
              <TableDetail tableId={selection.id} {...props} />
            ) : (
              <TransformationSummary
                transformation={selectedTransformation!}
                tables={tables}
                onEdit={() => onEdit(selectedTransformation!.id)}
                onSelectTable={(id) => onSelect({ kind: "table", id })}
              />
            )}
          </div>
        </ScrollArea>
      ) : (
        <section className="flex min-h-0 flex-1 flex-col">
          <header className="flex flex-col gap-2 px-3 pt-3 pb-2">
            <h2 className="text-xs font-medium text-muted-foreground uppercase">Phép biến đổi ({transformations.length})</h2>
            {transformations.length > 0 ? (
              <SearchInput size="sm" placeholder="Tìm theo tên hoặc bảng" shortcut="/" debounce={120} onSearch={setQuery} />
            ) : null}
          </header>
          <ScrollArea className="min-h-0 flex-1">
            {transformations.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-muted-foreground">
                Mỗi phép biến đổi ghi bảng nào tạo ra bảng nào, kèm SQL và liên kết cột.
              </p>
            ) : groups.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-muted-foreground">Không có phép biến đổi khớp “{query}”.</p>
            ) : (
              <ul className="flex flex-col gap-2 px-2 pb-3">
                {groups.map(([targetId, items]) => (
                  <li key={targetId} className="flex flex-col">
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs font-medium text-muted-foreground hover:text-foreground"
                      onClick={() => onSelect({ kind: "table", id: targetId })}
                    >
                      <WorkflowIcon className="size-3.5 shrink-0" />
                      <span className="truncate">{tables.get(targetId)?.display_name ?? "Bảng ngoài phạm vi"}</span>
                    </button>
                    <ul className="flex flex-col">
                      {items.map((item) => (
                        <li key={item.id} className="group/item flex items-center rounded-md hover:bg-muted">
                          <button
                            type="button"
                            onClick={() => onSelect({ kind: "transformation", id: item.id })}
                            className="flex min-w-0 flex-1 flex-col py-1.5 pr-1 pl-7 text-left"
                          >
                            <span className="truncate text-sm">{item.name}</span>
                            <span className="truncate text-[11px] text-muted-foreground">
                              {item.source_table_ids.length} nguồn · {item.dependencies.length} liên kết cột ·{" "}
                              {originLabel(item.origin)}
                            </span>
                          </button>
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            className="mr-1 opacity-0 group-hover/item:opacity-100 focus-visible:opacity-100"
                            aria-label={`Sửa ${item.name}`}
                            onClick={() => onEdit(item.id)}
                          >
                            <PencilIcon />
                          </Button>
                          <ChevronRightIcon className="mr-2 size-3.5 text-muted-foreground group-hover/item:hidden" />
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
        </section>
      )}
    </aside>
  )
}
