"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import {
  deleteChartView,
  fetchConversation,
  refreshConversations,
  saveChartView,
  saveFeedback,
  streamChat,
  validateChart,
  type ChatHistoryTurn,
  type ChatRequest,
  type CheckedChart,
} from "./api"
import type { ChartField, ChartSpec } from "./charts/spec"
import { FIRST_NARRATION, narrate } from "./narration"
import { DATA_TOOLS, inferFields } from "./results"
import type {
  ChartView,
  ChatEvent,
  DoneEvent,
  ErrorEvent,
  PreprocessEvent,
  Rating,
  ResultValue,
  StoredQuestion,
  StoredResult,
  StoredTurn,
  ToolStep,
} from "./types"

export type TurnPhase = "sending" | "streaming" | "done" | "stopped" | "failed"

export type QuestionStatus = "pending" | "running" | "waiting" | "answered"

// One sub-question of the turn: the agent's tool calls in order, then its own answer or the question it asked back.
// `draft` is the answer text streaming in for a sub-question of a split question, replaced by `answer` when it ends.
export type QuestionState = {
  position: number
  question: string
  status: QuestionStatus
  steps: ToolStep[]
  answer?: string
  draft?: string
  draftRound?: number
  exhausted?: boolean
  clarification?: string
}

// What the user sent: a question, or a reply to the clarification question of an earlier turn.
type TurnRequest = { question: string; resumeId?: string }

export type Turn = {
  id: string
  request: TurnRequest
  // Set once the server has recorded the turn, which only happens when a user name is set.
  conversationId?: string
  turnId?: string
  // The paused turn this one answers, for turns loaded from history.
  continuedFrom?: string
  startedAt: number
  // Known for turns loaded from history, whose timer cannot run.
  duration?: number
  phase: TurnPhase
  // Absent on a resumed turn: the server does not redo preprocessing.
  preprocess?: PreprocessEvent
  questions: QuestionState[]
  // The answer so far: streamed text while live, then the official answer.
  answer: string
  answerRound?: number
  // The current progress line while live.
  narration?: string
  synthesizing?: boolean
  outcome?: DoneEvent
  // Either the stream's `error` event or a failure before the stream started (HTTP status, network).
  error?: ErrorEvent
  feedback: Rating | null
  // The user's chart per result_id: saved with the turn when it is recorded, kept in memory otherwise.
  views: Record<string, ChartView>
  // Recorded by the chat pipeline removed on 2026-11-19, whose steps this screen no longer reads.
  legacy?: boolean
}

// What saving a chart needs to know about the result it belongs to.
export type ChartTarget = { resultId: string; fields: ChartField[]; rows: ResultValue[][]; complete: boolean }

// A save that a newer one for the same result made pointless.
export class SupersededSave extends Error {}

const newId = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now()))

const blankQuestion = (position: number, question = ""): QuestionState => ({
  position,
  question,
  status: "pending",
  steps: [],
})

function withQuestion(turn: Turn, position: number, change: (question: QuestionState) => QuestionState): Turn {
  const index = turn.questions.findIndex((item) => item.position === position)
  const questions =
    index === -1
      ? [...turn.questions, change(blankQuestion(position))].sort((a, b) => a.position - b.position)
      : turn.questions.with(index, change(turn.questions[index]))
  return { ...turn, phase: "streaming", questions }
}

// A make_chart step changes the chart of the data step with the same result_id.
function applyChart(steps: ToolStep[], step: ToolStep): ToolStep[] {
  if (step.tool !== "make_chart" || step.error || !step.result_id || !step.chart) return steps
  return steps.map((item) => {
    if (item.result_id !== step.result_id || !DATA_TOOLS.has(item.tool)) return item
    const types = item.chart_types ?? []
    return {
      ...item,
      chart: step.chart,
      chart_source: step.chart_source ?? "agent",
      display: step.display ?? item.display,
      chart_types: types.includes(step.chart!.type) ? types : [step.chart!.type, ...types],
    }
  })
}

