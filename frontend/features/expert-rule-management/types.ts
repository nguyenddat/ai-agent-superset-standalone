export type Operator =
  | "equals"
  | "not_equals"
  | "contains"
  | "not_contains"
  | "greater_than"
  | "greater_than_or_equal"
  | "less_than"
  | "less_than_or_equal"
  | "in"
  | "not_in"
  | "is_null"
  | "is_not_null"

export type ValueType = "string" | "number" | "boolean" | "null" | "array"
export type Scalar = string | number | boolean
export type RevisionStatus = "draft" | "approved" | "revoked"

export type RuleCondition = {
  column_id: string
  operator: Operator
  value_type: ValueType
  value: Scalar | Scalar[] | null
}

export type RuleException = { when: string; outcome: string }
export type RuleExample = { question: string; intent: string }

export type RuleContent = {
  description: string | null
  conditions: RuleCondition[]
  exceptions: RuleException[]
  examples: RuleExample[]
  glossary_term_ids: string[]
  metric_ids: string[]
}

export type RuleRevision = RuleContent & {
  number: number
  status: RevisionStatus
  created_at: string
}

export type ExpertRule = {
  id: string
  connection_id: string
  table_id: string
  name: string
  group_name: string | null
  current: RuleRevision
  serving: RuleRevision | null
  is_discoverable: boolean
  created_at: string
  updated_at: string
}

export type RuleCreate = RuleContent & {
  connection_id: string
  table_id: string
  name: string
  group_name: string | null
}

export type RuleUpdate = RuleContent & {
  expected_revision: number
  group_name: string | null
}

export type OptionColumn = { id: string; name: string; data_type: string }

export type RuleOptionTable = {
  table_id: string
  name: string
  columns: OptionColumn[]
  glossary_terms: { id: string; name: string }[]
  metrics: { id: string; name: string }[]
}
