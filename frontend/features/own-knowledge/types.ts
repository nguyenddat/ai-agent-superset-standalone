export type KnowledgeKind = "glossary" | "metric" | "expert_rule"
export type ReviewStatus = "pending" | "kept_own" | "promoted"

export type OwnEntry = {
  id: string
  connection_id: string
  user_id: string
  kind: KnowledgeKind
  name: string
  concept: string | null
  definition: string
  table_id: string | null
  source_clarification_id: string | null
  source_proposal_id: string | null
  source_question: string | null
  review_status: ReviewStatus
  review_note: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  promoted_kind: KnowledgeKind | null
  promoted_id: string | null
  version: number
  created_at: string
  updated_at: string
  active_for_agent: boolean
}

export type ReviewAction = "keep_own" | "reopen"
