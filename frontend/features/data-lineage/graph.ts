import type { DataLayer, ModelTable } from "../business-model/types"
import type { DependencyRole, GraphEdge, LineageColumn } from "./types"

/** How much of each table the cards show: the name only, the columns lineage touches, or every column. */
export type DetailLevel = "tables" | "linked" | "all"

export const DETAIL_LEVELS: { value: DetailLevel; label: string }[] = [
  { value: "tables", label: "Bảng" },
  { value: "linked", label: "Cột liên quan" },
  { value: "all", label: "Tất cả cột" },
]

export const CARD_WIDTH = 272
export const CARD_HEADER = 58
export const CARD_ROW = 28
export const CARD_MORE = 26

export type Card = {
  id: string
  table: ModelTable
  layer: DataLayer | null
  rows: LineageColumn[]
  hidden: number
  height: number
}

export type Link = {
  id: string
  source: string
  target: string
  sourceHandle: string
  targetHandle: string
  /** Null for a link between two tables rather than two columns. */
  role: DependencyRole | null
  transformationId: string | null
  kind: GraphEdge["kind"]
  /** `source>target` column ids, matched against a column trace. */
  columnKey: string | null
}

export const headerHandle = (side: "in" | "out") => `h:${side}`
export const columnHandle = (columnId: string, side: "in" | "out") => `c:${columnId}:${side}`

/** Height on a card where a handle sits: the middle of its row, or of the header. */
export function handleY(card: Card, handle: string) {
  const index = card.rows.findIndex((row) => handle.startsWith(`c:${row.column_id}:`))
  return index < 0 ? CARD_HEADER / 2 : CARD_HEADER + index * CARD_ROW + CARD_ROW / 2
}

const tableKey = (edge: GraphEdge) => `t:${edge.transformation_id ?? "flow"}:${edge.source_table_id}:${edge.target_table_id}`

export function buildLineage(
  edges: GraphEdge[],
  tables: Map<string, ModelTable>,
  layers: DataLayer[],
  columns: Map<string, LineageColumn[]> | undefined,
  detail: DetailLevel,
) {
  const tableIds = [...new Set(edges.flatMap((edge) => [edge.source_table_id, edge.target_table_id]))].filter((id) =>
    tables.has(id),
  )
  const involved = new Set(
    edges.flatMap((edge) => edge.dependencies.flatMap((dep) => [dep.source_column_id, dep.target_column_id ?? ""])),
  )

  const cards = tableIds.map<Card>((id) => {
    const all = columns?.get(id) ?? []
    const rows = detail === "all" ? all : detail === "linked" ? all.filter((column) => involved.has(column.column_id)) : []
    const hidden = detail === "linked" ? all.length - rows.length : 0
    const table = tables.get(id)!
    return {
      id,
      table,
      layer: layers.find((layer) => layer.id === table.layer_id) ?? null,
      rows,
      hidden,
      height: CARD_HEADER + rows.length * CARD_ROW + (hidden > 0 ? CARD_MORE : 0) + 2,
    }
  })
  const shown = new Set(cards.flatMap((card) => card.rows.map((row) => row.column_id)))

  const links = new Map<string, Link>()
  for (const edge of edges) {
    if (!tables.has(edge.source_table_id) || !tables.has(edge.target_table_id)) continue
    const columnLinks = detail !== "tables" && edge.dependencies.length > 0
    if (!columnLinks) {
      links.set(tableKey(edge), {
        id: tableKey(edge),
        source: edge.source_table_id,
        target: edge.target_table_id,
        sourceHandle: headerHandle("out"),
        targetHandle: headerHandle("in"),
        role: null,
        transformationId: edge.transformation_id,
        kind: edge.kind,
        columnKey: null,
      })
      continue
    }
    for (const dep of edge.dependencies) {
      const id = `d:${edge.transformation_id}:${dep.source_column_id}:${dep.target_column_id ?? "h"}:${dep.role}`
      links.set(id, {
        id,
        source: edge.source_table_id,
        target: edge.target_table_id,
        sourceHandle: shown.has(dep.source_column_id) ? columnHandle(dep.source_column_id, "out") : headerHandle("out"),
        targetHandle:
          dep.target_column_id && shown.has(dep.target_column_id)
            ? columnHandle(dep.target_column_id, "in")
            : headerHandle("in"),
        role: dep.role,
        transformationId: edge.transformation_id,
        kind: edge.kind,
        columnKey: `${dep.source_column_id}>${dep.target_column_id ?? ""}`,
      })
    }
  }
  return { cards, links: [...links.values()] }
}

