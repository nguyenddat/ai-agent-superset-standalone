export type DependencyRole = "value" | "group" | "join" | "filter"
export type TransformationOrigin = "manual" | "sql_job" | "view_sql"

export type ColumnDependency = {
  source_column_id: string
  target_column_id: string | null
  role: DependencyRole
}

export type TransformationInput = {
  target_table_id: string
  name: string
  description: string | null
  sql_text: string | null
  origin: TransformationOrigin
  source_table_ids: string[]
  dependencies: ColumnDependency[]
}

export type Transformation = TransformationInput & {
  id: string
  created_at: string
  updated_at: string
}

export type GraphEdge = {
  transformation_id: string | null
  source_table_id: string
  target_table_id: string
  kind: "transform" | "flow"
  origin: TransformationOrigin | "manual_edge"
  dependencies: ColumnDependency[]
}

export type LineageGraph = {
  connection_id: string
  edges: GraphEdge[]
}

export type LineagePreview = {
  target_table_id: string
  source_table_ids: string[]
  dependencies: ColumnDependency[]
  warnings: string[]
  complete: boolean
}

export type LineageColumn = {
  column_id: string
  table_id: string
  name: string
  data_type: string
  is_key: boolean
  display_name: string
}
