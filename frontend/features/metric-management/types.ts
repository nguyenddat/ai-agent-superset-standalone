import type { DomainRef } from "../business-model/domains"

export type MetricOrigin = "manual" | "superset"

export type Metric = {
  id: string
  origin: MetricOrigin
  name: string
  label: string | null
  expression: string
  description: string | null
  format: string | null
  currency: string | null
  metric_type: string | null
  warning_text: string | null
  is_active: boolean
  table_id: string | null
  source_url: string | null
  source_metric_id: number | null
  source_dataset_id: number | null
  source_database_id: string | null
  source_user_id: string | null
  source_dataset_owner_id: string | null
  source_schema: string | null
  source_table: string | null
  source_sql: string | null
  business_domains: DomainRef[]
  created_at: string
  updated_at: string
}

export type MetricInput = {
  table_id: string
  name: string
  expression: string
  label: string | null
  description: string | null
  format: string | null
  currency: string | null
  metric_type: string | null
  warning_text: string | null
  business_domain_ids: string[]
}

export type SupersetDatabase = {
  id: string
  source_url: string
  source_id: number
  name: string
  backend: string | null
  connection_id: string | null
}

export type SupersetUser = {
  id: string
  source_url: string
  source_id: number
  username: string
  first_name: string | null
  last_name: string | null
  email: string | null
}

export type SupersetSyncResult = {
  users: number
  databases: number
  metrics: number
  deactivated: number
}
