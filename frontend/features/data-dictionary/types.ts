export type SemanticRole = "key" | "measure" | "dimension" | "label" | "time" | "row_kind" | "attribute"
export type TemporalKind = "date" | "timestamp"
export type ColumnAggregation = "SUM" | "AVG" | "MIN" | "MAX" | "COUNT" | "COUNT_DISTINCT"
export type TableKind = "base" | "aggregate"
export type TableLayout = "wide" | "indicator_values" | "indicator_catalog"

export type TimeGrainValue = "instant" | "hour" | "day" | "week" | "month" | "quarter" | "year"
export type IndicatorAggregationValue = "SUM" | "AVG" | "MIN" | "MAX" | "COUNT" | "NONE"

export type RoleAssignment = {
  role: string
  qualifier: string | null
  column_id: string
}

export type ColumnRole = RoleAssignment & { column_name: string | null }

export type TimeGrain = {
  row_kind_value: string | null
  label: string | null
  time_grain: TimeGrainValue
}

export type IndicatorAggregation = {
  source_code: string
  aggregation: IndicatorAggregationValue
}

export type ReferencedColumn = {
  column_id: string
  table_id: string
  schema_name: string
  table_name: string
  column_name: string
}

export type ColumnDictionary = {
  column_id: string
  name: string
  data_type: string
  ordinal_position: number
  is_nullable: boolean
  source_is_primary_key: boolean
  default_value: string | null
  is_saved: boolean
  display_name: string
  description: string | null
  business_term: string | null
  semantic_role: SemanticRole
  semantic_role_is_default: boolean
  temporal_kind: TemporalKind | null
  unit: string | null
  format: string | null
  is_primary_key: boolean | null
  is_unique: boolean
  referenced_column: ReferencedColumn | null
  contains_pii: boolean
  aggregations: ColumnAggregation[]
  synonyms: string[]
  updated_at: string | null
}

export type TableDictionary = {
  table_id: string
  connection_id: string
  schema_name: string
  table_name: string
  table_type: string
  is_saved: boolean
  display_name: string
  description: string | null
  grain_description: string | null
  table_kind: TableKind | null
  layout: TableLayout
  indicator_catalog: { table_id: string; schema_name: string; table_name: string; display_name: string } | null
  contains_pii: boolean
  updated_at: string | null
  column_roles: ColumnRole[]
  time_grains: TimeGrain[]
  indicator_aggregations: IndicatorAggregation[]
  columns: ColumnDictionary[]
}

export type DictionaryTableSummary = {
  table_id: string
  table_name: string
  table_type: string
  is_saved: boolean
  display_name: string
  layout: TableLayout
  column_count: number
  described_column_count: number
}

export type DictionarySummary = {
  connection_id: string
  table_count: number
  described_table_count: number
  schemas: { schema_id: string; schema_name: string; tables: DictionaryTableSummary[] }[]
}

type StatsTable = {
  table_id: string
  schema_name: string
  table_name: string
  display_name: string
  is_saved: boolean
}

export type DictionaryStats = {
  connection_id: string
  table_count: number
  described_table_count: number
  column_count: number
  described_column_count: number
  schemas: { schema_id: string; schema_name: string; table_count: number; described_table_count: number }[]
  most_columns: (StatsTable & { column_count: number; described_column_count: number })[]
  most_referenced: (StatsTable & { referencing_table_count: number })[]
}

export type TableFields = Pick<
  TableDictionary,
  | "display_name"
  | "description"
  | "grain_description"
  | "table_kind"
  | "contains_pii"
  | "layout"
  | "time_grains"
  | "indicator_aggregations"
> & { column_roles: RoleAssignment[]; indicator_catalog_table_id: string | null }

export type ColumnFields = Pick<
  ColumnDictionary,
  | "display_name"
  | "description"
  | "business_term"
  | "temporal_kind"
  | "unit"
  | "format"
  | "is_primary_key"
  | "is_unique"
  | "contains_pii"
  | "aggregations"
  | "synonyms"
  | "referenced_column"
> & { semantic_role: SemanticRole | null }

export type AutofillEvent =
  | { event: "status"; data: { processed: number; total: number; message: string } }
  | { event: "columns"; data: { columns: ColumnDictionary[]; processed: number; total: number } }
  | { event: "table"; data: TableDictionary }
  | { event: "done"; data: { processed: number; total: number; failed_columns: number; table_filled: boolean } }
  | { event: "error"; data: { code: string; message: string } }
