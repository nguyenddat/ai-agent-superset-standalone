"use client"

import { useSyncExternalStore } from "react"
import { ChevronRightIcon, EyeOffIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

import { AnswerMarkdown } from "./answer-markdown"
import type { Turn } from "./use-chat"

const HIDDEN_KEY = "text2sql.subAnswers.hidden"
const CHANGE = "text2sql-sub-answers"

const read = () => {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1"
  } catch {
    return false
  }
}

const subscribe = (onChange: () => void) => {
  window.addEventListener(CHANGE, onChange)
  window.addEventListener("storage", onChange)
  return () => {
    window.removeEventListener(CHANGE, onChange)
    window.removeEventListener("storage", onChange)
  }
}

// Hiding the per-question answers applies to every turn and is remembered by the browser.
export function useSubAnswersHidden() {
  const hidden = useSyncExternalStore(subscribe, read, () => false)
  const setHidden = (value: boolean) => {
    try {
      if (value) window.localStorage.setItem(HIDDEN_KEY, "1")
      else window.localStorage.removeItem(HIDDEN_KEY)
    } catch {
      // Without storage the choice lasts until the page reloads.
    }
    window.dispatchEvent(new Event(CHANGE))
  }
  return [hidden, setHidden] as const
}

// A split question: each sub-question's own answer (its draft while streaming), folded away by default.
export function SubAnswers({ turn }: { turn: Turn }) {
  const [hidden, setHidden] = useSubAnswersHidden()
  const items = turn.questions.filter((item) => item.answer || item.draft || item.clarification)
  if (hidden || !items.length) return null
  return (
    <Collapsible className="rounded-lg border">
      <div className="flex items-center gap-2 pr-1.5">
        <CollapsibleTrigger className={cn(
          "group flex flex-1 items-center gap-1.5 rounded-lg px-3 py-2 text-left",
          "text-sm font-medium outline-none focus-visible:ring-2",
          "focus-visible:ring-ring",
        )}>
          <ChevronRightIcon className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            "group-data-[state=open]:rotate-90",
          )} />
          Trả lời từng phần ({items.length})
        </CollapsibleTrigger>
        <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setHidden(true)}>
          <EyeOffIcon data-icon="inline-start" />
          Ẩn mục này
        </Button>
      </div>
      <CollapsibleContent className="flex flex-col gap-3 border-t px-3 py-3 text-sm">
        {items.map((item) => (
          <section key={item.position} className="flex flex-col gap-1">
            <h4 className="text-xs font-medium text-muted-foreground">
              Câu {item.position}: {item.question}
            </h4>
            {item.answer ? (
              <AnswerMarkdown text={item.answer} />
            ) : item.draft ? (
              <div className="text-muted-foreground">
                <AnswerMarkdown text={item.draft} streaming />
              </div>
            ) : (
              <p className="text-muted-foreground">Hỏi lại: {item.clarification}</p>
            )}
          </section>
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}