const isStoredQuestion = (value: unknown): value is StoredQuestion =>
  typeof value === "object" && value !== null && "position" in value && Array.isArray((value as StoredQuestion).steps)

// Stored steps have no rows: each successful data step takes the stored result with its result_id (the backend
// assigns one to old results too), or else the next result with the same position, tool and SQL.
function storedQuestions(steps: StoredQuestion[], results: StoredResult[]): QuestionState[] {
  const remaining = results.filter((result) => result.kind !== "column_values")
  return steps.map((item) => ({
    position: item.position,
    question: item.question,
    status: "answered",
    answer: item.answer,
    exhausted: item.exhausted,
    steps: item.steps.map((step) => {
      if (step.error || !DATA_TOOLS.has(step.tool)) return { ...step, columns: [], rows: [] }
      let index = step.result_id ? remaining.findIndex((result) => result.result_id === step.result_id) : -1
      if (index === -1) {
        index = remaining.findIndex(
          (result) => result.position === item.position && result.tool === step.tool && result.sql === step.sql,
        )
      }
      const result = index === -1 ? undefined : remaining.splice(index, 1)[0]
      if (!result) return { ...step, columns: [], rows: [] }
      return {
        ...step,
        columns: result.columns,
        rows: result.rows,
        truncated: step.truncated || !!result.stored_truncated,
        result_id: result.result_id ?? step.result_id,
        fields: result.fields?.length ? result.fields : inferFields(result.columns, result.rows),
        chart: result.chart !== undefined ? result.chart : step.chart,
        chart_source: result.chart_source ?? step.chart_source,
        chart_types: result.chart_types ?? step.chart_types,
        display: result.display ?? step.display ?? "none",
      }
    }),
  }))
}

function fromStored(stored: StoredTurn): Turn {
  const steps = stored.steps ?? []
  const legacy = !steps.every(isStoredQuestion)
  const finished = stored.status === "answered" || stored.status === "needs_clarification"
  const waiting = stored.status === "needs_clarification"
  // Older statuses (cannot_answer, join_ambiguous...) are shown as plain answers.
  const settled = finished || (stored.status !== "running" && stored.status !== "error")
  const outcome: DoneEvent | undefined = settled
    ? {
        status: waiting ? "needs_clarification" : "answered",
        answer: stored.answer ?? "",
        clarification_question: stored.clarification_question,
        clarification_options: stored.clarification_options,
        resume_id: waiting ? (stored.resume_id ?? null) : null,
        resume_expires_at: waiting ? (stored.resume_expires_at ?? null) : null,
        conversation_id: stored.conversation_id,
        turn_id: stored.id,
      }
    : undefined
  const stopped = stored.error_code === "client_disconnected"
  return {
    id: stored.id,
    request: { question: stored.question },
    conversationId: stored.conversation_id,
    turnId: stored.id,
    continuedFrom: stored.continued_from ?? undefined,
    startedAt: Date.parse(stored.created_at),
    duration: stored.duration_ms ?? 0,
    phase: outcome ? "done" : stopped ? "stopped" : "failed",
    questions: legacy ? [] : storedQuestions(steps as StoredQuestion[], (stored.results ?? []) as StoredResult[]),
    // A waiting turn stores its clarification question as the answer; it is shown as the question instead.
    answer: waiting ? "" : (stored.answer ?? ""),
    outcome,
    error:
      outcome || stopped
        ? undefined
        : stored.status === "running"
          ? { code: "running", message: "Lượt này chưa kết thúc khi được lưu." }
          : { code: stored.error_code ?? "error", message: stored.error ?? "Lượt hỏi đáp này gặp lỗi khi xử lý." },
    feedback: stored.feedback?.rating ?? null,
    views: stored.views ?? {},
    legacy: legacy && steps.length > 0,
  }
}

// Answer text arrives in many small events; they are applied together once per animation frame.
type Streamed = Extract<ChatEvent, { event: "answer_delta" | "answer_reset" }>

