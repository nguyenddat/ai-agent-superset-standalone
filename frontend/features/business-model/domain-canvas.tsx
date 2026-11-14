"use client"

import "@xyflow/react/dist/style.css"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import {
  Background,
  BackgroundVariant,
  MarkerType,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  useStore,
  type OnNodeDrag,
  type XYPosition,
} from "@xyflow/react"
import { HandIcon, Link2Icon, Link2OffIcon, MaximizeIcon, MousePointer2Icon } from "lucide-react"
import { useTheme } from "next-themes"

import { FloatingButtonGroup } from "@/components/floating-button-group"

import {
  CanvasContext,
  DomainRegion,
  LineageLink,
  TableCircle,
  type CanvasHighlight,
  type LineageLinkEdge,
  type RegionNode,
  type TableNode,
} from "./canvas-nodes"
import type { BusinessDomain, BusinessModel } from "./types"
import {
  CELL_HEIGHT,
  CELL_WIDTH,
  NODE_HEIGHT,
  NODE_WIDTH,
  boxContains,
  layoutVenn,
  neighbours,
  nodePosition,
  regionBox,
  type Box,
} from "./venn-layout"

export const TABLE_DRAG_TYPE = "application/x-model-table"

export type ColoredDomain = { domain: BusinessDomain; color: string }
export type CanvasFocus = { nodeIds: string[]; nonce: number }

type DomainCanvasProps = {
  connectionId: string
  model: BusinessModel
  domains: ColoredDomain[]
  focus: CanvasFocus | null
  onEditDomain: (domain: BusinessDomain) => void
  onSetDomains: (tableId: string, domainIds: string[]) => void
}

type CanvasNode = RegionNode | TableNode
type Tool = "select" | "pan"
type DropHint = { tableId: string | null; regions: Set<string> }

export const regionNodeId = (domainId: string) => `region:${domainId}`

const nodeTypes = { region: DomainRegion, table: TableCircle }
const edgeTypes = { lineage: LineageLink }
const FIT_OPTIONS = { padding: 0.12, maxZoom: 1, duration: 400 }

function pointerOf(event: MouseEvent | TouchEvent | React.DragEvent) {
  const point = "touches" in event ? (event.touches[0] ?? event.changedTouches[0]) : event
  return { x: point.clientX, y: point.clientY }
}

const sameSet = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every((item) => b.has(item))

