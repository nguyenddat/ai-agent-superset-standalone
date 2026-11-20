"use client"

import { useMemo, type ReactElement, type SVGProps } from "react"
import { Sankey, SunburstChart, Tooltip, Treemap, type TooltipContentProps } from "recharts"

import { buildChartData, sankeyData, tree, tokenAt, type TreeNode } from "../data"
import { tokenColor } from "../palette"
import {
  chartHeight,
  Empty,
  measureText,
  ValueTip,
  WithLegend,
  yMeasure,
  type LegendItem,
  type RendererProps,
} from "./common"

type ColoredNode = TreeNode & { fill: string; children?: ColoredNode[] }

// Top-level groups take the palette in order; past eight they share the muted tone instead of new hues.
function colorTree(nodes: TreeNode[]): ColoredNode[] {
  const paint = (node: TreeNode, fill: string): ColoredNode => ({
    ...node,
    fill,
    children: node.children?.map((child) => paint(child, fill)),
  })
  return nodes.map((node, index) => paint(node, index < 8 ? tokenColor(tokenAt(index)) : "var(--chart-muted)"))
}

type Box = { x?: number; y?: number; width?: number; height?: number }
type CellProps = Box & { name?: string; depth?: number; fill?: string; value?: number }

function sortTree(nodes: ColoredNode[]): ColoredNode[] {
  return [...nodes]
    .sort((left, right) => right.value - left.value)
    .map((node) => (node.children ? { ...node, children: sortTree(node.children) } : node))
}

function treemapCell(leafDepth: number, valueText: (value?: number) => string) {
  return function TreemapCell(props: unknown): ReactElement {
    const { x = 0, y = 0, width = 0, height = 0, name, depth = 0, fill, value } = props as CellProps
    const leaf = depth >= leafDepth
    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          rx={leaf ? 3 : 0}
          fill={leaf ? fill : "transparent"}
          fillOpacity={leaf ? 0.85 : 0}
          stroke="var(--card)"
          strokeWidth={leaf ? 2 : 0}
        />
        {leaf && width > 48 && height > 20 && (
          <text x={x + 6} y={y + 15} fontSize={11} fill="#fff" style={{ textShadow: "0 0 2px rgb(0 0 0 / 0.5)" }}>
            {name && name.length > width / 7 ? `${name.slice(0, Math.max(1, Math.floor(width / 7) - 1))}…` : name}
          </text>
        )}
        {leaf && width > 56 && height > 38 && (
          <text
            x={x + 6}
            y={y + 30}
            fontSize={11}
            fill="#fff"
            fillOpacity={0.85}
            style={{ textShadow: "0 0 2px rgb(0 0 0 / 0.5)" }}
          >
            {valueText(value)}
          </text>
        )}
      </g>
    )
  }
}

export function TreemapRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const levels = [...(spec.encoding?.path ?? []).map((_, index) => `path${index}`), "x"]
  // One level: the cell's own label names it, so one hue keeps the colour from implying groups.
  const flat = levels.length === 1
  const colored = colorTree(tree(built.ctx.prepared.cells, levels))
  const nodes = sortTree(flat ? colored.map((node) => ({ ...node, fill: tokenColor("series-1") })) : colored)
  if (!nodes.length) return <Empty />
  const def = yMeasure(spec, fields)
  const items: LegendItem[] = !flat ? nodes.map((node) => ({ key: node.name, label: node.name, color: node.fill })) : []
  return (
    <WithLegend spec={spec} items={props.compact ? [] : items}>
      <Treemap
        width="100%"
        height={chartHeight(props, 300)}
        data={nodes}
        dataKey="value"
        nameKey="name"
        aspectRatio={4 / 3}
        isAnimationActive={false}
        content={treemapCell(levels.length, (value) => (value == null ? "" : measureText(spec, def, value)))}
      >
        <Tooltip
          content={({ active, payload }: TooltipContentProps) => {
            const node = payload?.[0]?.payload as CellProps | undefined
            if (!active || !node) return null
            return <ValueTip title={node.name} spec={spec} def={def} value={node.value} />
          }}
        />
      </Treemap>
    </WithLegend>
  )
}

