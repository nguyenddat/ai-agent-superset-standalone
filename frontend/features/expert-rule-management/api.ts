import useSWR, { mutate } from "swr"

import { apiFetch } from "@/lib/api"

import type { ExpertRule, RuleContent, RuleCreate, RuleOptionTable, RuleRevision, RuleUpdate } from "./types"

const BASE = "/api/v1/expert-rules"
export const rulesKey = (connectionId: string) => `${BASE}?connection_id=${connectionId}`
const optionsKey = (connectionId: string) => `${BASE}/options?connection_id=${connectionId}`
const revisionsKey = (ruleId: string) => `${BASE}/${ruleId}/revisions`

const fetcher = <T,>(path: string) => apiFetch<T>(path)

export function useRules(connectionId: string) {
  return useSWR<ExpertRule[]>(rulesKey(connectionId), fetcher, { revalidateOnFocus: false })
}

// Which glossary terms a rule may use depends on what is approved right now, so the options follow focus.
export function useRuleOptions(connectionId: string) {
  return useSWR<{ tables: RuleOptionTable[] }>(optionsKey(connectionId), fetcher)
}

export function useRuleRevisions(ruleId: string | null, revision: number) {
  return useSWR<RuleRevision[]>(ruleId && [revisionsKey(ruleId), revision], ([path]: [string]) => apiFetch(path), {
    revalidateOnFocus: false,
  })
}

export const refreshRules = (connectionId: string) =>
  Promise.all([mutate(rulesKey(connectionId)), mutate(optionsKey(connectionId))])

async function write(connectionId: string, path: string, method: string, body: unknown) {
  const saved = await apiFetch<ExpertRule>(path, { method, body: JSON.stringify(body) })
  await mutate(rulesKey(connectionId))
  return saved
}

export function createRule(input: RuleCreate) {
  return write(input.connection_id, BASE, "POST", input)
}

export function saveRuleDraft(connectionId: string, id: string, input: RuleUpdate) {
  return write(connectionId, `${BASE}/${id}/draft`, "PUT", input)
}

export function approveRule(connectionId: string, id: string, expectedRevision: number) {
  return write(connectionId, `${BASE}/${id}/approve`, "POST", { expected_revision: expectedRevision })
}

export function revokeRule(connectionId: string, id: string, expectedRevision: number) {
  return write(connectionId, `${BASE}/${id}/revoke`, "POST", { expected_revision: expectedRevision })
}

// Approval is all or nothing, so keeping only part of a draft saves that part as a newer draft and approves it.
export async function approveRuleContent(connectionId: string, rule: ExpertRule, content: RuleContent) {
  const draft = await apiFetch<ExpertRule>(`${BASE}/${rule.id}/draft`, {
    method: "PUT",
    body: JSON.stringify({
      ...content,
      business_domain_ids: rule.business_domains.map((domain) => domain.id),
      expected_revision: rule.current.number,
    }),
  })
  return approveRule(connectionId, rule.id, draft.current.number)
}

export async function deleteRule(connectionId: string, id: string) {
  await apiFetch<void>(`${BASE}/${id}`, { method: "DELETE" })
  await mutate(rulesKey(connectionId))
}
