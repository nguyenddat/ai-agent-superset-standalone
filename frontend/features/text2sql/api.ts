import useSWR, { mutate } from "swr"

import { API_URL, ApiError, apiFetch } from "@/lib/api"
import { readServerSentEvents } from "@/lib/sse"

import type { ChartField, ChartSpec } from "./charts/spec"
import type {
  ChatEvent,
  Conversation,
  ConversationDetail,
  ConversationListItem,
  Feedback,
  Rating,
  ResultValue,
} from "./types"

const CHAT = "/api/v1/text2sql/chat/stream"
const CONVERSATIONS = "/api/v1/conversations"

// Without userId nothing is recorded; conversationId adds the turn to that conversation; resumeId continues the
// turn that paused with a clarification question, and `question` is then the user's reply. chatHistory is only read
// without userId, when the server has no recorded turns to rewrite a follow-up question from.
// A past turn as the rewrite step sees it: the question and the bot's final reply (its clarification question
// when it asked one back).
export type ChatHistoryTurn = {
  question: string
  answer: string | null
}

export type ChatRequest = {
  connectionId: string
  question: string
  userId?: string
  conversationId?: string
  resumeId?: string
  chatHistory?: ChatHistoryTurn[]
}

export async function* streamChat(request: ChatRequest, signal: AbortSignal): AsyncGenerator<ChatEvent> {
  const body = {
    connection_id: request.connectionId,
    question: request.question,
    user_id: request.userId || null,
    conversation_id: request.conversationId ?? null,
    resume_id: request.resumeId ?? null,
    chat_history: request.chatHistory ?? [],
  }
  let response: Response
  try {
    response = await fetch(`${API_URL}${CHAT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError(0, "Không kết nối được tới backend. Kiểm tra server API đã chạy chưa.")
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    // The backend answers errors with a sentence in `detail`; anything else (a proxy page) gets a generic one.
    throw new ApiError(response.status, typeof detail === "string" ? detail : "Không thể gửi câu hỏi.")
  }
  for await (const message of readServerSentEvents(response)) {
    let data: unknown
    try {
      data = JSON.parse(message.data)
    } catch {
      throw new ApiError(0, "Không đọc được dữ liệu server gửi về.")
    }
    yield { event: message.event, data } as ChatEvent
  }
}

const fetcher = <T,>(path: string) => apiFetch<T>(path)
const query = (params: Record<string, string | number>) => new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)]))

const conversationsKey = (connectionId: string, userId: string) =>
  `${CONVERSATIONS}?${query({ user_id: userId, connection_id: connectionId, limit: 200 })}`

// History belongs to a user, so there is nothing to list until the browser has one.
export function useConversations(connectionId: string, userId: string) {
  return useSWR<ConversationListItem[]>(userId ? conversationsKey(connectionId, userId) : null, fetcher)
}

export const refreshConversations = (connectionId: string, userId: string) =>
  userId ? mutate(conversationsKey(connectionId, userId)) : Promise.resolve()

export const fetchConversation = (id: string, userId: string) =>
  apiFetch<ConversationDetail>(`${CONVERSATIONS}/${id}?${query({ user_id: userId, turns_limit: 500 })}`)

export type ConversationChange = { title?: string; is_pinned?: boolean; is_archived?: boolean }

export async function updateConversation(connectionId: string, userId: string, id: string, change: ConversationChange) {
  const saved = await apiFetch<Conversation>(`${CONVERSATIONS}/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ user_id: userId, ...change }),
  })
  await refreshConversations(connectionId, userId)
  return saved
}

export async function deleteConversation(connectionId: string, userId: string, id: string) {
  await apiFetch<void>(`${CONVERSATIONS}/${id}?${query({ user_id: userId })}`, { method: "DELETE" })
  await refreshConversations(connectionId, userId)
}

export function saveFeedback(userId: string, conversationId: string, turnId: string, rating: Rating | null) {
  const path = `${CONVERSATIONS}/${conversationId}/turns/${turnId}/feedback`
  if (rating === null) return apiFetch<void>(`${path}?${query({ user_id: userId })}`, { method: "DELETE" })
  return apiFetch<Feedback>(path, { method: "PUT", body: JSON.stringify({ user_id: userId, rating }) })
}

export type CheckedChart = { chart: ChartSpec; warnings: string[] }

// Checks a chart against a result that was not recorded (no user name); 400 carries the problems, one per line.
export function validateChart(chart: ChartSpec, fields: ChartField[], rows: ResultValue[][], rowsComplete: boolean) {
  return apiFetch<CheckedChart & { chart_types: string[] }>("/api/v1/text2sql/charts/validate", {
    method: "POST",
    body: JSON.stringify({
      chart,
      fields,
      rows: rows.slice(0, 1000),
      rows_complete: rowsComplete && rows.length <= 1000,
    }),
  })
}

const viewPath = (conversationId: string, turnId: string, resultId: string) =>
  `${CONVERSATIONS}/${conversationId}/turns/${turnId}/views/${encodeURIComponent(resultId)}`

// Saves the user's chart for one result of a recorded turn; the backend checks it against the stored rows.
export type SavedView = CheckedChart & { result_id: string; updated_at: string }

export function saveChartView(
  userId: string,
  conversationId: string,
  turnId: string,
  resultId: string,
  chart: ChartSpec,
) {
  return apiFetch<SavedView>(viewPath(conversationId, turnId, resultId), {
    method: "PUT",
    body: JSON.stringify({ user_id: userId, chart }),
  })
}

export function deleteChartView(userId: string, conversationId: string, turnId: string, resultId: string) {
  const path = `${viewPath(conversationId, turnId, resultId)}?${query({ user_id: userId })}`
  return apiFetch<void>(path, { method: "DELETE" })
}