function CanvasView({ connectionId, model, domains, focus, onEditDomain, onSetDomains }: DomainCanvasProps) {
  const router = useRouter()
  const { resolvedTheme } = useTheme()
  const flow = useReactFlow<CanvasNode, LineageLinkEdge>()
  const zoom = useStore((state) => Math.round(state.transform[2] * 100))

  const { nodes: baseNodes, boxes, cells, membership } = useMemo(() => {
    const present = new Set(model.tables.map((table) => table.table_id))
    const owners = new Map<string, ColoredDomain[]>()
    for (const item of domains) {
      for (const id of item.domain.table_ids) if (present.has(id)) owners.set(id, [...(owners.get(id) ?? []), item])
    }
    // Tables outside every domain are drawn only when they are linked to a table in a domain.
    const linked = new Set(
      model.lineage_edges.flatMap((edge) =>
        owners.has(edge.source_table_id) ? [edge.target_table_id] : owners.has(edge.target_table_id) ? [edge.source_table_id] : [],
      ),
    )
    const loose = model.tables.filter((table) => !owners.has(table.table_id) && linked.has(table.table_id))
    const layout = layoutVenn(
      domains.map((item) => item.domain),
      present,
      loose.map((table) => table.table_id),
      model.lineage_edges,
    )
    const layers = new Map(model.layers.map((layer) => [layer.id, layer]))
    const regionBoxes = new Map([...layout.regions].map(([id, region]) => [id, regionBox(region)]))

    const regions = domains.map(({ domain, color }): RegionNode => {
      const box = regionBoxes.get(domain.id)!
      return {
        id: regionNodeId(domain.id),
        type: "region",
        position: { x: box.x, y: box.y },
        width: box.width,
        height: box.height,
        draggable: false,
        selectable: false,
        focusable: false,
        zIndex: 0,
        style: { pointerEvents: "none" },
        data: { domain, color, count: domain.table_ids.filter((id) => present.has(id)).length },
      }
    })
    const tables = model.tables
      .filter((table) => layout.tables.has(table.table_id))
      .map((table): TableNode => {
        const own = owners.get(table.table_id) ?? []
        return {
          id: table.table_id,
          type: "table",
          position: nodePosition(layout.tables.get(table.table_id)!),
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
          zIndex: 1,
          data: {
            table,
            colors: own.map((item) => item.color),
            domainNames: own.map((item) => item.domain.name),
            layer: layers.get(table.layer_id ?? "") ?? null,
          },
        }
      })
    return {
      nodes: [...regions, ...tables] as CanvasNode[],
      boxes: regionBoxes,
      cells: layout.tables,
      membership: new Map([...owners].map(([id, list]) => [id, new Set(list.map((item) => item.domain.id))])),
    }
  }, [model, domains])

  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(baseNodes)
  useEffect(() => setNodes(baseNodes), [baseNodes, setNodes])

  const [showEdges, setShowEdges] = useState(true)
  const [tool, setTool] = useState<Tool>("select")
  const [hoveredTable, setHoveredTable] = useState<string | null>(null)
  const [drop, setDrop] = useState<DropHint | null>(null)
  const dragging = useRef(false)

  const related = useMemo(() => neighbours(model.lineage_edges), [model.lineage_edges])
  const edges = useMemo<LineageLinkEdge[]>(() => {
    if (!showEdges) return []
    const placed = new Set(cells.keys())
    return model.lineage_edges
      .filter((edge) => placed.has(edge.source_table_id) && placed.has(edge.target_table_id))
      .map((edge) => ({
        id: `${edge.source_table_id}:${edge.target_table_id}:${edge.kind}`,
        type: "lineage",
        source: edge.source_table_id,
        target: edge.target_table_id,
        data: { kind: edge.kind },
        selectable: false,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "var(--muted-foreground)" },
      }))
  }, [model.lineage_edges, cells, showEdges])

  useEffect(() => {
    if (focus) flow.fitView({ nodes: focus.nodeIds.map((id) => ({ id })), ...FIT_OPTIONS, padding: 0.35 })
  }, [focus, flow])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (event.metaKey || event.ctrlKey || event.altKey || target.closest("input, textarea, [contenteditable]")) return
      if (event.key === "v" || event.key === "V") setTool("select")
      if (event.key === "h" || event.key === "H") setTool("pan")
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const regionsAt = useCallback(
    (screen: XYPosition) => {
      const point = flow.screenToFlowPosition(screen)
      return { point, regions: new Set([...boxes].filter(([, box]) => boxContains(box, point)).map(([id]) => id)) }
    },
    [flow, boxes],
  )

  const homeCell = (tableId: string): Box => {
    const cell = cells.get(tableId)!
    return { x: cell.col * CELL_WIDTH, y: cell.row * CELL_HEIGHT, width: CELL_WIDTH, height: CELL_HEIGHT }
  }

  const onNodeDragStart: OnNodeDrag<CanvasNode> = () => {
    dragging.current = true
    setHoveredTable(null)
  }
  const onNodeDrag: OnNodeDrag<CanvasNode> = (event, node) => {
    const { regions } = regionsAt(pointerOf(event))
    setDrop((current) => (current && current.tableId === node.id && sameSet(current.regions, regions) ? current : { tableId: node.id, regions }))
  }
  const onNodeDragStop: OnNodeDrag<CanvasNode> = (event, node) => {
    dragging.current = false
    setDrop(null)
    setNodes(baseNodes)
    const { point, regions } = regionsAt(pointerOf(event))
    if (boxContains(homeCell(node.id), point)) return
    if (sameSet(regions, membership.get(node.id) ?? new Set())) return
    onSetDomains(node.id, [...regions])
  }

  const onDragOver = (event: React.DragEvent) => {
    if (!event.dataTransfer.types.includes(TABLE_DRAG_TYPE)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = "copy"
    const { regions } = regionsAt(pointerOf(event))
    setDrop((current) => (current && current.tableId === null && sameSet(current.regions, regions) ? current : { tableId: null, regions }))
  }
  const onDrop = (event: React.DragEvent) => {
    const tableId = event.dataTransfer.getData(TABLE_DRAG_TYPE)
    setDrop(null)
    const { regions } = regionsAt(pointerOf(event))
    if (!tableId || regions.size === 0) return
    event.preventDefault()
    onSetDomains(tableId, [...regions])
  }

  const highlight = useMemo<CanvasHighlight>(
    () => ({
      hoveredTable,
      related: (hoveredTable && related.get(hoveredTable)) || new Set(),
      dropRegions: drop?.regions ?? null,
      setHoveredTable: (tableId) => !dragging.current && setHoveredTable(tableId),
      onEditDomain,
      onOpenTable: (tableId) => router.push(`/connections/${connectionId}/dictionary?table=${tableId}`),
    }),
    [hoveredTable, related, drop, onEditDomain, router, connectionId],
  )

  const names = new Map(domains.map(({ domain }) => [domain.id, domain.name]))
  const dropLabel = drop
    ? drop.regions.size > 0
      ? `Thả vào: ${[...drop.regions].map((id) => names.get(id)).join(" ∩ ")}`
      : drop.tableId
        ? "Thả ra ngoài để bỏ bảng khỏi mọi miền"
        : "Thả vào một miền"
    : null
  const layers = model.layers.filter((layer) => model.tables.some((table) => table.layer_id === layer.id))

  return (
    <CanvasContext.Provider value={highlight}>
      <ReactFlow<CanvasNode, LineageLinkEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onDragOver={onDragOver}
        onDragLeave={() => setDrop((current) => (current?.tableId === null ? null : current))}
        onDrop={onDrop}
        nodesDraggable={tool === "select"}
        elementsSelectable={tool === "select"}
        nodesConnectable={false}
        minZoom={0.25}
        maxZoom={3}
        fitView
        fitViewOptions={FIT_OPTIONS}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        className={tool === "pan" ? "model-canvas cursor-grab" : "model-canvas"}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
        <MiniMap<CanvasNode>
          pannable
          zoomable
          style={{ width: 168, height: 112 }}
          className="hidden overflow-hidden rounded-xl border shadow-sm md:block"
          nodeBorderRadius={24}
          nodeColor={(node) =>
            node.type === "region" ? `${node.data.color}26` : (node.data.colors[0] ?? "#94a3b8")
          }
          nodeStrokeWidth={0}
        />
        {dropLabel ? (
          <Panel position="top-center" className="mt-12">
            <span className="rounded-full border bg-popover px-3 py-1.5 text-xs font-medium text-popover-foreground shadow-md">
              {dropLabel}
            </span>
          </Panel>
        ) : null}
        {layers.length > 0 ? (
          <Panel position="bottom-left" className="hidden max-w-xs rounded-xl border bg-card/90 p-2.5 shadow-sm backdrop-blur sm:block">
            <p className="mb-1.5 text-[11px] font-medium text-muted-foreground uppercase">Tầng dữ liệu</p>
            <ul className="flex flex-wrap gap-x-3 gap-y-1">
              {layers.map((layer) => (
                <li key={layer.id} className="flex items-center gap-1.5 text-xs">
                  <span className="size-2.5 rounded-full" style={{ background: layer.color ?? "var(--border)" }} />
                  {layer.name}
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}
        <Panel position="bottom-center">
          <FloatingButtonGroup
            label="Công cụ canvas"
            activeId={tool}
            onToolSelect={(id) => setTool(id as Tool)}
            tools={[
              { id: "select", label: "Chọn và kéo", icon: <MousePointer2Icon size={14} />, shortcut: "V" },
              { id: "pan", label: "Di chuyển màn hình", icon: <HandIcon size={14} />, shortcut: "H" },
            ]}
            zoomValue={zoom}
            onZoomChange={(value) => flow.zoomTo(value / 100, { duration: 200 })}
            menuItems={[
              { id: "fit", label: "Vừa khung hình", icon: <MaximizeIcon size={14} />, onSelect: () => flow.fitView(FIT_OPTIONS) },
              {
                id: "edges",
                label: showEdges ? "Ẩn quan hệ" : "Hiện quan hệ",
                icon: showEdges ? <Link2OffIcon size={14} /> : <Link2Icon size={14} />,
                onSelect: () => setShowEdges((value) => !value),
              },
            ]}
            className="shadow-lg"
          />
        </Panel>
      </ReactFlow>
    </CanvasContext.Provider>
  )
}

export function DomainCanvas(props: DomainCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasView {...props} />
    </ReactFlowProvider>
  )
}
