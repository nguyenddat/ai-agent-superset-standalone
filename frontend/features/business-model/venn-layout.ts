import type { BusinessDomain, LineageEdge } from "./types"

export const CELL_WIDTH = 136
export const CELL_HEIGHT = 136
export const NODE_WIDTH = 120
export const NODE_HEIGHT = 92
export const NODE_TOP = 30
export const CIRCLE_SIZE = 52
const MAX_COLUMNS = 14
const MAX_ROWS = 4

export const DOMAIN_COLORS = ["#2563eb", "#0d9488", "#d97706", "#db2777", "#7c3aed", "#059669", "#dc2626", "#0891b2"]

export type Point = { x: number; y: number }
export type Box = Point & { width: number; height: number }
export type Cell = { col: number; row: number }
type Rect = Cell & { columns: number; rows: number }

/** A domain's area: a rectangle of cells. `depth` alternates along a chain so the outlines of two overlapping domains never coincide. */
export type Region = { rect: Rect; depth: number }

export type VennLayout = { regions: Map<string, Region>; tables: Map<string, Cell> }

export function domainColor(domain: BusinessDomain, index: number) {
  return domain.color ?? DOMAIN_COLORS[index % DOMAIN_COLORS.length]
}

const pairKey = (a: string, b: string) => (a < b ? `${a}|${b}` : `${b}|${a}`)

function sharedCounts(owners: Map<string, string[]>) {
  const counts = new Map<string, number>()
  for (const domains of owners.values()) {
    for (let i = 0; i < domains.length; i += 1) {
      for (let j = i + 1; j < domains.length; j += 1) {
        const key = pairKey(domains[i], domains[j])
        counts.set(key, (counts.get(key) ?? 0) + 1)
      }
    }
  }
  return counts
}

/**
 * Orders the domains into chains in which each domain shares tables with the next one, following the largest share
 * first. Two domains next to each other in a chain overlap on the canvas, so their shared tables sit in the overlap.
 */
function domainChains(domainIds: string[], shared: Map<string, number>): string[][] {
  const neighbours = (id: string, pool: Set<string>) =>
    [...pool].filter((other) => other !== id && (shared.get(pairKey(id, other)) ?? 0) > 0)
  const remaining = new Set(domainIds)
  const chains: string[][] = []
  while (remaining.size > 0) {
    const start = [...remaining].sort((a, b) => neighbours(a, remaining).length - neighbours(b, remaining).length)[0]
    const chain = [start]
    remaining.delete(start)
    for (;;) {
      const last = chain[chain.length - 1]
      const next = neighbours(last, remaining).sort(
        (a, b) => (shared.get(pairKey(last, b)) ?? 0) - (shared.get(pairKey(last, a)) ?? 0),
      )[0]
      if (!next) break
      chain.push(next)
      remaining.delete(next)
    }
    chains.push(chain)
  }
  return chains
}

type Block = { domains: string[]; tables: string[] }

/**
 * Places every table once. A chain is a row of blocks: each domain's own tables, then the tables it shares with the
 * next domain, and so on; a domain covers the columns from the block it shares with the previous domain to the block
 * it shares with the next. A table whose domains are not neighbours in a chain stays in the overlap of two of them, or
 * with the first of its domains. Tables outside every domain (`loose`) go in rows below.
 */
export function layoutVenn(
  domains: BusinessDomain[],
  present: Set<string>,
  loose: string[],
  edges: LineageEdge[],
): VennLayout {
  const domainIds = domains.map((domain) => domain.id)
  const owners = new Map<string, string[]>()
  for (const domain of domains) {
    for (const id of domain.table_ids) if (present.has(id)) owners.set(id, [...(owners.get(id) ?? []), domain.id])
  }
  const chains = domainChains(domainIds, sharedCounts(owners))
  const chainOf = new Map(chains.flatMap((chain, index) => chain.map((id) => [id, index] as const)))

  const blocks = chains.map((chain) =>
    chain.flatMap((id, index): Block[] => [
      { domains: [id], tables: [] },
      ...(index < chain.length - 1 ? [{ domains: [id, chain[index + 1]], tables: [] }] : []),
    ]),
  )
  const blockFor = (signature: string[]) => {
    const chain = blocks[chainOf.get(signature[0])!]
    const pair = chain.find((block) => block.domains.length === 2 && block.domains.every((id) => signature.includes(id)))
    if (pair && signature.every((id) => chainOf.get(id) === chainOf.get(signature[0]))) return pair
    return chain.find((block) => block.domains.length === 1 && block.domains[0] === signature[0])!
  }
  for (const [tableId, signature] of owners) blockFor(signature).tables.push(tableId)

  const regions = new Map<string, Region>()
  const tables = new Map<string, Cell>()
  const slots: Slots[] = []
  let cursor = { col: 0, row: 0 }
  let bandRows = 0
  chains.forEach((chain, chainIndex) => {
    const chainBlocks = blocks[chainIndex]
    const largest = Math.max(1, ...chainBlocks.map((block) => block.tables.length))
    const rows = Math.min(MAX_ROWS, Math.ceil(Math.sqrt(largest)))
    // A domain keeps at least one column of its own when it shares no table with its neighbours, so it is never empty.
    const widths = chainBlocks.map((block, index) => {
      const columns = Math.ceil(block.tables.length / rows)
      const alone = block.domains.length === 1 && !chainBlocks[index - 1]?.tables.length && !chainBlocks[index + 1]?.tables.length
      return alone ? Math.max(columns, 1) : columns
    })
    const width = widths.reduce((sum, value) => sum + value, 0)
    if (cursor.col > 0 && cursor.col + width > MAX_COLUMNS) {
      cursor = { col: 0, row: cursor.row + bandRows + 1 }
      bandRows = 0
    }
    let col = cursor.col
    const spans = new Map<string, { from: number; to: number }>()
    chainBlocks.forEach((block, index) => {
      const slot = { col, row: cursor.row, rows, tables: block.tables }
      fillSlots(slot, block.tables, tables)
      slots.push(slot)
      for (const id of widths[index] > 0 ? block.domains : []) {
        spans.set(id, { from: spans.get(id)?.from ?? col, to: col + widths[index] })
      }
      col += widths[index]
    })
    chain.forEach((id, index) => {
      const span = spans.get(id)!
      regions.set(id, {
        rect: { col: span.from, row: cursor.row, columns: Math.max(1, span.to - span.from), rows },
        depth: index % 2,
      })
    })
    cursor = { col: col + 1, row: cursor.row }
    bandRows = Math.max(bandRows, rows)
  })

  // Half a row below the domains: close enough to read as context, clear of every outline.
  const looseRow = regions.size > 0 ? cursor.row + bandRows + 0.5 : 0
  const links = neighbours(edges)
  for (let round = 0; round < REFINE_ROUNDS; round += 1) {
    for (const slot of slots) orderSlot(slot, links, tables)
    placeLoose(loose, looseRow, links, tables)
  }
  return { regions, tables }
}