function applyStreamed(turn: Turn, event: Streamed): Turn {
  if (event.event === "answer_reset") {
    const { position, round } = event.data
    const next = turn.answerRound === round ? { ...turn, answer: "", answerRound: undefined } : turn
    return withQuestion(next, position, (question) =>
      question.draftRound === round ? { ...question, draft: undefined, draftRound: undefined } : question,
    )
  }
  const { position, round, final, text } = event.data
  if (final) {
    const answer = turn.answerRound === round || turn.answerRound === undefined ? turn.answer + text : text
    return { ...turn, phase: "streaming", answer, answerRound: round }
  }
  if (position === null) return turn
  return withQuestion(turn, position, (question) => ({
    ...question,
    draft: question.draftRound === round ? (question.draft ?? "") + text : text,
    draftRound: round,
  }))
}

// The server keeps the last 6 turns of what it is sent.
const HISTORY_TURNS = 6

// Finished turns on screen, for a chat without a user name that the server does not record.
function chatHistory(turns: Turn[]): ChatHistoryTurn[] {
  return turns
    .filter((turn) => turn.outcome)
    .slice(-HISTORY_TURNS)
    .map((turn) => ({
      question: turn.request.question,
      rewritten_question: turn.preprocess?.rewritten_question ?? null,
      answer: turn.outcome!.answer || null,
      status: turn.outcome!.status,
      clarification_question: turn.outcome!.clarification_question,
    }))
}

