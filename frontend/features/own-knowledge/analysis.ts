import type { BadgeTone } from "@/components/badge"

import type { ExpertRule } from "../expert-rule-management/types"
import { foldName } from "../glossary-management/labels"
import type { GlossaryTerm } from "../glossary-management/types"
import type { Metric } from "../metric-management/types"
import type { KnowledgeKind, OwnEntry } from "./types"

// The backend only stops one user from saving the same name twice. Overlap between users, and with what the
// catalog already holds, is worked out here so the reviewer sees it before keeping or promoting anything.

// Folds case, spacing, tone marks and punctuation, so "Ngay mua" and "Ngày mưa" land together.
export const looseName = (value: string) =>
  value
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/giu, "d")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim()

export type Verdict = "same" | "close" | "different"

export const VERDICTS: Record<Verdict, { label: string; tone: BadgeTone; hint: string }> = {
  same: { label: "Giống hệt", tone: "success", hint: "Cùng nội dung, chỉ khác dấu câu hoặc chữ hoa." },
  close: { label: "Gần giống", tone: "primary", hint: "Phần lớn từ ngữ trùng nhau và không lệch con số nào." },
  different: { label: "Khác", tone: "danger", hint: "Khác con số, khác phủ định hoặc khác phần lớn từ ngữ." },
}

const wording = (text: string) =>
  text
    .normalize("NFC")
    .toLocaleLowerCase("vi")
    .replace(/[^\p{L}\p{N}%]+/gu, " ")
    .trim()
const numbers = (text: string) =>
  (text.match(/\d+(?:[.,]\d+)?/g) ?? [])
    .map((value) => value.replace(",", "."))
    .sort()
    .join("|")
const NEGATIONS = new Set(["không", "chưa", "trừ"])

export function compareWording(a: string, b: string): Verdict {
  const left = wording(a)
  const right = wording(b)
  if (left === right) return "same"
  // A moved threshold or an added "không" flips the meaning even when nearly every word matches.
  if (numbers(a) !== numbers(b)) return "different"
  const leftWords = left.split(" ")
  const rightWords = right.split(" ")
  if (leftWords.some((word) => NEGATIONS.has(word)) !== rightWords.some((word) => NEGATIONS.has(word))) return "different"
  const rightSet = new Set(rightWords)
  const shared = new Set(leftWords.filter((word) => rightSet.has(word))).size
  return shared / new Set([...leftWords, ...rightWords]).size >= 0.8 ? "close" : "different"
}

export type SystemState = "serving" | "pending" | "stale" | "revoked" | "inactive"

export const SYSTEM_STATES: Record<SystemState, { label: string; tone: BadgeTone }> = {
  serving: { label: "AI đang dùng", tone: "success" },
  pending: { label: "Chờ duyệt", tone: "warning" },
  stale: { label: "Cần cập nhật", tone: "danger" },
  revoked: { label: "Đã thu hồi", tone: "neutral" },
  inactive: { label: "Đã tắt", tone: "neutral" },
}

// Only these still speak for the catalog; a revoked term or a switched-off metric no longer contradicts anyone.
const LIVE: SystemState[] = ["serving", "pending", "stale"]

export type SystemItem = {
  kind: KnowledgeKind
  id: string
  name: string
  names: string[]
  text: string | null
  detail: string | null
  state: SystemState
  href: string
}

export function systemCatalog(
  connectionId: string,
  terms: GlossaryTerm[],
  metrics: Metric[],
  rules: ExpertRule[],
): SystemItem[] {
  const base = `/connections/${connectionId}`
  return [
    ...terms.map((term): SystemItem => {
      const revision = term.serving ?? term.current
      return {
        kind: "glossary",
        id: term.id,
        name: term.canonical_name,
        names: [term.canonical_name, ...new Set([...term.current.synonyms, ...(term.serving?.synonyms ?? [])])],
        text: revision.definition,
        detail: null,
        state: term.serving ? "serving" : term.current.status === "revoked" ? "revoked" : "pending",
        href: `${base}/glossary?term=${term.id}`,
      }
    }),
    ...metrics.map((metric): SystemItem => ({
      kind: "metric",
      id: metric.id,
      name: metric.label?.trim() || metric.name,
      names: [metric.name, ...(metric.label?.trim() ? [metric.label] : [])],
      text: metric.description,
      detail: metric.expression,
      state: metric.is_active ? "serving" : "inactive",
      href: metric.table_id ? `${base}/metrics?table=${metric.table_id}` : `${base}/metrics`,
    })),
    ...rules.map((rule): SystemItem => ({
      kind: "expert_rule",
      id: rule.id,
      name: rule.name,
      names: [rule.name],
      text: (rule.serving ?? rule.current).description,
      detail: null,
      state: rule.is_discoverable
        ? "serving"
        : rule.serving
          ? "stale"
          : rule.current.status === "revoked"
            ? "revoked"
            : "pending",
      href: `${base}/rules?rule=${rule.id}`,
    })),
  ]
}

