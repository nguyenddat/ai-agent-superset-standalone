"use client"

import { CornerDownRightIcon, PencilIcon, RotateCcwIcon } from "lucide-react"

import { ChatNotice } from "@/components/chat-notice"
import { AnswerActions, FollowUps, StreamingText, type AnswerStatus } from "@/components/streaming-answer"
import { ThinkingTrace, type ThinkingStatus } from "@/components/thinking-trace"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { Message, MessageContent } from "@/components/ui/message"

import { AnswerDetails } from "./answer-details"
import { AnswerMarkdown } from "./answer-markdown"
import { ChartArea } from "./chart-area"
import { traceSteps } from "./labels"
import { dataResults } from "./results"
import { SubAnswers } from "./sub-answers"
import type { Rating } from "./types"
import type { ChatActions, Turn } from "./use-chat"

export type TurnActions = {
  busy: boolean
  onReply: (turn: Turn, option: string) => void
  onRetry: (turn: Turn) => void
  onEdit: (question: string) => void
  onRate?: (turn: Turn, rating: Rating | null) => void
  actions: ChatActions
}

export function UserTurn({ turn }: { turn: Turn }) {
  const reply = !!turn.request.resumeId || !!turn.continuedFrom
  return (
    <Message align="end">
      <MessageContent>
        {reply && (
          <span className="flex items-center justify-end gap-1 text-xs text-muted-foreground">
            <CornerDownRightIcon className="size-3.5" />
            Trả lời câu hỏi lại của AI
          </span>
        )}
        <Bubble variant="secondary" align="end">
          <BubbleContent className="whitespace-pre-wrap">{turn.request.question}</BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}

const isLive = (turn: Turn) => turn.phase === "sending" || turn.phase === "streaming"

function traceStatus(turn: Turn): ThinkingStatus {
  if (turn.phase === "stopped") return "cancelled"
  if (turn.phase === "failed") return "error"
  return isLive(turn) && !turn.answer ? "running" : "done"
}

function answerStatus(turn: Turn): AnswerStatus {
  if (isLive(turn)) return "streaming"
  if (turn.phase === "stopped") return "stopped"
  if (turn.phase === "failed") return "error"
  return "done"
}

function Clarification({ turn, busy, onReply }: { turn: Turn; busy: boolean; onReply: (option: string) => void }) {
  const question = turn.outcome?.clarification_question
  const options = turn.outcome?.clarification_options ?? []
  if (!question && !options.length) return null
  return (
    <div className="flex flex-col gap-2">
      {question && <p className="text-sm font-medium whitespace-pre-wrap">{question}</p>}
      {options.length > 0 && (
        <FollowUps items={options} label="Chọn nhanh một câu trả lời" onSelect={(option) => !busy && onReply(option)} />
      )}
    </div>
  )
}

// The answer comes first, then the charts brought up for it, the sub-question answers of a split question and,
// folded away, the figures and how they were computed. While live, one line says what is happening.
export function AssistantTurn({ turn, busy, onReply, onRetry, onEdit, onRate, actions }: { turn: Turn } & TurnActions) {
  const live = isLive(turn)
  const steps = traceSteps(turn)
  const results = dataResults(turn)
  const waiting = turn.outcome?.status === "needs_clarification"
  const split = turn.preprocess?.is_split ?? turn.questions.length > 1
  const rate = onRate && turn.turnId ? (rating: Rating | null) => onRate(turn, rating) : undefined
  const trace =
    steps.length > 0 ? (
      <ThinkingTrace
        steps={steps}
        status={traceStatus(turn)}
        startedAt={turn.startedAt}
        duration={turn.duration}
        defaultOpen={false}
      />
    ) : null

  return (
    <Message align="start">
      <MessageContent className="w-full min-w-0 gap-3">
        {live && (
          <ThinkingTrace
            steps={steps}
            status="running"
            label={turn.narration ?? "Đang xử lý"}
            startedAt={turn.startedAt}
            defaultOpen={false}
          />
        )}
        {turn.answer ? (
          <Bubble variant="ghost">
            <BubbleContent className="w-full min-w-0">
              <StreamingText status={answerStatus(turn)}>
                <AnswerMarkdown text={turn.answer} streaming={live} />
              </StreamingText>
            </BubbleContent>
          </Bubble>
        ) : (
          live && <div aria-hidden className="h-6" />
        )}
        <ChartArea turn={turn} results={results} actions={actions} />
        {split && <SubAnswers turn={turn} />}
        {turn.legacy && (
          <p className="text-xs text-muted-foreground">
            Lượt này được ghi bởi phiên bản cũ nên không hiện các bước xử lý.
          </p>
        )}
        {waiting && <Clarification turn={turn} busy={busy} onReply={(option) => onReply(turn, option)} />}
        {turn.phase === "failed" && (
          <ChatNotice
            kind="error"
            title={turn.answer ? "Câu trả lời bị gián đoạn" : "Chưa trả lời được câu hỏi"}
            description={turn.error?.message}
            details={turn.error?.code}
            onRetry={busy ? undefined : () => onRetry(turn)}
          />
        )}
        {(results.length > 0 || (!live && trace)) && (
          <AnswerDetails turn={turn} results={results} actions={actions} trace={live ? null : trace} />
        )}
        {!live && (turn.answer || waiting || turn.phase === "stopped") && (
          <div className="flex flex-wrap items-center gap-2">
            {turn.answer ? (
              <AnswerActions
                copyText={turn.answer}
                onRegenerate={() => onRetry(turn)}
                feedback={rate ? turn.feedback : undefined}
                onFeedback={rate}
                disabled={busy}
              />
            ) : (
              turn.phase === "stopped" && (
                <Button variant="outline" size="sm" disabled={busy} onClick={() => onRetry(turn)}>
                  <RotateCcwIcon data-icon="inline-start" />
                  Hỏi lại
                </Button>
              )
            )}
            {waiting && (
              <Button variant="outline" size="sm" disabled={busy} onClick={() => onEdit(turn.request.question)}>
                <PencilIcon data-icon="inline-start" />
                Sửa câu hỏi
              </Button>
            )}
          </div>
        )}
      </MessageContent>
    </Message>
  )
}
