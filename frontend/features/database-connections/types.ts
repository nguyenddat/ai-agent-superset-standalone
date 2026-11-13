export type DatabaseConnection = {
  id: string
  name: string
  dialect: string
  driver: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type Dialect = {
  dialect: string
  driver: string
  label: string
}

export type ConnectionTestResult = {
  ok: boolean
  message: string
}

export type SyncResult = {
  status: string
  last_synced_at: string
  schema_count: number
  table_count: number
  column_count: number
}

export type DatabaseSchema = {
  id: string
  name: string
  last_synced_at: string
}

export type DatabaseTable = {
  id: string
  name: string
  table_type: string
  description: string | null
  last_synced_at: string
}

export type DatabaseColumn = {
  name: string
  data_type: string
  ordinal_position: number
  is_nullable: boolean
  is_primary_key: boolean
  default_value: string | null
  description: string | null
}