const REFINE_ROUNDS = 4

type Slots = Cell & { rows: number; tables: string[] }

function fillSlots(slot: Slots, ordered: string[], tables: Map<string, Cell>) {
  ordered.forEach((tableId, position) =>
    tables.set(tableId, { col: slot.col + Math.floor(position / slot.rows), row: slot.row + (position % slot.rows) }),
  )
}

/** The mean position of the placed tables linked to `tableId` on one axis, or its own position when none is placed. */
function barycenter(tableId: string, axis: keyof Cell, links: Map<string, Set<string>>, tables: Map<string, Cell>) {
  const placed = [...(links.get(tableId) ?? [])].flatMap((id) => tables.get(id) ?? [])
  if (placed.length === 0) return tables.get(tableId)?.[axis] ?? 0
  return placed.reduce((sum, cell) => sum + cell[axis], 0) / placed.length
}

/**
 * Barycenter heuristic, as in layered graph drawing: a block's tables are sorted by the mean column of their linked
 * tables and fill its columns from left to right, then each column is sorted by the mean row. Tables end up on the
 * side of the block facing what they link to, which shortens edges and removes most crossings.
 */
function orderSlot(slot: Slots, links: Map<string, Set<string>>, tables: Map<string, Cell>) {
  const byCol = [...slot.tables].sort(
    (a, b) => barycenter(a, "col", links, tables) - barycenter(b, "col", links, tables),
  )
  const ordered: string[] = []
  for (let start = 0; start < byCol.length; start += slot.rows) {
    const column = byCol.slice(start, start + slot.rows)
    ordered.push(...column.sort((a, b) => barycenter(a, "row", links, tables) - barycenter(b, "row", links, tables)))
  }
  fillSlots(slot, ordered, tables)
}

/** Puts each table outside the domains in the row below them, in the free column nearest the tables it links to. */
function placeLoose(loose: string[], row: number, links: Map<string, Set<string>>, tables: Map<string, Cell>) {
  for (const id of loose) tables.delete(id)
  const wanted = loose
    .map((id) => ({ id, col: Math.max(0, Math.round(barycenter(id, "col", links, tables))) }))
    .sort((a, b) => a.col - b.col)
  const taken = new Set<number>()
  for (const { id, col } of wanted) {
    let free = col
    for (let step = 1; taken.has(free); step += 1) free = !taken.has(col + step) ? col + step : Math.max(0, col - step)
    taken.add(free)
    tables.set(id, { col: free, row })
  }
}

export function regionBox({ rect, depth }: Region): Box {
  const inset = 6 + depth * 10
  return {
    x: rect.col * CELL_WIDTH + inset,
    y: rect.row * CELL_HEIGHT + inset,
    width: rect.columns * CELL_WIDTH - inset * 2,
    height: rect.rows * CELL_HEIGHT - inset * 2,
  }
}

export function nodePosition(cell: Cell): Point {
  return { x: cell.col * CELL_WIDTH + (CELL_WIDTH - NODE_WIDTH) / 2, y: cell.row * CELL_HEIGHT + NODE_TOP }
}

export const boxContains = (box: Box, point: Point) =>
  point.x >= box.x && point.x <= box.x + box.width && point.y >= box.y && point.y <= box.y + box.height

/** Every table that shares a lineage edge with each table. */
export function neighbours(edges: LineageEdge[]): Map<string, Set<string>> {
  const result = new Map<string, Set<string>>()
  const link = (from: string, to: string) => result.set(from, (result.get(from) ?? new Set()).add(to))
  for (const edge of edges) {
    link(edge.source_table_id, edge.target_table_id)
    link(edge.target_table_id, edge.source_table_id)
  }
  return result
}
