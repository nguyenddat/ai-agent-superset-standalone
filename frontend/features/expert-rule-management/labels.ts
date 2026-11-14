import type { BadgeTone } from "@/components/badge"

import type { ExpertRule, Operator, RuleCondition, RuleContent, RuleRevision, Scalar, ValueType } from "./types"

/** What a reader cares about: is the AI applying this rule, and is something waiting for review. */
export type RuleState = "active" | "stale" | "changed" | "draft" | "revoked"

export function ruleState(rule: ExpertRule): RuleState {
  if (rule.current.status === "approved") return rule.is_discoverable ? "active" : "stale"
  if (rule.current.status === "revoked") return "revoked"
  return rule.serving ? "changed" : "draft"
}

/** An approved revision the AI no longer applies, because a term or metric it pinned has changed since. */
export const servingIsStale = (rule: ExpertRule) => !!rule.serving && !rule.is_discoverable

export const RULE_STATES: Record<RuleState, { label: string; tone: BadgeTone; hint: string }> = {
  active: { label: "Đang áp dụng", tone: "success", hint: "AI đang áp dụng quy tắc này." },
  stale: {
    label: "Cần cập nhật",
    tone: "danger",
    hint: "Thuật ngữ hoặc metric liên kết đã đổi từ lúc duyệt, nên AI tạm ngừng áp dụng.",
  },
  changed: {
    label: "Chờ duyệt thay đổi",
    tone: "warning",
    hint: "AI vẫn áp dụng bản đã duyệt cho đến khi bản nháp mới được duyệt.",
  },
  draft: { label: "Chờ duyệt", tone: "warning", hint: "AI chưa áp dụng quy tắc này cho đến khi được duyệt." },
  revoked: { label: "Đã thu hồi", tone: "neutral", hint: "AI không còn áp dụng quy tắc này." },
}

export const OPERATORS: Record<Operator, string> = {
  equals: "bằng",
  not_equals: "khác",
  contains: "chứa",
  not_contains: "không chứa",
  greater_than: "lớn hơn",
  greater_than_or_equal: "từ … trở lên",
  less_than: "nhỏ hơn",
  less_than_or_equal: "từ … trở xuống",
  in: "là một trong",
  not_in: "không là một trong",
  is_null: "trống",
  is_not_null: "có giá trị",
}

export type ColumnKind = "number" | "boolean" | "text"

export function columnKind(dataType: string): ColumnKind {
  if (/bool/i.test(dataType)) return "boolean"
  if (/int|numeric|decimal|real|double|float|number|money|serial/i.test(dataType)) return "number"
  return "text"
}

/** Only the comparisons the backend accepts for a column of this kind. */
export const OPERATORS_BY_KIND: Record<ColumnKind, Operator[]> = {
  number: [
    "equals",
    "not_equals",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
    "in",
    "not_in",
    "is_null",
    "is_not_null",
  ],
  boolean: ["equals", "not_equals", "is_null", "is_not_null"],
  text: ["equals", "not_equals", "contains", "not_contains", "in", "not_in", "is_null", "is_not_null"],
}

export function valueTypeFor(operator: Operator, kind: ColumnKind): ValueType {
  if (operator === "is_null" || operator === "is_not_null") return "null"
  if (operator === "in" || operator === "not_in") return "array"
  if (operator === "contains" || operator === "not_contains") return "string"
  if (operator !== "equals" && operator !== "not_equals") return "number"
  return kind === "number" ? "number" : kind === "boolean" ? "boolean" : "string"
}

const scalarText = (value: Scalar) =>
  typeof value === "boolean" ? (value ? "Đúng" : "Sai") : typeof value === "string" ? `“${value}”` : String(value)

export function describeCondition(condition: RuleCondition, columnName: string) {
  const { operator, value } = condition
  const label = OPERATORS[operator]
  if (value === null) return `${columnName} ${label}`
  if (Array.isArray(value)) return `${columnName} ${label}: ${value.map(scalarText).join(", ")}`
  const text = scalarText(value)
  if (label.includes("…")) return `${columnName} ${label.replace("…", text)}`
  return `${columnName} ${label} ${text}`
}

export const contentOf = (revision: RuleRevision): RuleContent => ({
  description: revision.description,
  conditions: revision.conditions,
  exceptions: revision.exceptions,
  examples: revision.examples,
  glossary_term_ids: revision.glossary_term_ids,
  metric_ids: revision.metric_ids,
})

export const sameValue = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
export const sameIds = (a: string[], b: string[]) => sameValue([...a].sort(), [...b].sort())
