import useSWR, { mutate } from "swr"

import { API_URL, ApiError, apiFetch } from "@/lib/api"
import { readServerSentEvents } from "@/lib/sse"

import type { AutofillEvent, DictionaryStats, DictionarySummary, TableDictionary } from "./types"

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export const summaryKey = (connectionId: string) => `/api/v1/database-connections/${connectionId}/dictionary-summary`
export const STATS_LIMIT = 8
export const statsKey = (connectionId: string) =>
  `/api/v1/database-connections/${connectionId}/dictionary-stats?limit=${STATS_LIMIT}`
export const dictionaryKey = (tableId: string) => `/api/v1/tables/${tableId}/dictionary`

export function useDictionarySummary(connectionId: string) {
  return useSWR<DictionarySummary>(summaryKey(connectionId), fetcher)
}

export function useDictionaryStats(connectionId: string) {
  return useSWR<DictionaryStats>(statsKey(connectionId), fetcher)
}

export function useTableDictionary(tableId: string | null) {
  return useSWR<TableDictionary>(tableId && dictionaryKey(tableId), fetcher, { revalidateOnFocus: false })
}

async function storeDictionary(dictionary: TableDictionary) {
  await mutate(dictionaryKey(dictionary.table_id), dictionary, { revalidate: false })
  await mutate(summaryKey(dictionary.connection_id))
  await mutate(statsKey(dictionary.connection_id))
}

export async function saveTableDictionary(tableId: string, body: unknown) {
  const dictionary = await apiFetch<TableDictionary>(dictionaryKey(tableId), {
    method: "PUT",
    body: JSON.stringify(body),
  })
  await storeDictionary(dictionary)
  return dictionary
}

export async function saveColumnDictionaries(tableId: string, columns: unknown[]) {
  const dictionary = await apiFetch<TableDictionary>(`${dictionaryKey(tableId)}/columns`, {
    method: "PUT",
    body: JSON.stringify({ columns }),
  })
  await storeDictionary(dictionary)
  return dictionary
}

export async function* streamAutofill(tableId: string, signal: AbortSignal): AsyncGenerator<AutofillEvent> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${dictionaryKey(tableId)}/autofill`, { method: "POST", signal })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError(0, "Không kết nối được tới backend. Kiểm tra server API đã chạy chưa.")
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.detail ?? "Không thể bắt đầu tự động điền.")
  }
  for await (const message of readServerSentEvents(response)) {
    yield { event: message.event, data: JSON.parse(message.data) } as AutofillEvent
  }
}
