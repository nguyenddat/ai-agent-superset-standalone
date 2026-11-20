import type { ChartDisplay, ChartField, ChartSource, ChartSpec } from "./charts/spec"

// Mirrors the SSE events of POST /api/v1/text2sql/chat/stream (backend/modules/text2sql/services/chat_events.py).

export type ResultValue = string | number | boolean | null

export type TurnEvent = { conversation_id: string; turn_id: string; continued_from: string | null }

export type PreprocessQuestion = {
  position: number
  question: string
  depends_on: number[]
  question_type: string
  business_concepts: string[]
  metrics: { name: string; label: string | null }[]
  glossary: string[]
  expert_rules: string[]
  own_knowledge: string[]
}

export type PreprocessEvent = {
  rewritten_question: string
  is_split: boolean
  execution_mode: "parallel" | "sequential"
  stages: number[][]
  questions: PreprocessQuestion[]
}

export type ExplanationKind =
  | "metric"
  | "source"
  | "period"
  | "filter"
  | "group"
  | "order"
  | "rule"
  | "value_match"
  | "data_range"
  | "scope"
  | "assumption"
  | "method"
  | "truncated"
  | "warning"

// One line of "Cách tính", built by the backend from the tool step. `start`/`end` (ISO, end inclusive) let the
// period be re-labelled for the day it is read; `text` is the fallback.
export type Explanation = {
  kind: ExplanationKind
  text: string
  name?: string | null
  status?: "applied" | "yielded" | "skipped" | null
  field?: string | null
  start?: string | null
  end?: string | null
  values?: string[] | null
}

// One tool call of the agent. Lookups (get_metric, get_table, get_expert_rule) carry no sql or rows;
// query_metric, run_sql and get_column_values carry the SQL and every row the query returned.
// Successful query_metric/run_sql steps also carry a stable result_id, labelled fields, the "Cách tính" lines and
// a chart (the agent's or the backend's suggestion); make_chart steps carry the result_id and chart they set.
// Every chart field is optional: turns recorded before them have none.
export type ToolStep = {
  tool: string
  arguments: Record<string, unknown>
  sql: string | null
  columns: string[]
  rows: ResultValue[][]
  row_count: number
  truncated: boolean
  notes: string[]
  error: string | null
  result_id?: string | null
  fields?: ChartField[]
  explanations?: Explanation[]
  chart?: ChartSpec | null
  chart_source?: ChartSource | null
  chart_types?: string[]
  display?: ChartDisplay | null
}

export type ToolEvent = ToolStep & { position: number }

export type QuestionStartedEvent = { position: number; question: string; resumed: boolean }

export type QuestionWaitingEvent = { position: number; question: string; options: string[] }

// Sent just before a tool runs (not for ask_user); `subject` is the catalog label of what it reads.
export type ToolStartedEvent = { position: number; tool: string; subject: string | null }

// A chunk of answer text. `final` chunks belong to the turn's answer (position null for the synthesized answer of a
// split question); the others are a sub-question's draft. The official answer events always replace them.
export type AnswerDeltaEvent = { position: number | null; round: number; final: boolean; text: string }

// The round that streamed text turned out to call a tool: drop that round's text.
export type AnswerResetEvent = { position: number; round: number }

export type QuestionAnsweredEvent = { position: number; question: string; answer: string; exhausted: boolean }

export type ChatStatus = "answered" | "needs_clarification"

export type ClarificationEvent = { question: string; options: string[]; resume_id: string; expires_at: string }

// conversation_id and turn_id are null when no user name was sent, so nothing was recorded.
export type DoneEvent = {
  status: ChatStatus
  answer: string
  clarification_question: string | null
  clarification_options: string[]
  resume_id: string | null
  resume_expires_at: string | null
  conversation_id: string | null
  turn_id: string | null
}

export type ErrorEvent = { code: string; message: string }

export type ChatEvent =
  | { event: "turn"; data: TurnEvent }
  | { event: "preprocess"; data: PreprocessEvent }
  | { event: "question_started"; data: QuestionStartedEvent }
  | { event: "tool_started"; data: ToolStartedEvent }
  | { event: "tool"; data: ToolEvent }
  | { event: "answer_delta"; data: AnswerDeltaEvent }
  | { event: "answer_reset"; data: AnswerResetEvent }
  | { event: "synthesize_started"; data: Record<string, never> }
  | { event: "question_waiting"; data: QuestionWaitingEvent }
  | { event: "question_answered"; data: QuestionAnsweredEvent }
  | { event: "answer"; data: { answer: string } }
  | { event: "clarification"; data: ClarificationEvent }
  | { event: "done"; data: DoneEvent }
  | { event: "error"; data: ErrorEvent }

// Mirrors backend/modules/conversation/schemas/schema_conversation.py and the turn data the chat route stores
// (docs/handbook/modules/conversation/ghi-luot-tu-pipeline.md).

export type Rating = "up" | "down"

export type Feedback = { rating: Rating; comment: string | null; created_at: string; updated_at: string }

// Stored steps keep no rows; the rows of successful data steps are in `results`.
export type StoredQuestion = {
  position: number
  question: string
  answer: string
  exhausted: boolean
  steps: Omit<ToolStep, "columns" | "rows">[]
}

// The backend adds result_id, fields and chart_types to results recorded before charts existed (with chart null and
// display "none"); column_values results never have them.
export type StoredResult = {
  position: number
  kind: "metric" | "sql" | "column_values"
  tool: string
  sql: string | null
  columns: string[]
  rows: ResultValue[][]
  row_count: number
  truncated: boolean
  stored_truncated?: boolean
  result_id?: string
  fields?: ChartField[]
  chart?: ChartSpec | null
  chart_source?: ChartSource | null
  chart_types?: string[]
  display?: ChartDisplay | null
}

// The user's chart choice for one result of a turn, keyed by result_id.
export type ChartView = { chart: ChartSpec; updated_at?: string }

// Turns recorded before 2026-11-19 used other statuses and step shapes; they are shown as question and answer only.
export type StoredTurn = {
  id: string
  conversation_id: string
  sequence: number
  question: string
  rewritten_question: string | null
  answer: string | null
  status: "running" | "error" | ChatStatus | (string & {})
  steps: unknown[] | null
  results: unknown[] | null
  continued_from: string | null
  clarification_question: string | null
  clarification_options: string[]
  // Set while a waiting turn can still be resumed.
  resume_id: string | null
  resume_expires_at: string | null
  error_code: string | null
  error: string | null
  duration_ms: number | null
  feedback: Feedback | null
  views?: Record<string, ChartView> | null
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
