"use client"

import "@xyflow/react/dist/style.css"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  Background,
  BackgroundVariant,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
  useStore,
} from "@xyflow/react"
import { HandIcon, MaximizeIcon, MousePointer2Icon, XIcon } from "lucide-react"
import { useTheme } from "next-themes"

import { FloatingButtonGroup } from "@/components/floating-button-group"
import { SegmentedControl } from "@/components/segmented-control"
import { Button } from "@/components/ui/button"

import { layoutLineage } from "./elk-layout"
import { DETAIL_LEVELS, type Card, type DetailLevel, type Link } from "./graph"
import { ROLES, ROLE_STROKE } from "./labels"
import {
  LineageContext,
  LineageLink,
  TableCard,
  type CardNode,
  type LineageCanvasState,
  type LinkEdge,
} from "./lineage-nodes"

const nodeTypes = { card: TableCard }
const edgeTypes = { link: LineageLink }
const FIT_OPTIONS = { padding: 0.15, maxZoom: 1.1, duration: 320 }
const MIN_READABLE_ZOOM = 0.55
const FRAME_PADDING = 48

type Tool = "select" | "pan"

export type CanvasFocus = { tableIds: string[]; nonce: number }

type LineageCanvasProps = {
  cards: Card[]
  links: Link[]
  detail: DetailLevel
  onDetailChange: (detail: DetailLevel) => void
  selectedTable: string | null
  selectionLabel: string | null
  focus: CanvasFocus | null
  state: Omit<LineageCanvasState, "hoveredLink">
  onSelectTable: (tableId: string | null) => void
  onSelectTransformation: (transformationId: string) => void
  onClearSelection: () => void
}

