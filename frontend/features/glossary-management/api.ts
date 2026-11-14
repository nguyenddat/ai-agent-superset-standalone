import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import { dictionaryKey } from "../data-dictionary/api"
import type { TableDictionary } from "../data-dictionary/types"
import type { GlossaryContent, GlossaryCreate, GlossaryTerm, GlossaryUpdate } from "./types"

const BASE = "/api/v1/glossary"
export const glossaryKey = (connectionId: string) => `${BASE}?connection_id=${connectionId}`

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useGlossary(connectionId: string) {
  return useSWR<GlossaryTerm[]>(glossaryKey(connectionId), fetcher, { revalidateOnFocus: false })
}

export const refreshGlossary = (connectionId: string) => mutate(glossaryKey(connectionId))

async function write(connectionId: string, path: string, method: string, body?: unknown) {
  const saved = await apiFetch<GlossaryTerm>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
  await refreshGlossary(connectionId)
  return saved
}

export function createTerm(input: GlossaryCreate) {
  return write(input.connection_id, BASE, "POST", input)
}

export function saveDraft(connectionId: string, id: string, input: GlossaryUpdate) {
  return write(connectionId, `${BASE}/${id}/draft`, "PUT", input)
}

export function approveTerm(connectionId: string, id: string, expectedRevision: number) {
  return write(connectionId, `${BASE}/${id}/approve`, "POST", { expected_revision: expectedRevision })
}

export function revokeTerm(connectionId: string, id: string, expectedRevision: number) {
  return write(connectionId, `${BASE}/${id}/revoke`, "POST", { expected_revision: expectedRevision })
}

// Approval is all or nothing, so keeping only part of a draft saves that part as a newer draft and approves it.
export async function approveContent(connectionId: string, term: GlossaryTerm, content: GlossaryContent) {
  const draft = await apiFetch<GlossaryTerm>(`${BASE}/${term.id}/draft`, {
    method: "PUT",
    body: JSON.stringify({ ...content, group_name: term.group_name, expected_revision: term.current.number }),
  })
  return approveTerm(connectionId, term.id, draft.current.number)
}

export async function deleteTerm(connectionId: string, id: string) {
  await apiFetch<void>(`${BASE}/${id}`, { method: "DELETE" })
  await refreshGlossary(connectionId)
}

// Links carry only a column id, so naming one means reading the dictionaries of the connection's tables. The requests
// share the cache with the dictionary tab.
async function fetchColumns(tableIds: string[]) {
  const dictionaries = await Promise.all(
    tableIds.map((tableId) =>
      mutate<TableDictionary>(dictionaryKey(tableId), (cached) => cached ?? apiFetch(dictionaryKey(tableId)), {
        revalidate: false,
      }),
    ),
  )
  return dictionaries.filter((dictionary): dictionary is TableDictionary => !!dictionary)
}

export function useConnectionColumns(tableIds: string[], enabled: boolean) {
  const ids = [...new Set(tableIds)].sort()
  return useSWR(enabled && ids.length ? ["glossary-columns", ...ids] : null, ([, ...keys]: string[]) => fetchColumns(keys), {
    revalidateOnFocus: false,
    keepPreviousData: true,
  })
}
