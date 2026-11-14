"use client"

import { createContext, useContext } from "react"
import {
  BaseEdge,
  Handle,
  Position,
  useInternalNode,
  type Edge,
  type EdgeProps,
  type InternalNode,
  type Node,
  type NodeProps,
} from "@xyflow/react"
import { PencilIcon, SigmaIcon, Table2Icon } from "lucide-react"

import { cn } from "@/lib/utils"

import type { BusinessDomain, DataLayer, ModelTable } from "./types"
import { CIRCLE_SIZE, NODE_WIDTH } from "./venn-layout"

export type CanvasHighlight = {
  hoveredTable: string | null
  related: Set<string>
  dropRegions: Set<string> | null
  setHoveredTable: (tableId: string | null) => void
  onEditDomain: (domain: BusinessDomain) => void
  onOpenTable: (tableId: string) => void
}

export const CanvasContext = createContext<CanvasHighlight | null>(null)

const useCanvas = () => useContext(CanvasContext) as CanvasHighlight

export type RegionNodeData = { domain: BusinessDomain; color: string; count: number }
export type TableNodeData = { table: ModelTable; colors: string[]; domainNames: string[]; layer: DataLayer | null }
export type LineageEdgeData = { kind: "flow" | "relation" }
export type RegionNode = Node<RegionNodeData, "region">
export type TableNode = Node<TableNodeData, "table">
export type LineageLinkEdge = Edge<LineageEdgeData, "lineage">

export function DomainRegion({ data }: NodeProps<RegionNode>) {
  const { domain, color, count } = data
  const canvas = useCanvas()
  const dropping = canvas.dropRegions?.has(domain.id) ?? false

  return (
    <div
      style={{ "--domain": color } as React.CSSProperties}
      className={cn(
        "relative size-full rounded-[28px] border-[1.5px] border-[color-mix(in_oklch,var(--domain)_55%,transparent)] bg-[color-mix(in_oklch,var(--domain)_6%,transparent)] transition-[background-color,border-color] duration-200",
        dropping && "border-dashed border-(--domain) bg-[color-mix(in_oklch,var(--domain)_14%,transparent)]",
      )}
    >
      <button
        type="button"
        onClick={() => canvas.onEditDomain(domain)}
        title={domain.description ?? undefined}
        className="nodrag nopan group/label pointer-events-auto absolute -top-3 left-5 flex h-6 max-w-[calc(100%-2.5rem)] items-center gap-1.5 rounded-full bg-(--domain) px-2.5 text-xs font-medium text-white shadow-sm"
      >
        <span className="truncate">{domain.name}</span>
        <span className="rounded-full bg-white/20 px-1.5 text-[10px] tabular-nums">{count}</span>
        <PencilIcon className="hidden size-3 group-hover/label:block" />
      </button>
      {count === 0 ? (
        <span className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
          Kéo bảng vào đây
        </span>
      ) : null}
    </div>
  )
}

// Physical names such as fact_chi_tiet_thoi_tiet break after an underscore instead of in the middle of a word.
const wrapAtUnderscores = (name: string) =>
  name.split("_").flatMap((part, index, parts) => (index < parts.length - 1 ? [part, "_", <wbr key={index} />] : [part]))

const circleBackground =(colors: string[]) => {
  if (colors.length === 0) return "var(--muted-foreground)"
  if (colors.length === 1) return colors[0]
  const step = 100 / colors.length
  return `linear-gradient(135deg, ${colors.map((color, index) => `${color} ${index * step}% ${(index + 1) * step}%`).join(", ")})`
}

