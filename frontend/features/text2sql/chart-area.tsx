"use client"

import { ChartPanel } from "./charts/chart-panel"
import { promotedResults, type DataResult } from "./results"
import type { ChatActions, Turn } from "./use-chat"

// The charts brought up under the answer: what the agent chose to show, the suggestion for the last query of a
// sub-question, or what the user picked.
export function ChartArea({ turn, results, actions }: { turn: Turn; results: DataResult[]; actions: ChatActions }) {
  const shown = promotedResults(turn, results)
  if (!shown.length) return null
  return (
    <div className="flex flex-col gap-3">
      {shown.map((result) => (
        <section
          key={result.id}
          className="min-w-0 rounded-lg border bg-card p-3"
          aria-label={`Biểu đồ: ${result.title}`}
        >
          <ChartPanel turn={turn} result={result} actions={actions} title={result.title} />
        </section>
      ))}
    </div>
  )
}
