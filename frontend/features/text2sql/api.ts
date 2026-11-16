import useSWR, { mutate } from "swr"

import { API_URL, ApiError, apiFetch } from "@/lib/api"
import { readServerSentEvents } from "@/lib/sse"

import type { ChatEvent, Conversation, ConversationDetail, ConversationListItem, Feedback, Rating, Suggestion } from "./types"

const CHAT = "/api/v1/text2sql/chat"
const CONVERSATIONS = "/api/v1/conversations"

// Without userId nothing is recorded; conversationId adds the turn to that conversation; previousTurnId with
// joinSignature continues a join_ambiguous turn with the chosen option.
export type ChatRequest = {
  connectionId: string
  question?: string
  userId?: string
  conversationId?: string
  previousTurnId?: string
  joinSignature?: string
}

export async function* streamChat(request: ChatRequest, signal: AbortSignal): AsyncGenerator<ChatEvent> {
  const body = {
    connection_id: request.connectionId,
    question: request.question || null,
    user_id: request.userId || null,
    conversation_id: request.conversationId ?? null,
    previous_turn_id: request.previousTurnId ?? null,
    join_signature: request.joinSignature ?? null,
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
    // 422 from FastAPI carries a list of field errors rather than a sentence.
    throw new ApiError(response.status, typeof detail === "string" ? detail : "Không thể gửi câu hỏi.")
  }
  for await (const message of readServerSentEvents(response)) {
    yield { event: message.event, data: JSON.parse(message.data) } as ChatEvent
  }
}

const fetcher = <T,>(path: string) => apiFetch<T>(path)
const query = (params: Record<string, string | number>) => new URLSearchParams(Object.entries(params).map(([key, value]) => [key, String(value)]))

export function useSuggestions(connectionId: string, userId: string, limit: number) {
  const params = query({ connection_id: connectionId, limit, ...(userId ? { user_id: userId } : {}) })
  return useSWR<Suggestion[]>(`/api/v1/text2sql/suggestions?${params}`, fetcher, { revalidateOnFocus: false })
}

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
