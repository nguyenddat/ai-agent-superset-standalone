// Mirrors the SSE events of POST /api/v1/text2sql/chat (backend/modules/text2sql/chat/events.py).

export type StepName =
  | "rewrite"
  | "metric_search"
  | "metric_query"
  | "field_search"
  | "dataset_plan"
  | "join_plan"
  | "dataset_query"
  | "analysis"

export type StepStatus = "started" | "done" | "skipped"

export type JoinOptionDetail = {
  number: number
  // Sent back as join_signature to continue the turn with this option.
  signature: string
  description: string
  root_table: string
  tables: string[]
  joins: string[]
  previously_used: boolean
}

// Each step sends its own detail shape; only the fields the screen reads are listed.
export type StepDetail = {
  original_question?: string
  rewritten_question?: string
  glossary_terms?: string[]
  rules?: string[]
  own_knowledge?: string[]
  changes?: string[]
  candidates?: { name: string; label: string; source: string }[]
  reason?: string
  outcome?: string
  queries?: number
  match?: "ok" | "none" | "unverified"
  note?: string | null
  tables?: { name: string; display_name: string; fields: string[] }[] | string[]
  root_table?: string
  added_tables?: string[]
  status?: "ok" | "ambiguous" | "not_declared"
  message?: string
  options?: JoinOptionDetail[]
  chosen?: boolean
  signature?: string
  description?: string
  joins?: string[]
  dataset_id?: string | null
  created?: boolean
  added_columns?: number
}

export type StepEvent = { step: StepName; status: StepStatus; detail: StepDetail }

export type ReasoningSource = "model" | "server"

// One sentence of reasoning, streamed in pieces that share an index.
export type ReasoningEvent = { step: StepName; source: ReasoningSource; index: number; delta: string }

export type ReasoningLine = { source: ReasoningSource; text: string }

export type TurnEvent = { conversation_id: string; turn_id: string }

export type ColumnType = "integer" | "decimal" | "float" | "date" | "datetime" | "boolean" | "text"

export type ResultColumn = {
  name: string
  column_id?: string | null
  label?: string | null
  role: string
  data_type?: ColumnType | null
  format?: string | null
  unit?: string | null
  contains_pii: boolean
}

export type ResultValue = string | number | boolean | null

export type QueryData = {
  kind: "metric" | "dataset"
  metric?: { name: string; label: string; format: string | null; currency: string | null }
  sql: string
  parameters: Record<string, unknown>
  columns: ResultColumn[]
  rows: ResultValue[][]
  row_count: number
  truncated: boolean
  warnings: string[]
  rules_applied: string[]
  filters_overridden: string[]
  pii: { confirmation: string; masked_columns: string[]; detected: Record<string, unknown>; warning: string | null }
}

export type ChatOutcome =
  | "answered"
  | "needs_clarification"
  | "cannot_answer"
  | "join_ambiguous"
  | "join_not_declared"
  | "error"

export type ChatFlow = "metric" | "dataset" | "none"

// Fields left empty by the server are omitted; conversation_id and turn_id only come when the turn was recorded.
export type DoneEvent = {
  status: ChatOutcome
  flow: ChatFlow
  dataset_id?: string
  assumptions?: string[]
  message?: string
  clarification_question?: string
  clarification_options?: string[]
  conversation_id?: string
  turn_id?: string
}

export type ErrorEvent = { code: string; message: string }

export type ChatEvent =
  | { event: "turn"; data: TurnEvent }
  | { event: "step"; data: StepEvent }
  | { event: "reasoning"; data: ReasoningEvent }
  | { event: "data"; data: QueryData }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: DoneEvent }
  | { event: "error"; data: ErrorEvent }

// Mirrors backend/modules/conversation/schemas/schema_conversation.py.

export type Rating = "up" | "down"

export type Feedback = { rating: Rating; comment: string | null; created_at: string; updated_at: string }

export type StoredStep = StepEvent & { reasoning?: ReasoningLine[] }

export type StoredTurn = {
  id: string
  conversation_id: string
  sequence: number
  question: string
  rewritten_question: string | null
  answer: string | null
  flow: ChatFlow | null
  status: "running" | ChatOutcome
  steps: StoredStep[] | null
  results: QueryData[] | null
  assumptions: string[] | null
  dataset_id: string | null
  continued_from: string | null
  clarification_question: string | null
  clarification_options: string[]
  error_code: string | null
  error: string | null
  duration_ms: number | null
  feedback: Feedback | null
  created_at: string
}

export type Conversation = {
  id: string
  connection_id: string
  user_id: string
  title: string
  is_pinned: boolean
  is_archived: boolean
  last_message_at: string | null
  created_at: string
  updated_at: string
  turn_count: number
}

export type ConversationListItem = Conversation & { last_question: string | null; last_status: StoredTurn["status"] | null }

export type ConversationDetail = Conversation & { turns: StoredTurn[] }

export type Suggestion = { question: string; source: "history" | "rule_example" | "metric" }
