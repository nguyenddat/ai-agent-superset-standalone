"use client"

import { createContext, useContext } from "react"
import {
  BaseEdge,
  EdgeLabelRenderer,
  Handle,
  Position,
  getBezierPath,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react"
import { EyeIcon, KeyRoundIcon, SigmaIcon, Table2Icon } from "lucide-react"

import { cn } from "@/lib/utils"

import {
  CARD_HEADER,
  CARD_MORE,
  CARD_ROW,
  CARD_WIDTH,
  columnHandle,
  headerHandle,
  linkLit,
  type Card,
  type Highlight,
  type Link,
} from "./graph"
import { ROLE_STROKE, isView, roleLabel } from "./labels"

export type LineageCanvasState = {
  highlight: Highlight | null
  selectedColumn: string | null
  hoveredLink: string | null
  transformationName: (id: string | null) => string | null
  onSelectColumn: (columnId: string) => void
  onOpenTable: (tableId: string) => void
}

export const LineageContext = createContext<LineageCanvasState | null>(null)

const useLineage = () => useContext(LineageContext) as LineageCanvasState

export type CardNode = Node<{ card: Card }, "card">
export type LinkEdge = Edge<{ link: Link }, "link">

const hidden = "!size-2 !min-w-0 !border-0 !bg-transparent"

export function TableCard({ data, selected }: NodeProps<CardNode>) {
  const { card } = data
  const { table, layer } = card
  const lineage = useLineage()
  const dimmed = lineage.highlight !== null && !lineage.highlight.tables.has(card.id)
  const Icon = isView(table.table_type) ? EyeIcon : table.table_kind === "aggregate" ? SigmaIcon : Table2Icon

  return (
    <div
      onDoubleClick={() => lineage.onOpenTable(card.id)}
      style={{ width: CARD_WIDTH, "--layer": layer?.color ?? "var(--border)" } as React.CSSProperties}
      className={cn(
        "relative overflow-hidden rounded-xl border bg-card text-card-foreground shadow-sm transition-[opacity,box-shadow] duration-200",
        selected && "ring-2 ring-ring/60",
        dimmed && "opacity-30",
      )}
    >
      <Handle id={headerHandle("in")} type="target" position={Position.Left} style={{ top: CARD_HEADER / 2 }} className={hidden} isConnectable={false} />
      <Handle id={headerHandle("out")} type="source" position={Position.Right} style={{ top: CARD_HEADER / 2 }} className={hidden} isConnectable={false} />

      <header
        className="flex items-center gap-2.5 border-l-4 border-l-(--layer) px-3"
        style={{ height: CARD_HEADER }}
        title={[
          table.display_name,
          `${table.schema_name}.${table.table_name} · ${table.table_type}`,
          layer ? `Tầng: ${layer.name}` : null,
          "Nhấp để lần dòng dữ liệu, nhấp đúp để mở từ điển",
        ]
          .filter(Boolean)
          .join("\n")}
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="size-4" />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium">{table.display_name}</span>
          <span className="truncate font-mono text-[11px] text-muted-foreground">
            {table.schema_name}.{table.table_name}
          </span>
        </span>
      </header>

      {card.rows.map((row, index) => {
        const top = CARD_HEADER + index * CARD_ROW + CARD_ROW / 2
        const active = lineage.selectedColumn === row.column_id
        const lit = !active && (lineage.highlight?.columns.has(row.column_id) ?? false)
        return (
          <button
            key={row.column_id}
            type="button"
            title={`${row.display_name}\n${row.name} · ${row.data_type}\nNhấp để lần cột này`}
            onClick={(event) => {
              event.stopPropagation()
              lineage.onSelectColumn(row.column_id)
            }}
            className={cn(
              "nodrag flex w-full items-center gap-2 border-t px-3 text-left text-xs transition-colors hover:bg-muted/70",
              active && "bg-[color-mix(in_oklch,var(--chart-1)_18%,transparent)]",
              lit && "bg-[color-mix(in_oklch,var(--chart-1)_9%,transparent)]",
            )}
            style={{ height: CARD_ROW }}
          >
            <Handle id={columnHandle(row.column_id, "in")} type="target" position={Position.Left} style={{ top }} className={hidden} isConnectable={false} />
            <Handle id={columnHandle(row.column_id, "out")} type="source" position={Position.Right} style={{ top }} className={hidden} isConnectable={false} />
            <span className="flex w-3 shrink-0 justify-center text-muted-foreground">
              {row.is_key ? <KeyRoundIcon className="size-3" /> : null}
            </span>
            <span className={cn("min-w-0 flex-1 truncate font-mono", (active || lit) && "font-medium")}>{row.name}</span>
            <span className="max-w-24 shrink-0 truncate font-mono text-[10px] text-muted-foreground">{row.data_type}</span>
          </button>
        )
      })}
      {card.hidden > 0 ? (
        <p className="flex items-center border-t px-3 text-[11px] text-muted-foreground" style={{ height: CARD_MORE }}>
          +{card.hidden} cột không tham gia lineage
        </p>
      ) : null}
    </div>
  )
}

export function LineageLink({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd }: EdgeProps<LinkEdge>) {
  const lineage = useLineage()
  const link = data!.link
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const lit = lineage.highlight ? linkLit(link, lineage.highlight) : false
  const hovered = lineage.hoveredLink === id
  // Links that only shape the rows end on the target's header; they stay faint until a selection lights them.
  const quiet = link.role !== null && link.role !== "value"
  const dimmed = lineage.highlight !== null && !lit
  const stroke = link.role ? ROLE_STROKE[link.role] : { color: "var(--muted-foreground)", dash: link.kind === "flow" ? "6 5" : undefined }
  const name = lineage.transformationName(link.transformationId)
  const label = [name ?? (link.kind === "flow" ? "Cạnh khai báo ở Mô hình" : null), link.role ? roleLabel(link.role) : null]
    .filter(Boolean)
    .join(" · ")

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        interactionWidth={18}
        style={{
          stroke: stroke.color,
          strokeDasharray: stroke.dash,
          strokeWidth: lit || hovered ? 2.4 : 1.5,
          strokeOpacity: dimmed && !hovered ? 0.08 : lit || hovered ? 1 : quiet ? 0.22 : 0.55,
          transition: "stroke-opacity 200ms, stroke-width 200ms",
        }}
      />
      {hovered && label ? (
        <EdgeLabelRenderer>
          <span
            className="pointer-events-none absolute rounded-full border bg-popover px-2.5 py-1 text-[11px] font-medium whitespace-nowrap text-popover-foreground shadow-md"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {label}
          </span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}
