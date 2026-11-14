import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import type {
  ConnectionTestResult,
  DatabaseColumn,
  DatabaseConnection,
  DatabaseSchema,
  DatabaseTable,
  Dialect,
  SyncResult,
} from "./types"

const CONNECTIONS = "/api/v1/database-connections"

type ConnectionInput = { dialect: string; driver: string | null; uri: string }
type ConnectionScope = Pick<DatabaseConnection, "schema_includes" | "schema_excludes" | "table_includes" | "table_excludes">
type ConnectionChanges = Partial<{ name: string; is_active: boolean; uri: string } & ConnectionScope>

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useConnections() {
  return useSWR<DatabaseConnection[]>(CONNECTIONS, fetcher)
}

export function useConnection(id: string) {
  return useSWR<DatabaseConnection>(`${CONNECTIONS}/${id}`, fetcher)
}

export type SchemaTables = { schema: DatabaseSchema; tables: DatabaseTable[] }

export function useSchemaTables(connectionId: string) {
  return useSWR<SchemaTables[]>(["schema-tables", connectionId], async () => {
    const schemas = await apiFetch<DatabaseSchema[]>(`${CONNECTIONS}/${connectionId}/schemas`)
    return Promise.all(
      schemas.map(async (schema) => ({
        schema,
        tables: await apiFetch<DatabaseTable[]>(`/api/v1/schemas/${schema.id}/tables`),
      })),
    )
  })
}

const isDialectsKey = (key: unknown) => typeof key === "string" && key.endsWith("/dialects")
const isConnectionKey = (key: unknown) => typeof key === "string" && key.startsWith(CONNECTIONS) && !isDialectsKey(key)

export function useDialects() {
  return useSWR<Dialect[]>(`${CONNECTIONS}/dialects`, fetcher, { revalidateOnFocus: false })
}

export function useSchemas(connectionId: string | null) {
  return useSWR<DatabaseSchema[]>(connectionId && `${CONNECTIONS}/${connectionId}/schemas`, fetcher)
}

export function useTables(schemaId: string | null) {
  return useSWR<DatabaseTable[]>(schemaId && `/api/v1/schemas/${schemaId}/tables`, fetcher)
}

export function useColumns(tableId: string | null) {
  return useSWR<DatabaseColumn[]>(tableId && `/api/v1/tables/${tableId}/columns`, fetcher)
}

export function testConnection(input: ConnectionInput) {
  return apiFetch<ConnectionTestResult>(`${CONNECTIONS}/test`, { method: "POST", body: JSON.stringify(input) })
}

export async function createConnection(input: ConnectionInput & { name: string } & ConnectionScope) {
  const result = await apiFetch<DatabaseConnection>(CONNECTIONS, { method: "POST", body: JSON.stringify(input) })
  await mutate(CONNECTIONS)
  return result
}

export async function updateConnection(id: string, changes: ConnectionChanges) {
  const result = await apiFetch<DatabaseConnection>(`${CONNECTIONS}/${id}`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  })
  await mutate(isConnectionKey)
  return result
}

export async function deleteConnection(id: string) {
  await apiFetch<void>(`${CONNECTIONS}/${id}`, { method: "DELETE" })
  await mutate(CONNECTIONS)
}

export async function syncConnection(id: string) {
  const result = await apiFetch<SyncResult>(`${CONNECTIONS}/${id}/sync`, { method: "POST" })
  await mutate((key) => !isDialectsKey(key))
  return result
}
