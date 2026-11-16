"use client"

import Link from "next/link"
import { BookOpenIcon, CheckIcon, InfoIcon, PencilIcon, RotateCcwIcon, SplitIcon, UnlinkIcon } from "lucide-react"

import { ChatNotice } from "@/components/chat-notice"
import { AnswerActions, FollowUps, StreamingText, type AnswerStatus } from "@/components/streaming-answer"
import { ThinkingTrace, type ThinkingStatus } from "@/components/thinking-trace"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from "@/components/ui/item"
import { Message, MessageContent } from "@/components/ui/message"

import { AnswerMarkdown } from "./answer-markdown"
import { traceSteps } from "./labels"
import { QueryResult } from "./query-result"
import type { JoinOptionDetail, Rating, StepDetail } from "./types"
import type { Turn } from "./use-chat"

export type TurnActions = {
  connectionId: string
  busy: boolean
  onAsk: (question: string) => void
  onRetry: (turn: Turn) => void
  onEdit: (question: string) => void
  onChoose: (turn: Turn, option: JoinOptionDetail) => void
  onRate?: (turn: Turn, rating: Rating | null) => void
}

export function UserTurn({ turn }: { turn: Turn }) {
  const choice = turn.request.choice
  return (
    <Message align="end">
      <MessageContent>
        <Bubble variant="secondary" align="end">
          <BubbleContent className="whitespace-pre-wrap">
            {choice ? (
              <span className="flex items-center gap-1.5">
                <SplitIcon className="size-3.5 shrink-0" />
                {choice.label}
              </span>
            ) : (
              turn.request.question
            )}
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}

const isLive = (turn: Turn) => turn.phase === "sending" || turn.phase === "streaming"

function traceStatus(turn: Turn): ThinkingStatus {
  if (turn.phase === "stopped") return "cancelled"
  if (turn.phase === "failed" && !turn.answer) return "error"
  const answering = turn.steps.some((item) => item.step === "analysis")
  return answering || !isLive(turn) ? "done" : "running"
}

function answerStatus(turn: Turn): AnswerStatus {
  if (isLive(turn)) return "streaming"
  if (turn.phase === "stopped") return "stopped"
  if (turn.phase === "failed") return "error"
  return "done"
}

const detailOf = (turn: Turn, step: string): StepDetail | undefined =>
  turn.steps.find((item) => item.step === step && item.status === "done")?.detail

function RewriteNote({ turn }: { turn: Turn }) {
  const detail = detailOf(turn, "rewrite")
  const assumptions = turn.outcome?.assumptions ?? []
  const rewritten = detail?.rewritten_question?.trim()
  const changed = !!rewritten && rewritten !== detail?.original_question?.trim()
  const used = [
    ...(detail?.glossary_terms ?? []).map((name) => ({ name, kind: "Thuật ngữ" })),
    ...(detail?.rules ?? []).map((name) => ({ name, kind: "Quy tắc" })),
    ...(detail?.own_knowledge ?? []).map((name) => ({ name, kind: "Tri thức riêng" })),
  ]
  if (!changed && !used.length && !assumptions.length) return null
  return (
    <div className="flex flex-col gap-1.5 text-xs text-muted-foreground">
      {changed && (
        <p>
          Hiểu câu hỏi là: <span className="text-foreground">{rewritten}</span>
        </p>
      )}
      {used.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span>Đã dùng:</span>
          {used.map((item) => (
            <Badge key={`${item.kind}:${item.name}`} variant="outline" title={item.kind}>
              {item.name}
            </Badge>
          ))}
        </div>
      )}
      {assumptions.length > 0 && (
        <div className="flex items-start gap-1.5">
          <InfoIcon className="mt-px size-3.5 shrink-0" />
          <div className="flex flex-col gap-0.5">
            <span>AI đã giả định:</span>
            <ul className="ml-4 list-disc">
              {assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

type JoinChoice = { chosen: Set<string>; canChoose: boolean; busy: boolean; onChoose: (option: JoinOptionDetail) => void }

function JoinOptions({ turn, chosen, canChoose, busy, onChoose }: { turn: Turn } & JoinChoice) {
  const options = detailOf(turn, "join_plan")?.options ?? []
  if (!options.length) return null
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Các cách nối bảng</CardTitle>
        <CardDescription>
          {canChoose
            ? "Hệ thống không tự chọn. Chọn một cách nối để chạy tiếp truy vấn."
            : "Hệ thống không tự chọn. Hãy hỏi lại và nói rõ cách nối bạn muốn dùng; đặt tên người dùng để chọn trực tiếp."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ItemGroup className="gap-2">
          {options.map((option) => {
            const content = (
              <ItemContent>
                <ItemTitle>
                  Cách {option.number}: bắt đầu từ {option.root_table}
                  {chosen.has(option.signature) && (
                    <Badge>
                      <CheckIcon data-icon="inline-start" />
                      Đã chọn
                    </Badge>
                  )}
                  {option.previously_used && <Badge variant="secondary">Đã dùng trước đây</Badge>}
                </ItemTitle>
                <ItemDescription className="line-clamp-none">
                  {option.joins.length ? option.joins.join("; ") : option.tables.join(", ")}
                </ItemDescription>
              </ItemContent>
            )
            return canChoose ? (
              <Item key={option.signature} variant="outline" size="sm" asChild>
                <button type="button" className="text-left" disabled={busy} onClick={() => onChoose(option)}>
                  {content}
                </button>
              </Item>
            ) : (
              <Item key={option.signature} variant="outline" size="sm">
                {content}
              </Item>
            )
          })}
        </ItemGroup>
      </CardContent>
    </Card>
  )
}

function NotDeclared({ connectionId }: { connectionId: string }) {
  return (
    <Alert>
      <UnlinkIcon />
      <AlertTitle>Các bảng chưa được khai báo quan hệ</AlertTitle>
      <AlertDescription>
        <p>Khai báo cột tham chiếu giữa các bảng trong từ điển dữ liệu rồi hỏi lại.</p>
        <Button variant="outline" size="sm" className="mt-2" asChild>
          <Link href={`/connections/${connectionId}/dictionary`}>
            <BookOpenIcon data-icon="inline-start" />
            Mở từ điển dữ liệu
          </Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}

// A recorded turn has the conversation as context, so a short reply is enough; otherwise the reply needs the question.
function Clarification({ turn, busy, onAsk }: { turn: Turn; busy: boolean; onAsk: (question: string) => void }) {
  const question = turn.outcome?.clarification_question
  const options = turn.outcome?.clarification_options ?? []
  if (!question && !options.length) return null
  const reply = (option: string) => onAsk(turn.turnId ? option : `${turn.request.question} (${option})`)
  return (
    <div className="flex flex-col gap-2">
      {question && <p className="text-sm font-medium">{question}</p>}
      {options.length > 0 && (
        <FollowUps items={options} label="Chọn nhanh một hướng" onSelect={(option) => !busy && reply(option)} />
      )}
    </div>
  )
}

export function AssistantTurn({
  turn,
  connectionId,
  busy,
  chosen,
  canChoose,
  onAsk,
  onRetry,
  onEdit,
  onChoose,
  onRate,
}: { turn: Turn; chosen: Set<string>; canChoose: boolean } & TurnActions) {
  const live = isLive(turn)
  const steps = traceSteps(turn.steps, live)
  const status = turn.outcome?.status
  const canRephrase = status === "needs_clarification" || status === "cannot_answer" || status === "join_ambiguous"
  const message = !turn.answer && turn.outcome?.message
  const rate = onRate && turn.turnId ? (rating: Rating | null) => onRate(turn, rating) : undefined

  return (
    <Message align="start">
      <MessageContent className="gap-3">
        {(steps.length > 0 || live) && (
          <ThinkingTrace steps={steps} status={traceStatus(turn)} startedAt={turn.startedAt} duration={turn.duration} />
        )}
        <RewriteNote turn={turn} />
        {turn.results.map((data, index) => (
          <QueryResult key={index} data={data} />
        ))}
        {status === "join_ambiguous" && (
          <JoinOptions turn={turn} chosen={chosen} canChoose={canChoose} busy={busy} onChoose={(option) => onChoose(turn, option)} />
        )}
        {turn.answer && (
          <Bubble variant="ghost">
            <BubbleContent className="w-full">
              <StreamingText status={answerStatus(turn)}>
                <AnswerMarkdown text={turn.answer} />
              </StreamingText>
            </BubbleContent>
          </Bubble>
        )}
        {message && <p className="text-sm">{message}</p>}
        {status === "needs_clarification" && <Clarification turn={turn} busy={busy} onAsk={onAsk} />}
        {status === "join_not_declared" && <NotDeclared connectionId={connectionId} />}
        {turn.phase === "failed" && (
          <ChatNotice
            kind="error"
            title={turn.answer ? "Câu trả lời bị gián đoạn" : "Chưa trả lời được câu hỏi"}
            description={turn.error?.message}
            details={turn.error?.code}
            onRetry={busy ? undefined : () => onRetry(turn)}
          />
        )}
        {status === "error" && (
          <ChatNotice
            kind="error"
            title="Một bước xử lý gặp lỗi"
            description="Hệ thống chưa xử lý trọn vẹn câu hỏi. Bạn có thể thử lại sau ít phút."
            onRetry={busy ? undefined : () => onRetry(turn)}
          />
        )}
        {!live && (turn.answer || canRephrase || turn.phase === "stopped") && (
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
            {canRephrase && (
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