export function SunburstRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const levels = (spec.encoding?.path ?? []).map((_, index) => `path${index}`)
  const nodes = colorTree(tree(built.ctx.prepared.cells, levels))
  if (!nodes.length) return <Empty />
  const def = yMeasure(spec, fields)
  const total = nodes.reduce((sum, node) => sum + node.value, 0)
  const items: LegendItem[] = nodes.map((node) => ({ key: node.name, label: node.name, color: node.fill }))
  return (
    <WithLegend
      spec={{ ...spec, legend: { show: "show", position: spec.legend?.position ?? "right" } }}
      items={props.compact ? [] : items}
    >
      <SunburstChart
        responsive
        style={{ width: "100%", height: chartHeight(props, 300) }}
        data={{ name: "Tổng", value: total, children: nodes, fill: "transparent" }}
        dataKey="value"
        innerRadius={36}
        ringPadding={2}
        stroke="var(--card)"
        textOptions={{ fontSize: 0 }}
      >
        <Tooltip
          content={({ active, payload }: TooltipContentProps) => {
            const node = payload?.[0]?.payload as TreeNode | undefined
            if (!active || !node) return null
            return <ValueTip title={node.name} spec={spec} def={def} value={node.value} />
          }}
        />
      </SunburstChart>
    </WithLegend>
  )
}

type NodeProps = Box & { index?: number; payload?: { name?: string; value?: number } }
type LinkProps = {
  sourceX?: number
  targetX?: number
  sourceY?: number
  targetY?: number
  sourceControlX?: number
  targetControlX?: number
  linkWidth?: number
  index?: number
  payload?: { source?: { name?: string }; target?: { name?: string } }
}

export function SankeyRenderer(props: RendererProps) {
  const { spec, fields, rows } = props
  const built = useMemo(() => buildChartData(spec, fields, rows), [spec, fields, rows])
  const data = sankeyData(built.ctx.prepared.cells)
  if (!data.links.length) return <Empty />
  const def = yMeasure(spec, fields)
  const sources = new Set(data.links.map((link) => link.source))
  const colorOf = (index: number) => {
    const order = [...sources].indexOf(index)
    return order >= 0 && order < 8 ? tokenColor(tokenAt(order)) : "var(--chart-muted)"
  }
  const Node = (node: unknown): ReactElement => {
    const { x = 0, y = 0, width = 0, height = 0, index = 0, payload } = node as NodeProps
    const left = x < 120
    return (
      <g>
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          rx={2}
          fill={sources.has(index) ? colorOf(index) : "var(--muted-foreground)"}
        />
        <text
          x={left ? x + width + 6 : x - 6}
          y={y + height / 2}
          fontSize={11}
          textAnchor={left ? "start" : "end"}
          dominantBaseline="middle"
          fill="var(--foreground)"
        >
          {payload?.name}
        </text>
      </g>
    )
  }
  const Link = (link: unknown): ReactElement<SVGProps<SVGPathElement>> => {
    const { sourceX = 0, targetX = 0, sourceY = 0, targetY = 0 } = link as LinkProps
    const { sourceControlX = 0, targetControlX = 0, linkWidth = 0, index = 0 } = link as LinkProps
    const source = data.links[index]?.source ?? 0
    return (
      <path
        d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
        fill="none"
        stroke={colorOf(source)}
        strokeOpacity={0.3}
        strokeWidth={Math.max(1, linkWidth)}
      />
    )
  }
  return (
    <Sankey
      width="100%"
      height={chartHeight(props, 320)}
      data={data}
      nodePadding={14}
      nodeWidth={10}
      margin={{ top: 8, right: 8, bottom: 8, left: 8 }}
      node={Node}
      link={Link}
    >
      <Tooltip
        content={({ active, payload }: TooltipContentProps) => {
          type Inner = LinkProps["payload"] & { value?: number; name?: string }
          const item = payload?.[0]?.payload as { payload?: Inner } | undefined
          if (!active || !item?.payload) return null
          const inner = item.payload
          const pair = inner.source?.name && inner.target?.name
          const title = pair ? `${inner.source!.name} → ${inner.target!.name}` : inner.name
          return <ValueTip title={title} spec={spec} def={def} value={inner.value} />
        }}
      />
    </Sankey>
  )
}
