import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import { dictionaryKey } from "../data-dictionary/api"
import type { TableDictionary } from "../data-dictionary/types"
import type {
  LineageColumn,
  LineageGraph,
  LineagePreview,
  Transformation,
  TransformationInput,
} from "./types"

const base = (connectionId: string) => `/api/v1/data-lineage/connections/${connectionId}`
const graphKey = (connectionId: string) => `${base(connectionId)}/graph`
const transformationsKey = (connectionId: string) => `${base(connectionId)}/transformations`

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useLineageGraph(connectionId: string) {
  return useSWR<LineageGraph>(graphKey(connectionId), fetcher, { revalidateOnFocus: false })
}

export function useTransformations(connectionId: string) {
  return useSWR<Transformation[]>(transformationsKey(connectionId), fetcher, { revalidateOnFocus: false })
}

const toColumns = (dictionary: TableDictionary): LineageColumn[] =>
  dictionary.columns.map((column) => ({
    column_id: column.column_id,
    table_id: dictionary.table_id,
    name: column.name,
    data_type: column.data_type,
    is_key: column.is_primary_key ?? column.source_is_primary_key,
    display_name: column.display_name,
  }))

// Column ids come from each table's dictionary; the requests share the cache with the dictionary tab.
async function fetchColumns(tableIds: string[]) {
  const dictionaries = await Promise.all(
    tableIds.map((tableId) =>
      mutate<TableDictionary>(dictionaryKey(tableId), (cached) => cached ?? apiFetch(dictionaryKey(tableId)), {
        revalidate: false,
      }),
    ),
  )
  return new Map(tableIds.map((tableId, index) => [tableId, toColumns(dictionaries[index]!)]))
}

export function useTableColumns(tableIds: string[]) {
  const ids = [...new Set(tableIds)].sort()
  return useSWR(ids.length ? ["lineage-columns", ...ids] : null, ([, ...keys]: string[]) => fetchColumns(keys), {
    revalidateOnFocus: false,
    keepPreviousData: true,
  })
}

async function refresh(connectionId: string) {
  await Promise.all([mutate(graphKey(connectionId)), mutate(transformationsKey(connectionId))])
}

export async function saveTransformation(connectionId: string, input: TransformationInput, id?: string) {
  const saved = await apiFetch<Transformation>(
    id ? `${transformationsKey(connectionId)}/${id}` : transformationsKey(connectionId),
    { method: id ? "PUT" : "POST", body: JSON.stringify(input) },
  )
  await refresh(connectionId)
  return saved
}

export async function deleteTransformation(connectionId: string, id: string) {
  await apiFetch<void>(`${transformationsKey(connectionId)}/${id}`, { method: "DELETE" })
  await refresh(connectionId)
}

export function previewSql(connectionId: string, targetTableId: string, sqlText: string) {
  return apiFetch<LineagePreview>(`${base(connectionId)}/preview`, {
    method: "POST",
    body: JSON.stringify({ target_table_id: targetTableId, sql_text: sqlText }),
  })
}

export function readViewSql(connectionId: string, tableId: string) {
  return apiFetch<{ target_table_id: string; sql_text: string }>(`${base(connectionId)}/tables/${tableId}/view-sql`)
}
