import useSWR, { mutate } from "swr"

import { requestJson } from "@/lib/api"

import { refreshGlossary } from "../glossary-management/api"
import { metricsKey } from "../metric-management/api"
import { refreshRules } from "../expert-rule-management/api"
import type { KnowledgeKind, OwnEntry, ReviewAction } from "./types"

// Same-origin proxy (app/api/own-knowledge) that adds the admin key on the server.
const BASE = "/api/own-knowledge/admin/entries"
export const entriesKey = (connectionId: string) => `${BASE}?connection_id=${connectionId}`
let reviewPassword = ""

export function setReviewPassword(value: string) {
  reviewPassword = value
}

const authHeaders = () => ({ "X-Review-Password": reviewPassword })

const refreshEntries = (connectionId: string) =>
  mutate((key) => Array.isArray(key) && key[0] === entriesKey(connectionId))

export function useOwnEntries(connectionId: string, password: string) {
  return useSWR<OwnEntry[]>(
    password ? [entriesKey(connectionId), password] : null,
    ([url]: [string, string]) => requestJson<OwnEntry[]>(url, { headers: authHeaders() }),
  )
}

const post = <T,>(path: string, body: unknown) =>
  requestJson<T>(path, { method: "POST", headers: authHeaders(), body: JSON.stringify(body) })

export async function reviewEntry(entry: OwnEntry, action: ReviewAction, reviewer: string, note: string | null) {
  const saved = await post<OwnEntry>(`${BASE}/${entry.id}/review`, {
    expected_version: entry.version,
    action,
    reviewer_id: reviewer,
    note,
  })
  await refreshEntries(entry.connection_id)
  return saved
}

export async function promoteEntry<T>(
  entry: OwnEntry,
  kind: KnowledgeKind,
  payload: Record<string, unknown>,
  reviewer: string,
  note: string | null,
) {
  // The server takes the connection from the entry, so the form's copy is left out.
  const body = { ...payload }
  delete body.connection_id
  const result = await post<{ entry: OwnEntry; target: T }>(`${BASE}/${entry.id}/promote`, {
    expected_version: entry.version,
    target_kind: kind,
    payload: body,
    reviewer_id: reviewer,
    note,
  })
  await Promise.all([
    refreshEntries(entry.connection_id),
    kind === "glossary"
      ? refreshGlossary(entry.connection_id)
      : kind === "metric"
        ? mutate(metricsKey(entry.connection_id))
        : refreshRules(entry.connection_id),
  ])
  return result.target
}