export function TableCircle({ data, dragging }: NodeProps<TableNode>) {
  const { table, colors, domainNames, layer } = data
  const canvas = useCanvas()
  const focused = canvas.hoveredTable !== null
  const isHovered = canvas.hoveredTable === table.table_id
  const isRelated = canvas.related.has(table.table_id)
  const Icon = table.table_kind === "aggregate" ? SigmaIcon : Table2Icon
  const outside = colors.length === 0

  return (
    <div
      onMouseEnter={() => canvas.setHoveredTable(table.table_id)}
      onMouseLeave={() => canvas.setHoveredTable(null)}
      onDoubleClick={() => canvas.onOpenTable(table.table_id)}
      title={[
        table.display_name,
        `${table.schema_name}.${table.table_name}`,
        domainNames.length > 0 ? `Miền: ${domainNames.join(", ")}` : "Chưa thuộc miền nào",
        layer ? `Tầng: ${layer.name}` : null,
        "Nhấp đúp để mở từ điển",
      ]
        .filter(Boolean)
        .join("\n")}
      className={cn(
        "flex flex-col items-center gap-1.5 transition-opacity duration-200",
        focused && !isHovered && !isRelated && "opacity-30",
      )}
      style={{ width: NODE_WIDTH }}
    >
      <div className="relative" style={{ width: CIRCLE_SIZE, height: CIRCLE_SIZE }}>
        <Handle type="source" position={Position.Top} isConnectable={false} className="opacity-0" />
        <Handle type="target" position={Position.Top} isConnectable={false} className="opacity-0" />
        <span
          className={cn(
            "flex size-full items-center justify-center rounded-full text-white shadow-md ring-2 ring-background transition-transform duration-200",
            outside && "opacity-70",
            isHovered && "scale-110 ring-[3px] ring-foreground/70",
            dragging && "scale-110 shadow-xl",
          )}
          style={{ background: circleBackground(colors) }}
        >
          <Icon className="size-5" strokeWidth={2.25} />
        </span>
        {layer?.color ? (
          <span
            title={`Tầng: ${layer.name}`}
            className="absolute -right-0.5 -bottom-0.5 size-3.5 rounded-full ring-2 ring-background"
            style={{ background: layer.color }}
          />
        ) : null}
      </div>
      <span
        className={cn(
          "line-clamp-2 w-full text-center text-xs leading-tight font-medium [overflow-wrap:anywhere]",
          !table.is_saved && "text-muted-foreground",
        )}
      >
        {wrapAtUnderscores(table.display_name)}
      </span>
    </div>
  )
}

function circleCenter(node: InternalNode) {
  return {
    x: node.internals.positionAbsolute.x + (node.measured.width ?? NODE_WIDTH) / 2,
    y: node.internals.positionAbsolute.y + CIRCLE_SIZE / 2,
  }
}

const RADIUS = CIRCLE_SIZE / 2 + 3

export function LineageLink({ id, source, target, data, markerEnd }: EdgeProps<LineageLinkEdge>) {
  const sourceNode = useInternalNode(source)
  const targetNode = useInternalNode(target)
  const canvas = useCanvas()
  if (!sourceNode || !targetNode) return null

  const from = circleCenter(sourceNode)
  const to = circleCenter(targetNode)
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  const [ux, uy] = [dx / length, dy / length]
  const start = { x: from.x + ux * RADIUS, y: from.y + uy * RADIUS }
  const end = { x: to.x - ux * RADIUS, y: to.y - uy * RADIUS }
  // A gentle bend to one side keeps edges between neighbouring circles apart, as in a hand-drawn model.
  const bend = Math.min(60, length * 0.18)
  const control = { x: (start.x + end.x) / 2 - uy * bend, y: (start.y + end.y) / 2 + ux * bend }
  const path = `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`

  const hovered = canvas.hoveredTable
  const active = hovered !== null && (source === hovered || target === hovered)
  const faded = hovered !== null && !active

  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={active && data?.kind === "flow" ? markerEnd : undefined}
      style={{
        stroke: active ? "var(--foreground)" : "var(--muted-foreground)",
        strokeOpacity: active ? 0.9 : faded ? 0.06 : 0.22,
        strokeWidth: active ? 2 : 1.25,
        transition: "stroke-opacity 200ms, stroke 200ms",
      }}
    />
  )
}