export type Highlight = {
  tables: Set<string>
  columns: Set<string>
  /** Table pairs (`source>target`) and column pairs a trace runs along. */
  tablePairs: Set<string>
  columnPairs: Set<string>
  transformationId: string | null
  /** For a selected table, how each lit table relates to it. */
  neighbours?: Map<string, "parent" | "child">
}

function walk(start: string, next: (id: string) => string[]) {
  const seen = new Set([start])
  const queue = [start]
  while (queue.length) {
    for (const id of next(queue.shift()!)) {
      if (seen.has(id)) continue
      seen.add(id)
      queue.push(id)
    }
  }
  return seen
}

/**
 * One table with only its direct parents (the tables it is built from) and direct children (the tables built from
 * it); everything further away stays in the background so a busy graph still reads at a glance.
 */
export function traceTable(edges: GraphEdge[], tableId: string): Highlight {
  const own = edges.filter((e) => e.target_table_id === tableId || e.source_table_id === tableId)
  const neighbours = new Map<string, "parent" | "child">()
  for (const e of own) {
    if (e.target_table_id === tableId && e.source_table_id !== tableId) neighbours.set(e.source_table_id, "parent")
    if (e.source_table_id === tableId && e.target_table_id !== tableId) neighbours.set(e.target_table_id, "child")
  }
  return {
    tables: new Set([tableId, ...neighbours.keys()]),
    columns: new Set(),
    tablePairs: new Set(own.map((e) => `${e.source_table_id}>${e.target_table_id}`)),
    columnPairs: new Set(),
    transformationId: null,
    neighbours,
  }
}

/**
 * The columns a column is computed from and the ones computed from it. Value and group links carry a column on;
 * join and filter links only shape the rows, so they are shown for the columns they lead into but not followed.
 */
export function traceColumn(edges: GraphEdge[], columnTable: Map<string, string>, columnId: string): Highlight {
  const deps = edges.flatMap((edge) => edge.dependencies)
  const carries = deps.filter((dep) => dep.target_column_id && (dep.role === "value" || dep.role === "group"))
  const up = walk(columnId, (id) => carries.filter((d) => d.target_column_id === id).map((d) => d.source_column_id))
  const down = walk(columnId, (id) => carries.filter((d) => d.source_column_id === id).map((d) => d.target_column_id!))
  const columns = new Set([...up, ...down])
  const columnPairs = new Set(
    carries
      .filter(
        (d) =>
          (up.has(d.source_column_id) && up.has(d.target_column_id!)) ||
          (down.has(d.source_column_id) && down.has(d.target_column_id!)),
      )
      .map((d) => `${d.source_column_id}>${d.target_column_id}`),
  )
  const tables = new Set([...columns].flatMap((id) => columnTable.get(id) ?? []))
  return { tables, columns, tablePairs: new Set(), columnPairs, transformationId: null }
}

export function traceTransformation(edges: GraphEdge[], transformationId: string): Highlight {
  const own = edges.filter((edge) => edge.transformation_id === transformationId)
  return {
    tables: new Set(own.flatMap((edge) => [edge.source_table_id, edge.target_table_id])),
    columns: new Set(own.flatMap((edge) => edge.dependencies.flatMap((d) => [d.source_column_id, d.target_column_id ?? ""]))),
    tablePairs: new Set(own.map((edge) => `${edge.source_table_id}>${edge.target_table_id}`)),
    columnPairs: new Set(),
    transformationId,
  }
}

export function linkLit(link: Link, highlight: Highlight) {
  if (highlight.transformationId) return link.transformationId === highlight.transformationId
  if (highlight.columnPairs.size || highlight.columns.size) return !!link.columnKey && highlight.columnPairs.has(link.columnKey)
  return highlight.tablePairs.has(`${link.source}>${link.target}`)
}
