"use client"

import { Badge } from "@/components/badge"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

import { RULE_STATES, ruleState } from "./labels"
import type { ExpertRule } from "./types"

// `explained` adds a focusable tooltip, so leave it off inside a clickable row.
export function RuleStatus({ rule, size = "md", explained }: { rule: ExpertRule; size?: "sm" | "md"; explained?: boolean }) {
  const state = RULE_STATES[ruleState(rule)]
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
