"use client"

import { Badge } from "@/components/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

import { TERM_STATES, termState } from "./labels"
import type { GlossaryTerm } from "./types"

// `explained` adds a focusable tooltip, so leave it off inside a clickable row.
export function TermStatus({ term, size = "md", explained }: { term: GlossaryTerm; size?: "sm" | "md"; explained?: boolean }) {
  const state = TERM_STATES[termState(term)]
  const badge = (
    <Badge tone={state.tone} size={size} dot title={explained ? undefined : state.hint}>
      {state.label}
    </Badge>
  )
  if (!explained) return badge
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50" tabIndex={0}>
          {badge}
        </span>
      </TooltipTrigger>
      <TooltipContent>{state.hint}</TooltipContent>
    </Tooltip>
  )
}
