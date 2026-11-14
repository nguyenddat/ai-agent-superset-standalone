import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import type { Metric, MetricInput, SupersetDatabase, SupersetSyncResult, SupersetUser } from "./types"

const BASE = "/api/v1/metrics"
export const metricsKey = (connectionId: string) => `${BASE}?connection_id=${connectionId}`
const DATABASES = `${BASE}/superset/databases`
const USERS = `${BASE}/superset/users`

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useMetrics(connectionId: string) {
  return useSWR<Metric[]>(metricsKey(connectionId), fetcher, { revalidateOnFocus: false })
}

export function useSupersetDatabases() {
  return useSWR<SupersetDatabase[]>(DATABASES, fetcher, { revalidateOnFocus: false })
}

export function useSupersetUsers() {
  return useSWR<SupersetUser[]>(USERS, fetcher, { revalidateOnFocus: false })
}

// Sync and linking change which metrics every connection sees, so every metric list reloads.
const refreshAll = () => mutate((key) => typeof key === "string" && key.startsWith(BASE))

export async function createMetric(connectionId: string, input: MetricInput) {
  const saved = await apiFetch<Metric>(BASE, { method: "POST", body: JSON.stringify(input) })
  await mutate(metricsKey(connectionId))
  return saved
}

export async function updateMetric(connectionId: string, id: string, changes: Partial<MetricInput>) {
  const saved = await apiFetch<Metric>(`${BASE}/${id}`, { method: "PATCH", body: JSON.stringify(changes) })
  await mutate(metricsKey(connectionId))
  return saved
}

export async function deleteMetric(connectionId: string, id: string) {
  await apiFetch<void>(`${BASE}/${id}`, { method: "DELETE" })
  await mutate(metricsKey(connectionId))
}

export async function syncSuperset() {
  const result = await apiFetch<SupersetSyncResult>(`${BASE}/superset/sync`, { method: "POST" })
  await refreshAll()
  return result
}

export async function linkSupersetDatabase(databaseId: string, connectionId: string | null) {
  const saved = await apiFetch<SupersetDatabase>(`${DATABASES}/${databaseId}/link`, {
    method: "PUT",
    body: JSON.stringify({ connection_id: connectionId }),
  })
  await refreshAll()
  return saved
}
