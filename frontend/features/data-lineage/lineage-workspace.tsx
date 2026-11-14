"use client"

import { useCallback, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { CircleXIcon, PlusIcon } from "lucide-react"

import { EmptyState } from "@/components/empty-state"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

import { useBusinessModel } from "../business-model/api"
import type { BusinessModel } from "../business-model/types"
import { useConnectionId } from "../database-connections/detail/connection-layout"
import { useLineageGraph, useTableColumns, useTransformations } from "./api"
import { buildLineage, traceColumn, traceTable, traceTransformation, type DetailLevel, type Highlight } from "./graph"
import { LineageCanvas, type CanvasFocus } from "./lineage-canvas"
import { LineageSidebar, type Selection } from "./lineage-sidebar"
import { TransformationEditor } from "./transformation-editor"
import type { LineageGraph, Transformation } from "./types"

const FRAME = "grid min-h-[560px] gap-3 lg:h-[calc(100svh-12.75rem)] lg:grid-cols-[19rem_minmax(0,1fr)]"

export function LineageWorkspace() {
  const connectionId = useConnectionId()
  const model = useBusinessModel(connectionId)
  const graph = useLineageGraph(connectionId)
  const transformations = useTransformations(connectionId)
  const error = model.error ?? graph.error ?? transformations.error

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!model.data || !graph.data || !transformations.data) {
    return (
      <div className={FRAME}>
        <Skeleton className="hidden rounded-xl lg:block" />
        <Skeleton className="rounded-xl" />
      </div>
    )
  }

  if (model.data.tables.length === 0) {
    return (
      <div className="rounded-xl border">
        <EmptyState
          scene="chart"
          title="Chưa có bảng để vẽ dòng dữ liệu"
          description="Đồng bộ metadata của kết nối để lấy danh sách bảng, rồi khai báo bảng nào tạo ra bảng nào."
        />
      </div>
    )
  }

  return (
    <LineageEditor
      connectionId={connectionId}
      model={model.data}
      graph={graph.data}
      transformations={transformations.data}
    />
  )
}

type EditorState = { transformationId: string | null; target: string | null; nonce: number }

