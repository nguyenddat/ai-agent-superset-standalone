"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { fetchConversation, refreshConversations, saveFeedback, streamChat, type ChatRequest } from "./api"
import type {
  DoneEvent,
  ErrorEvent,
  JoinOptionDetail,
  QueryData,
  Rating,
  ReasoningEvent,
  ReasoningLine,
  StepEvent,
  StoredTurn,
} from "./types"

export type TurnPhase = "sending" | "streaming" | "done" | "stopped" | "failed"

export type TurnStep = StepEvent & { reasoning: ReasoningLine[] }

// What the user asked for: a question, or a join option picked for an earlier join_ambiguous turn.
type TurnRequest = { question: string; choice?: { turnId: string; signature: string; label: string } }

export type Turn = {
  id: string
  request: TurnRequest
  // Set once the server has recorded the turn, which only happens when a user name is set.
  conversationId?: string
  turnId?: string
  startedAt: number
  // Known for turns loaded from history, whose timer cannot run.
  duration?: number
  phase: TurnPhase
  // One entry per step, in the order the steps began; a later event for the same step replaces it.
  steps: TurnStep[]
  results: QueryData[]
  answer: string
  outcome?: DoneEvent
  // Either the stream's `error` event or a failure before the stream started (HTTP status, network).
  error?: ErrorEvent
  feedback: Rating | null
}

const newId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()))

function withStep(turn: Turn, name: StepEvent["step"], change: (step: TurnStep) => TurnStep): Turn {
  const index = turn.steps.findIndex((item) => item.step === name)
  const current = index === -1 ? { step: name, status: "started" as const, detail: {}, reasoning: [] } : turn.steps[index]
  const steps = index === -1 ? [...turn.steps, change(current)] : turn.steps.with(index, change(current))
  return { ...turn, phase: "streaming", steps }
}

function addReasoning(step: TurnStep, { source, index, delta }: ReasoningEvent): TurnStep {
  const reasoning = [...step.reasoning]
  while (reasoning.length <= index) reasoning.push({ source, text: "" })
  reasoning[index] = { ...reasoning[index], text: reasoning[index].text + delta }
  return { ...step, reasoning }
}

const choiceLabel = (option: Pick<JoinOptionDetail, "root_table">, number?: number) =>
  number ? `Dùng cách nối ${number}, bắt đầu từ ${option.root_table}` : `Dùng cách nối bắt đầu từ ${option.root_table}`

function fromStored(stored: StoredTurn): Turn {
  const steps = (stored.steps ?? []).map((step) => ({ ...step, detail: step.detail ?? {}, reasoning: step.reasoning ?? [] }))
  const chosen = steps.find((step) => step.step === "join_plan" && step.detail.chosen)?.detail
  const choice =
    stored.continued_from && chosen?.signature
      ? { turnId: stored.continued_from, signature: chosen.signature, label: choiceLabel({ root_table: chosen.root_table ?? "" }) }
      : undefined
  const outcome: DoneEvent | undefined =
    stored.status === "running" || stored.status === "error"
      ? undefined
      : {
          status: stored.status,
          flow: stored.flow ?? "none",
          assumptions: stored.assumptions ?? undefined,
          clarification_question: stored.clarification_question ?? undefined,
          clarification_options: stored.clarification_options,
        }
  const stopped = stored.error_code === "client_disconnected"
  return {
    id: stored.id,
    request: { question: stored.question, choice },
    conversationId: stored.conversation_id,
    turnId: stored.id,
    startedAt: Date.parse(stored.created_at),
    duration: stored.duration_ms ?? 0,
    phase: outcome ? "done" : stopped ? "stopped" : "failed",
    steps,
    results: stored.results ?? [],
    answer: stored.answer ?? "",
    outcome,
    error:
      outcome || stopped
        ? undefined
        : stored.status === "running"
          ? { code: "running", message: "Lượt này chưa kết thúc khi được lưu." }
          : { code: stored.error_code ?? "error", message: "Lượt hỏi đáp này gặp lỗi khi xử lý." },
    feedback: stored.feedback?.rating ?? null,
  }
}

