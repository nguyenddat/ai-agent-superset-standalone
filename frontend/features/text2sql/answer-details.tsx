"use client"

import { useMemo, type ReactNode } from "react"
import { ChevronRightIcon, EyeIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

import { todayIso } from "./charts/format"
import { QueryResult } from "./query-result"
import { explanationText, questionExplanations, type DataResult } from "./results"
import { useSubAnswersHidden } from "./sub-answers"
import type { ChatActions, Turn } from "./use-chat"

function RewriteNote({ turn }: { turn: Turn }) {
  const rewritten = turn.preprocess?.rewritten_question.trim()
  if (!rewritten || rewritten === turn.request.question.trim()) return null
  return (
    <p className="text-xs text-muted-foreground">
      Hiểu câu hỏi là: <span className="text-foreground">{rewritten}</span>
    </p>
  )
}

function HowComputed({ results }: { results: DataResult[] }) {
  const today = useMemo(() => todayIso(), [])
  const items = questionExplanations(results)
  if (!items.length) return null
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium">Cách tính</span>
      <ul className={cn(
        "ml-4 flex list-disc flex-col gap-0.5 text-xs text-muted-foreground",
        "marker:text-muted-foreground/60",
      )}>
        {items.map((item) => (
          <li key={`${item.kind}:${item.text}`}>{explanationText(item, today)}</li>
        ))}
      </ul>
    </div>
  )
}

// Everything behind the answer, folded away by default: how the question was read, how each figure was computed,
// the result tables with their charts and SQL, and the processing steps.
export function AnswerDetails({
  turn,
  results,
  actions,
  trace,
}: {
  turn: Turn
  results: DataResult[]
  actions: ChatActions
  trace: ReactNode
}) {
  const [hidden, setHidden] = useSubAnswersHidden()
  const split = turn.preprocess?.is_split ?? turn.questions.length > 1
  const groups = turn.questions
    .map((item) => ({ item, results: results.filter((result) => result.position === item.position) }))
    .filter((group) => group.results.length)
  return (
    <Collapsible className="min-w-0 rounded-lg border">
      <CollapsibleTrigger className={cn(
        "group flex w-full items-center gap-1.5 rounded-lg px-3 py-2 text-left",
        "text-sm font-medium outline-none focus-visible:ring-2",
        "focus-visible:ring-ring",
      )}>
        <ChevronRightIcon className={cn(
          "size-4 shrink-0 text-muted-foreground transition-transform",
          "group-data-[state=open]:rotate-90",
        )} />
        Số liệu và cách tính{results.length ? ` (${results.length})` : ""}
      </CollapsibleTrigger>
      <CollapsibleContent className="flex min-w-0 flex-col gap-4 border-t px-3 py-3">
        <RewriteNote turn={turn} />
        {groups.map(({ item, results: own }) => (
          <section key={item.position} className="flex min-w-0 flex-col gap-2">
            {split && (
              <h4 className="text-sm font-medium">
                Câu {item.position}: {item.question}
              </h4>
            )}
            <HowComputed results={own} />
            {own.map((result) => (
              <QueryResult key={result.id} turn={turn} result={result} actions={actions} />
            ))}
          </section>
        ))}
        {trace}
        {split && hidden && (
          <Button
            variant="ghost"
            size="sm"
            className="self-start text-muted-foreground"
            onClick={() => setHidden(false)}
          >
            <EyeIcon data-icon="inline-start" />
            Hiện trả lời từng phần
          </Button>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