function CanvasView({
  cards,
  links,
  detail,
  onDetailChange,
  selectedTable,
  selectionLabel,
  focus,
  state,
  onSelectTable,
  onSelectTransformation,
  onClearSelection,
}: LineageCanvasProps) {
  const { resolvedTheme } = useTheme()
  const flow = useReactFlow<CardNode, LinkEdge>()
  const zoom = useStore((store) => Math.round(store.transform[2] * 100))
  const [tool, setTool] = useState<Tool>("select")
  const [hoveredLink, setHoveredLink] = useState<string | null>(null)
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }> | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState<CardNode>([])
  const fitted = useRef<Map<string, { x: number; y: number }> | null>(null)

  // Only a change of cards, rows or links lays the graph out again; a new highlight keeps every card where it is.
  const shape = useMemo(
    () => JSON.stringify([cards.map((card) => [card.id, card.height]), links.map((link) => link.id)]),
    [cards, links],
  )
  useEffect(() => {
    let current = true
    void layoutLineage(cards, links).then((result) => current && setPositions(result))
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `shape` stands for cards and links.
  }, [shape])

  // A new layout places every card; otherwise cards keep where the user dragged them.
  const applied = useRef<typeof positions>(null)
  useEffect(() => {
    if (!positions) return
    const fresh = applied.current !== positions
    applied.current = positions
    setNodes((current) => {
      const previous = new Map(current.map((node) => [node.id, node]))
      return cards.map((card) => ({
        id: card.id,
        type: "card",
        position: (!fresh && previous.get(card.id)?.position) || positions.get(card.id) || { x: 0, y: 0 },
        data: { card },
        selected: card.id === selectedTable,
      }))
    })
  }, [cards, positions, selectedTable, setNodes])

  // Frames cards at a zoom where column rows stay readable: a graph taller than the view starts at its top instead of
  // shrinking until nothing can be read.
  const width = useStore((store) => store.width)
  const height = useStore((store) => store.height)
  const frame = useCallback(
    (tableIds?: string[]) => {
      const bounds = flow.getNodesBounds(tableIds ?? flow.getNodes().map((node) => node.id))
      if (!bounds.width || !width || !height) return
      const zoom = Math.min(
        FIT_OPTIONS.maxZoom,
        Math.max(MIN_READABLE_ZOOM, Math.min((width - 2 * FRAME_PADDING) / bounds.width, (height - 2 * FRAME_PADDING) / bounds.height)),
      )
      const x = width / 2 - (bounds.x + bounds.width / 2) * zoom
      const y =
        bounds.height * zoom > height - 2 * FRAME_PADDING
          ? FRAME_PADDING + 40 - bounds.y * zoom
          : height / 2 - (bounds.y + bounds.height / 2) * zoom
      void flow.setViewport({ x, y, zoom }, { duration: FIT_OPTIONS.duration })
    },
    [flow, width, height],
  )

  // A new layout can change card heights (columns load, or the detail level changes); React Flow measures them on the
  // next frames, so the fit waits for that to frame their real size.
  const measured = useNodesInitialized()
  useEffect(() => {
    if (!positions || !measured || fitted.current === positions) return
    const timer = window.setTimeout(() => {
      fitted.current = positions
      frame()
    }, 120)
    return () => window.clearTimeout(timer)
  }, [positions, measured, frame])

  useEffect(() => {
    if (focus?.tableIds.length) frame(focus.tableIds)
  }, [focus, frame])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLElement && event.target.closest("input, textarea, [contenteditable]")) return
      if (event.key === "v" || event.key === "V") setTool("select")
      else if (event.key === "h" || event.key === "H") setTool("pan")
      else if (event.key === "Escape") onClearSelection()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClearSelection])

  const edges = useMemo<LinkEdge[]>(
    () =>
      links.map((link) => ({
        id: link.id,
        type: "link",
        source: link.source,
        target: link.target,
        sourceHandle: link.sourceHandle,
        targetHandle: link.targetHandle,
        data: { link },
      })),
    [links],
  )

  const usedRoles = ROLES.filter((role) => links.some((link) => link.role === role.value))

  return (
    <LineageContext.Provider value={{ ...state, hoveredLink }}>
      <ReactFlow<CardNode, LinkEdge>
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onNodeClick={(_, node) => onSelectTable(node.id)}
        onEdgeClick={(_, edge) => edge.data?.link.transformationId && onSelectTransformation(edge.data.link.transformationId)}
        onEdgeMouseEnter={(_, edge) => setHoveredLink(edge.id)}
        onEdgeMouseLeave={() => setHoveredLink(null)}
        onPaneClick={onClearSelection}
        nodesDraggable={tool === "select"}
        elementsSelectable={tool === "select"}
        panOnDrag={tool === "pan" ? true : [1, 2]}
        selectionOnDrag={false}
        nodesConnectable={false}
        minZoom={0.15}
        maxZoom={2.5}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
        className={tool === "pan" ? "lineage-canvas cursor-grab" : "lineage-canvas"}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} />
        <MiniMap<CardNode>
          pannable
          zoomable
          style={{ width: 168, height: 112 }}
          className="hidden overflow-hidden rounded-xl border shadow-sm md:block"
          nodeBorderRadius={8}
          nodeColor={(node) => (state.highlight && !state.highlight.tables.has(node.id) ? "#94a3b833" : "#94a3b8")}
          nodeStrokeWidth={0}
        />

        <Panel position="top-left" className="flex flex-wrap items-center gap-2">
          <SegmentedControl
            label="Mức chi tiết"
            size="sm"
            value={detail}
            onValueChange={(value) => onDetailChange(value as DetailLevel)}
            options={DETAIL_LEVELS}
            className="bg-card/90 shadow-sm backdrop-blur"
          />
        </Panel>

        {selectionLabel ? (
          <Panel position="top-center" className="mt-12 sm:mt-0">
            <span className="flex items-center gap-1 rounded-full border bg-popover py-1 pr-1 pl-3 text-xs font-medium text-popover-foreground shadow-md">
              {selectionLabel}
              <Button variant="ghost" size="icon-xs" className="rounded-full" aria-label="Bỏ chọn (Esc)" onClick={onClearSelection}>
                <XIcon />
              </Button>
            </span>
          </Panel>
        ) : null}

        {usedRoles.length > 0 ? (
          <Panel position="bottom-left" className="hidden rounded-xl border bg-card/90 p-2.5 shadow-sm backdrop-blur sm:block">
            <p className="mb-1.5 text-[11px] font-medium text-muted-foreground uppercase">Vai trò cột</p>
            <ul className="flex flex-col gap-1">
              {usedRoles.map((role) => (
                <li key={role.value} className="flex items-center gap-2 text-xs" title={role.hint}>
                  <svg width="28" height="6" aria-hidden className="shrink-0">
                    <line
                      x1="1"
                      x2="27"
                      y1="3"
                      y2="3"
                      strokeWidth="2"
                      style={{ stroke: ROLE_STROKE[role.value].color }}
                      strokeDasharray={ROLE_STROKE[role.value].dash}
                    />
                  </svg>
                  {role.label}
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
            ]}
            className="shadow-lg"
          />
        </Panel>
      </ReactFlow>
    </LineageContext.Provider>
  )
}

export function LineageCanvas(props: LineageCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasView {...props} />
    </ReactFlowProvider>
  )
}