export function useChat(connectionId: string, userId: string) {
  const [turns, setTurns] = useState<Turn[]>([])
  // A conversation belongs to the user who started it; another name starts a new one.
  const [conversation, setConversation] = useState<{ id: string; userId: string } | null>(null)
  // The resume_id the user chose not to answer; the next message is then a new question.
  const [dismissed, setDismissed] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const turnsRef = useRef<Turn[]>([])
  const buffer = useRef<{ id: string; event: Streamed }[]>([])
  const frame = useRef<number | null>(null)
  const saves = useRef(new Map<string, { latest: number; chain: Promise<unknown> }>())
  const conversationId = conversation && conversation.userId === userId ? conversation.id : undefined

  useEffect(() => {
    turnsRef.current = turns
  }, [turns])

  useEffect(
    () => () => {
      controller.current?.abort()
      if (frame.current !== null) cancelAnimationFrame(frame.current)
    },
    [],
  )

  const update = useCallback((id: string, change: (turn: Turn) => Turn) => {
    setTurns((current) => current.map((turn) => (turn.id === id ? change(turn) : turn)))
  }, [])

  // Applies the buffered answer text in one state update.
  const flush = useCallback(() => {
    if (frame.current !== null) {
      cancelAnimationFrame(frame.current)
      frame.current = null
    }
    const pending = buffer.current
    if (!pending.length) return
    buffer.current = []
    setTurns((current) =>
      current.map((turn) =>
        pending.reduce((next, item) => (item.id === turn.id ? applyStreamed(next, item.event) : next), turn),
      ),
    )
  }, [])

  const run = useCallback(
    async (request: TurnRequest) => {
      if (controller.current) return
      const abort = new AbortController()
      controller.current = abort
      const id = newId()
      const user = userId
      const narration = { split: false, drafting: new Set<string>() }
      setTurns((current) => [
        ...current,
        {
          id,
          request,
          startedAt: Date.now(),
          phase: "sending",
          questions: [],
          answer: "",
          narration: request.resumeId ? "Đang tiếp tục với câu trả lời của bạn…" : FIRST_NARRATION,
          feedback: null,
          views: {},
        },
      ])
      const body: ChatRequest = {
        connectionId,
        question: request.question,
        userId: user || undefined,
        conversationId,
        resumeId: request.resumeId,
        chatHistory: user ? undefined : chatHistory(turnsRef.current),
      }
      const say = (message: ChatEvent) => {
        if (message.event === "preprocess") narration.split = message.data.is_split
        if (message.event === "answer_reset") {
          narration.drafting.delete(`true:${message.data.position}`)
          narration.drafting.delete(`false:${message.data.position}`)
        }
        const line = narrate(message, narration)
        if (line) update(id, (turn) => ({ ...turn, narration: line }))
      }
      try {
        for await (const message of streamChat(body, abort.signal)) {
          if (message.event === "answer_delta" || message.event === "answer_reset") {
            say(message)
            buffer.current.push({ id, event: message })
            frame.current ??= requestAnimationFrame(() => {
              frame.current = null
              flush()
            })
            continue
          }
          // Every other event applies after the text that came before it.
          flush()
          say(message)
          if (message.event === "turn") {
            const { conversation_id, turn_id } = message.data
            setConversation({ id: conversation_id, userId: user })
            update(id, (turn) => ({ ...turn, phase: "streaming", conversationId: conversation_id, turnId: turn_id }))
          } else if (message.event === "preprocess") {
            const preprocess = message.data
            const questions = preprocess.questions.map((item) => blankQuestion(item.position, item.question))
            update(id, (turn) => ({ ...turn, phase: "streaming", preprocess, questions }))
          } else if (message.event === "question_started") {
            const { position, question } = message.data
            update(id, (turn) =>
              withQuestion(turn, position, (current) => ({ ...current, question, status: "running" })),
            )
          } else if (message.event === "tool") {
            const { position, ...step } = message.data
            update(id, (turn) =>
              withQuestion(turn, position, (current) => ({
                ...current,
                steps: [...applyChart(current.steps, step), step],
              })),
            )
          } else if (message.event === "question_waiting") {
            const { position, question } = message.data
            update(id, (turn) =>
              withQuestion(turn, position, (current) => ({
                ...current,
                status: "waiting",
                clarification: question,
                draft: undefined,
                draftRound: undefined,
              })),
            )
          } else if (message.event === "question_answered") {
            const { position, question, answer, exhausted } = message.data
            update(id, (turn) =>
              withQuestion(turn, position, (current) => ({
                ...current,
                question,
                answer,
                exhausted,
                status: "answered",
                draft: undefined,
                draftRound: undefined,
              })),
            )
          } else if (message.event === "synthesize_started") {
            update(id, (turn) => ({
              ...turn,
              phase: "streaming",
              synthesizing: true,
              answer: "",
              answerRound: undefined,
            }))
          } else if (message.event === "answer") {
            const answer = message.data.answer
            update(id, (turn) => ({ ...turn, phase: "streaming", answer, answerRound: undefined }))
          } else if (message.event === "done") {
            const outcome = message.data
            update(id, (turn) => ({
              ...turn,
              phase: "done",
              outcome,
              narration: undefined,
              synthesizing: false,
              answer: outcome.status === "answered" ? outcome.answer || turn.answer : "",
              answerRound: undefined,
            }))
          } else if (message.event === "error") {
            const error = message.data
            update(id, (turn) => ({ ...turn, phase: "failed", error, narration: undefined, synthesizing: false }))
          }
        }
        flush()
        // A stream that closes without `done` or `error` was cut off (server restart, proxy timeout).
        update(id, (turn) =>
          turn.phase === "sending" || turn.phase === "streaming"
            ? {
                ...turn,
                phase: "failed",
                narration: undefined,
                error: { code: "interrupted", message: "Kết nối bị ngắt trước khi có câu trả lời đầy đủ." },
              }
            : turn,
        )
      } catch (error) {
        flush()
        if (abort.signal.aborted) {
          update(id, (turn) => ({ ...turn, phase: "stopped", narration: undefined, synthesizing: false }))
        } else {
          const message = error instanceof Error ? error.message : "Không thể gửi câu hỏi."
          update(id, (turn) => ({
            ...turn,
            phase: "failed",
            narration: undefined,
            error: { code: "request_failed", message },
          }))
        }
      } finally {
        if (controller.current === abort) controller.current = null
        // The first recorded turn creates the conversation; later ones move it to the top of the history.
        void refreshConversations(connectionId, user)
      }
    },
    [connectionId, conversationId, flush, update, userId],
  )

  // Only the last turn can be resumed, with the resume_id its stream returned, unless the user set it aside.
  const last = turns.at(-1)
  const resumeId = last?.outcome?.status === "needs_clarification" ? last.outcome.resume_id : null
  const pendingId = resumeId && resumeId !== dismissed ? resumeId : undefined
  const pending = pendingId ? { resumeId: pendingId, question: last?.outcome?.clarification_question ?? "" } : null

  const send = useCallback(
    (question: string) => {
      const text = question.trim()
      if (text) void run({ question: text, resumeId: pendingId })
    },
    [pendingId, run],
  )

  // A quick reply resumes the paused turn when possible; otherwise it is asked as a follow-up question, which a
  // recorded conversation understands from its history and a stateless chat needs the original question for.
  const reply = useCallback(
    (turn: Turn, option: string) => {
      if (pendingId && turn.id === last?.id) void run({ question: option, resumeId: pendingId })
      else void run({ question: turn.turnId ? option : `${turn.request.question} (${option})` })
    },
    [last?.id, pendingId, run],
  )

  const dismiss = useCallback(() => setDismissed(resumeId), [resumeId])

  const retry = useCallback((turn: Turn) => void run(turn.request), [run])

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

  // Saves of one result run one after another; a save that a newer one replaced while waiting is skipped.
  const serial = useCallback(<T,>(key: string, task: () => Promise<T>): Promise<T> => {
    const entry = saves.current.get(key) ?? { latest: 0, chain: Promise.resolve() }
    const ticket = entry.latest + 1
    const chain = entry.chain.catch(() => undefined).then(() => {
      if (saves.current.get(key)?.latest !== ticket) throw new SupersededSave()
      return task()
    })
    saves.current.set(key, { latest: ticket, chain })
    return chain
  }, [])

  // Checks and keeps the user's chart for a result: saved with the turn when it is recorded, otherwise only checked.
  // The turn shows the backend's normalized spec; a rejected chart leaves the previous one in place.
  const saveView = useCallback(
    (turn: Turn, target: ChartTarget, chart: ChartSpec): Promise<CheckedChart> => {
      const owner = userId
      return serial(`${turn.id}:${target.resultId}`, async () => {
        const current = turnsRef.current.find((item) => item.id === turn.id) ?? turn
        const recorded = current.conversationId && current.turnId && owner
        const checked = recorded
          ? await saveChartView(owner, current.conversationId!, current.turnId!, target.resultId, chart)
          : await validateChart(chart, target.fields, target.rows, target.complete)
        const view: ChartView = {
          chart: checked.chart,
          updated_at: "updated_at" in checked ? (checked.updated_at as string) : new Date().toISOString(),
        }
        update(turn.id, (item) => ({ ...item, views: { ...item.views, [target.resultId]: view } }))
        return { chart: checked.chart, warnings: checked.warnings }
      })
    },
    [serial, update, userId],
  )

  // Drops the user's chart so the agent's (or the suggested) one shows again.
  const resetView = useCallback(
    (turn: Turn, resultId: string) => {
      const owner = userId
      return serial(`${turn.id}:${resultId}`, async () => {
        const current = turnsRef.current.find((item) => item.id === turn.id) ?? turn
        if (current.conversationId && current.turnId && owner && current.views[resultId]) {
          await deleteChartView(owner, current.conversationId, current.turnId, resultId)
        }
        update(turn.id, (item) => {
          const views = { ...item.views }
          delete views[resultId]
          return { ...item, views }
        })
      })
    },
    [serial, update, userId],
  )

  const busy = last?.phase === "sending" || last?.phase === "streaming"
  const status = !busy ? "ready" : last.phase === "sending" ? "submitted" : "streaming"

  return {
    turns,
    status,
    busy,
    loading,
    conversationId,
    pending,
    send,
    reply,
    dismiss,
    retry,
    stop,
    clear,
    open,
    rate,
    saveView,
    resetView,
  } as const
}

export type ChatActions = Pick<ReturnType<typeof useChat>, "saveView" | "resetView">
