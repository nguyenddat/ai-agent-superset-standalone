import type { ElkNode, ElkPort } from "elkjs/lib/elk-api"

import { CARD_WIDTH, handleY, type Card, type Link } from "./graph"

type Point = { x: number; y: number }

let elkInstance: Promise<{ layout: (graph: ElkNode) => Promise<ElkNode> }> | null = null

// elkjs is large, so it loads on first use as its own chunk.
function loadElk() {
  elkInstance ??= import("elkjs/lib/elk.bundled.js").then((module) => new module.default())
  return elkInstance
}

const LAYOUT_OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.edgeRouting": "SPLINES",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
  "elk.spacing.nodeNode": "36",
  "elk.layered.spacing.nodeNodeBetweenLayers": "120",
  // One layered grid for every table, so all sources share the left columns even when chains are not connected.
  "elk.separateConnectedComponents": "false",
}

/**
 * Lays the lineage out left to right with ELK Layered (Sugiyama), so data flows from sources to targets. Each column
 * a link joins is a port fixed at its row, so ELK orders the cards by the rows the links meet and keeps them from
 * crossing on the way.
 */
export async function layoutLineage(cards: Card[], links: Link[]): Promise<Map<string, Point>> {
  const byId = new Map(cards.map((card) => [card.id, card]))
  const ports = new Map<string, Map<string, ElkPort>>(cards.map((card) => [card.id, new Map()]))
  const portOf = (cardId: string, handle: string, side: "EAST" | "WEST") => {
    const id = `${cardId}|${handle}|${side}`
    ports.get(cardId)!.set(id, {
      id,
      x: side === "EAST" ? CARD_WIDTH : 0,
      y: handleY(byId.get(cardId)!, handle),
      width: 0,
      height: 0,
      layoutOptions: { "elk.port.side": side },
    })
    return id
  }
  const edges = links
    .filter((link) => byId.has(link.source) && byId.has(link.target) && link.source !== link.target)
    .map((link) => ({
      id: link.id,
      sources: [portOf(link.source, link.sourceHandle, "EAST")],
      targets: [portOf(link.target, link.targetHandle, "WEST")],
    }))

  const elk = await loadElk()
  const graph = await elk.layout({
    id: "lineage",
    layoutOptions: LAYOUT_OPTIONS,
    children: cards.map((card) => ({
      id: card.id,
      width: CARD_WIDTH,
      height: card.height,
      ports: [...ports.get(card.id)!.values()],
      layoutOptions: { "elk.portConstraints": "FIXED_POS" },
    })),
    edges,
  })
  return new Map((graph.children ?? []).map((node) => [node.id, { x: Math.round(node.x ?? 0), y: Math.round(node.y ?? 0) }]))
}