export function useChat(connectionId: string, userId: string) {
  const [turns, setTurns] = useState<Turn[]>([])
  // A conversation belongs to the user who started it; another name starts a new one.
  const [conversation, setConversation] = useState<{ id: string; userId: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const conversationId = conversation && conversation.userId === userId ? conversation.id : undefined

  useEffect(() => () => controller.current?.abort(), [])

  const update = useCallback((id: string, change: (turn: Turn) => Turn) => {
    setTurns((current) => current.map((turn) => (turn.id === id ? change(turn) : turn)))
  }, [])

  const run = useCallback(
    async (request: TurnRequest) => {
      if (controller.current) return
      const abort = new AbortController()
      controller.current = abort
      const id = newId()
      const user = userId
      setTurns((current) => [
        ...current,
        { id, request, startedAt: Date.now(), phase: "sending", steps: [], results: [], answer: "", feedback: null },
      ])
      const body: ChatRequest = request.choice
        ? { connectionId, userId: user, conversationId, previousTurnId: request.choice.turnId, joinSignature: request.choice.signature }
        : { connectionId, question: request.question, userId: user || undefined, conversationId }
      try {
        for await (const message of streamChat(body, abort.signal)) {
          if (message.event === "turn") {
            const { conversation_id, turn_id } = message.data
            setConversation({ id: conversation_id, userId: user })
            update(id, (turn) => ({ ...turn, conversationId: conversation_id, turnId: turn_id }))
          } else if (message.event === "step") {
            const { step, status, detail } = message.data
            update(id, (turn) => withStep(turn, step, (current) => ({ ...current, status, detail })))
          } else if (message.event === "reasoning") {
            const event = message.data
            update(id, (turn) => withStep(turn, event.step, (current) => addReasoning(current, event)))
          } else if (message.event === "data") {
            const data = message.data
            update(id, (turn) => ({ ...turn, phase: "streaming", results: [...turn.results, data] }))
          } else if (message.event === "token") {
            const chunk = message.data.text
            update(id, (turn) => ({ ...turn, phase: "streaming", answer: turn.answer + chunk }))
          } else if (message.event === "done") {
            const outcome = message.data
            update(id, (turn) => ({ ...turn, phase: "done", outcome }))
          } else if (message.event === "error") {
            const error = message.data
            update(id, (turn) => ({ ...turn, phase: "failed", error }))
          }
        }
        // A stream that closes without `done` or `error` was cut off (server restart, proxy timeout).
        update(id, (turn) =>
          turn.phase === "sending" || turn.phase === "streaming"
            ? { ...turn, phase: "failed", error: { code: "interrupted", message: "Kết nối bị ngắt trước khi có câu trả lời đầy đủ." } }
            : turn,
        )
      } catch (error) {
        if (abort.signal.aborted) {
          update(id, (turn) => ({ ...turn, phase: "stopped" }))
        } else {
          const message = error instanceof Error ? error.message : "Không thể gửi câu hỏi."
          update(id, (turn) => ({ ...turn, phase: "failed", error: { code: "request_failed", message } }))
        }
      } finally {
        if (controller.current === abort) controller.current = null
        // The first recorded turn creates the conversation; later ones move it to the top of the history.
        void refreshConversations(connectionId, user)
      }
    },
    [connectionId, conversationId, update, userId],
  )

  const send = useCallback((question: string) => {
    const text = question.trim()
    if (text) void run({ question: text })
  }, [run])

  const retry = useCallback((turn: Turn) => void run(turn.request), [run])

  // Continuing needs the recorded turn, so only turns of the current user's conversation can be continued.
  const choose = useCallback(
    (turn: Turn, option: JoinOptionDetail) => {
      if (!turn.turnId || turn.conversationId !== conversationId) return
      const choice = { turnId: turn.turnId, signature: option.signature, label: choiceLabel(option, option.number) }
      void run({ question: turn.request.question, choice })
    },
    [conversationId, run],
  )

  const stop = useCallback(() => controller.current?.abort(), [])

  const clear = useCallback(() => {
    controller.current?.abort()
    setTurns([])
    setConversation(null)
  }, [])

  const open = useCallback(
    async (id: string) => {
      controller.current?.abort()
      setLoading(true)
      try {
        const detail = await fetchConversation(id, userId)
        setTurns(detail.turns.map(fromStored))
        setConversation({ id: detail.id, userId })
      } finally {
        setLoading(false)
      }
    },
    [userId],
  )

  const rate = useCallback(
    async (turn: Turn, rating: Rating | null) => {
      if (!turn.conversationId || !turn.turnId || !userId) return
      const previous = turn.feedback
      update(turn.id, (current) => ({ ...current, feedback: rating }))
      try {
        await saveFeedback(userId, turn.conversationId, turn.turnId, rating)
      } catch (error) {
        update(turn.id, (current) => ({ ...current, feedback: previous }))
        throw error
      }
    },
    [update, userId],
  )

  const last = turns.at(-1)
  const busy = last?.phase === "sending" || last?.phase === "streaming"
  const status = !busy ? "ready" : last.phase === "sending" ? "submitted" : "streaming"

  return { turns, status, busy, loading, conversationId, send, retry, choose, stop, clear, open, rate } as const
}
