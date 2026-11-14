import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import type { BusinessDomain, BusinessModel, DomainInput } from "./types"

const BASE = "/api/v1/business-model"

export const modelKey = (connectionId: string) => `${BASE}/connections/${connectionId}`

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useBusinessModel(connectionId: string) {
  return useSWR<BusinessModel>(modelKey(connectionId), fetcher, { revalidateOnFocus: false })
}

export function updateModel(connectionId: string, change: (model: BusinessModel) => BusinessModel) {
  return mutate<BusinessModel>(modelKey(connectionId), (model) => model && change(model), { revalidate: false })
}

export const refreshModel = (connectionId: string) => mutate(modelKey(connectionId))

// Domains span every connection while the model lists only this connection's tables, so a write keeps the members
// that belong to other connections.
async function withOtherMembers(domainId: string, tableIds: string[], connectionTableIds: Set<string>) {
  const domains = await apiFetch<BusinessDomain[]>(`${BASE}/domains`)
  const others = domains.find((domain) => domain.id === domainId)?.table_ids.filter((id) => !connectionTableIds.has(id))
  return [...new Set([...(others ?? []), ...tableIds])]
}

export function createDomain(input: DomainInput) {
  return apiFetch<BusinessDomain>(`${BASE}/domains`, { method: "POST", body: JSON.stringify(input) })
}

export async function updateDomain(domainId: string, input: DomainInput, connectionTableIds: Set<string>) {
  const table_ids = await withOtherMembers(domainId, input.table_ids, connectionTableIds)
  return apiFetch<BusinessDomain>(`${BASE}/domains/${domainId}`, {
    method: "PUT",
    body: JSON.stringify({ ...input, table_ids }),
  })
}

export function deleteDomain(domainId: string) {
  return apiFetch<void>(`${BASE}/domains/${domainId}`, { method: "DELETE" })
}