export type SystemMatch = SystemItem & { exact: boolean; verdict: Verdict | null }
export type PeerMatch = { entry: OwnEntry; exact: boolean; verdict: Verdict }

export type Findings = {
  target: SystemItem | null
  system: SystemMatch[]
  peers: PeerMatch[]
  conflicts: number
  duplicates: number
}

export type EntryGroup = {
  key: string
  name: string
  entries: OwnEntry[]
  system: SystemItem[]
  // Distinct meanings among the users' entries: two entries share one when their wording is the same or close.
  meanings: number
  // Some entry disagrees with a catalog item that still counts, whether or not the users agree among themselves.
  againstCatalog: boolean
  conflicts: boolean
  duplicates: boolean
}

function indexBy<T>(items: T[], keys: (item: T) => string[]) {
  const index = new Map<string, T[]>()
  for (const item of items) {
    for (const key of new Set(keys(item).map(looseName))) {
      if (!key) continue
      index.set(key, [...(index.get(key) ?? []), item])
    }
  }
  return index
}

export function analyze(entries: OwnEntry[], catalog: SystemItem[]) {
  const catalogByName = indexBy(catalog, (item) => item.names)
  const catalogById = new Map(catalog.map((item) => [item.id, item]))
  const entriesByName = indexBy(entries, (entry) => [entry.name])

  const findings = new Map<string, Findings>()
  for (const entry of entries) {
    const key = looseName(entry.name)
    const folded = foldName(entry.name)
    const target = entry.promoted_id ? (catalogById.get(entry.promoted_id) ?? null) : null
    const system = (catalogByName.get(key) ?? [])
      .filter((item) => item.id !== target?.id)
      .map((item) => ({
        ...item,
        exact: item.names.some((name) => foldName(name) === folded),
        verdict: item.text?.trim() ? compareWording(entry.definition, item.text) : null,
      }))
    const peers = (entriesByName.get(key) ?? [])
      .filter((other) => other.id !== entry.id)
      .map((other) => ({
        entry: other,
        exact: foldName(other.name) === folded,
        verdict: compareWording(entry.definition, other.definition),
      }))
    const live = system.filter((item) => LIVE.includes(item.state) && item.verdict)
    findings.set(entry.id, {
      target,
      system,
      peers,
      conflicts:
        live.filter((item) => item.verdict === "different").length +
        peers.filter((peer) => peer.verdict === "different").length,
      duplicates:
        live.filter((item) => item.verdict !== "different").length +
        peers.filter((peer) => peer.verdict !== "different").length,
    })
  }

  const groups: EntryGroup[] = [...entriesByName.entries()].map(([key, members]) => {
    // Union-find over "same or close", so three users who agree count as one meaning.
    const parent = members.map((_, index) => index)
    const root = (index: number): number => (parent[index] === index ? index : (parent[index] = root(parent[index])))
    members.forEach((entry, i) => {
      for (let j = i + 1; j < members.length; j++) {
        if (compareWording(entry.definition, members[j].definition) !== "different") parent[root(j)] = root(i)
      }
    })
    const meanings = new Set(members.map((_, index) => root(index))).size
    const counts = new Map<string, number>()
    for (const entry of members) counts.set(entry.name, (counts.get(entry.name) ?? 0) + 1)
    const name = [...counts.entries()].sort((a, b) => b[1] - a[1] || b[0].localeCompare(a[0], "vi"))[0][0]
    return {
      key,
      name,
      entries: members,
      system: catalogByName.get(key) ?? [],
      meanings,
      againstCatalog: members.some((entry) =>
        findings.get(entry.id)!.system.some((item) => LIVE.includes(item.state) && item.verdict === "different"),
      ),
      conflicts: members.some((entry) => findings.get(entry.id)!.conflicts > 0),
      duplicates: members.some((entry) => findings.get(entry.id)!.duplicates > 0),
    }
  })

  return { findings, groups }
}
