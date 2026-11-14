import type { TableKind } from "../data-dictionary/types"

export type DataLayer = {
  id: string
  name: string
  description: string | null
  color: string | null
  level: number
  sort_order: number
}

export type BusinessDomain = {
  id: string
  name: string
  description: string | null
  color: string | null
  table_ids: string[]
}

export type ModelTable = {
  table_id: string
  schema_name: string
  table_name: string
  table_type: string
  display_name: string
  table_kind: TableKind | null
  layer_id: string | null
  is_saved: boolean
}

export type LineageEdge = {
  id: string | null
  source_table_id: string
  target_table_id: string
  kind: "flow" | "relation"
  origin: "dictionary" | "manual" | "override"
  label: string | null
  color: string | null
}

export type BusinessModel = {
  connection_id: string
  layers: DataLayer[]
  domains: BusinessDomain[]
  tables: ModelTable[]
  business_canvas: Record<string, unknown>
  lineage_canvas: Record<string, unknown>
  lineage_edges: LineageEdge[]
}

export type DomainInput = {
  name: string
  description: string | null
  color: string | null
  table_ids: string[]
}