function LineageEditor({
  connectionId,
  model,
  graph,
  transformations,
}: {
  connectionId: string
  model: BusinessModel
  graph: LineageGraph
  transformations: Transformation[]
}) {
  const router = useRouter()
  const [detail, setDetail] = useState<DetailLevel>("linked")
  const [selection, setSelection] = useState<Selection | null>(null)
  const [focus, setFocus] = useState<CanvasFocus | null>(null)
  const [editor, setEditor] = useState<EditorState | null>(null)

  const tables = useMemo(() => new Map(model.tables.map((table) => [table.table_id, table])), [model.tables])
  const graphTableIds = useMemo(
    () => [...new Set(graph.edges.flatMap((edge) => [edge.source_table_id, edge.target_table_id]))],
    [graph.edges],
  )
  const { data: columns } = useTableColumns(detail === "tables" ? [] : graphTableIds)
  const { cards, links } = useMemo(
    () => buildLineage(graph.edges, tables, model.layers, detail === "tables" ? undefined : columns, detail),
    [graph.edges, tables, model.layers, columns, detail],
  )
  const columnById = useMemo(() => new Map([...(columns?.values() ?? [])].flat().map((c) => [c.column_id, c])), [columns])

  const highlight = useMemo<Highlight | null>(() => {
    if (!selection) return null
    if (selection.kind === "table") return traceTable(graph.edges, selection.id)
    if (selection.kind === "transformation") return traceTransformation(graph.edges, selection.id)
    const columnTable = new Map([...columnById].map(([id, column]) => [id, column.table_id]))
    return traceColumn(graph.edges, columnTable, selection.id)
  }, [selection, graph.edges, columnById])

  const select = useCallback(
    (next: Selection | null) => {
      setSelection(next)
      if (!next) return
      const columnTable = new Map([...columnById].map(([id, column]) => [id, column.table_id]))
      const ids = [
        ...(next.kind === "table"
          ? traceTable(graph.edges, next.id)
          : next.kind === "transformation"
            ? traceTransformation(graph.edges, next.id)
            : traceColumn(graph.edges, columnTable, next.id)
        ).tables,
      ]
      if (ids.length) setFocus({ tableIds: ids, nonce: Date.now() })
    },
    [graph.edges, columnById],
  )
  const clearSelection = useCallback(() => setSelection(null), [])

  const names = useMemo(() => new Map(transformations.map((item) => [item.id, item.name])), [transformations])
  const selectionLabel = !selection
    ? null
    : selection.kind === "table"
      ? `Dòng dữ liệu của ${tables.get(selection.id)?.display_name ?? "bảng"}`
      : selection.kind === "transformation"
        ? `Phép biến đổi: ${names.get(selection.id) ?? ""}`
        : `Cột ${columnById.get(selection.id)?.name ?? ""}: nguồn và nơi dùng`

  const openEditor = (transformationId: string | null, target: string | null = null) => {
    setEditor({ transformationId, target, nonce: Date.now() })
    if (transformationId) setSelection({ kind: "transformation", id: transformationId })
  }
  const editing = editor?.transformationId ? transformations.find((item) => item.id === editor.transformationId) ?? null : null

  return (
    <div className={FRAME}>
      <LineageSidebar
        tables={tables}
        transformations={transformations}
        edges={graph.edges}
        selection={selection}
        onSelect={select}
        onCreate={(target) => openEditor(null, target ?? null)}
        onEdit={(id) => openEditor(id)}
      />

      <div className="relative min-h-[560px] overflow-hidden rounded-xl border bg-background">
        {graph.edges.length > 0 ? (
          <LineageCanvas
            cards={cards}
            links={links}
            detail={detail}
            onDetailChange={setDetail}
            selectedTable={selection?.kind === "table" ? selection.id : null}
            selectionLabel={selectionLabel}
            focus={focus}
            state={{
              highlight,
              selectedColumn: selection?.kind === "column" ? selection.id : null,
              transformationName: (id) => (id ? names.get(id) ?? null : null),
              onSelectColumn: (id) => select({ kind: "column", id }),
              onOpenTable: (id) => router.push(`/connections/${connectionId}/dictionary?table=${id}`),
            }}
            onSelectTable={(id) => select(id ? { kind: "table", id } : null)}
            onSelectTransformation={(id) => select({ kind: "transformation", id })}
            onClearSelection={clearSelection}
          />
        ) : (
          <div className="flex size-full items-center justify-center p-6">
            <EmptyState
              scene="chart"
              title="Chưa có dòng dữ liệu"
              description="Khai báo phép biến đổi đầu tiên: chọn bảng đích, dán SQL tạo ra nó, hệ thống sẽ nhận bảng nguồn và liên kết cột."
              action={
                <Button onClick={() => openEditor(null)}>
                  <PlusIcon data-icon="inline-start" />
                  Khai báo phép biến đổi
                </Button>
              }
            />
          </div>
        )}

        <div
          className={cn(
            "absolute inset-y-0 right-0 z-10 w-full border-l shadow-2xl transition-transform duration-300 ease-out lg:w-[min(46rem,100%)]",
            editor ? "translate-x-0" : "pointer-events-none translate-x-full",
          )}
          aria-hidden={!editor}
        >
          {editor ? (
            <TransformationEditor
              key={editor.nonce}
              connectionId={connectionId}
              tables={model.tables}
              transformation={editing}
              initialTarget={editor.target}
              onClose={() => setEditor(null)}
              onSaved={(saved) => {
                setEditor(null)
                select({ kind: "transformation", id: saved.id })
              }}
            />
          ) : null}
        </div>
      </div>
    </div>
  )
}
