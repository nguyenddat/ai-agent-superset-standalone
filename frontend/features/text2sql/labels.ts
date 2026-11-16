import type { ThinkingStep } from "@/components/thinking-trace"

import type { StepEvent, StepName } from "./types"
import type { TurnStep } from "./use-chat"

export const STEP_LABELS: Record<StepName, string> = {
  rewrite: "Hiểu câu hỏi",
  metric_search: "Tìm metric phù hợp",
  metric_query: "Truy vấn metric",
  field_search: "Tìm trường dữ liệu",
  dataset_plan: "Lập kế hoạch truy vấn",
  join_plan: "Tính cách nối bảng",
  dataset_query: "Chạy truy vấn nhiều bảng",
  analysis: "Viết câu trả lời",
}

const OUTCOMES: Record<string, string> = {
  answered: "có kết quả",
  needs_clarification: "cần làm rõ",
  cannot_answer: "chưa trả lời được",
}

function stepDetail({ step, status, detail }: StepEvent): string | undefined {
  if (status === "skipped") return "bỏ qua"
  if (status !== "done") return undefined
  switch (step) {
    case "rewrite": {
      const used = (detail.glossary_terms?.length ?? 0) + (detail.rules?.length ?? 0) + (detail.own_knowledge?.length ?? 0)
      return used ? `dùng ${used} mục tri thức` : undefined
    }
    case "metric_search":
      return detail.candidates?.length ? `${detail.candidates.length} ứng viên` : "không có ứng viên"
    case "field_search":
      if (detail.match === "none" || !detail.tables?.length) return "không tìm thấy"
      return `${detail.tables.length} bảng`
    case "join_plan":
      if (detail.status === "ambiguous") return `${detail.options?.length ?? 0} cách nối`
      if (detail.status === "not_declared") return "chưa khai báo quan hệ"
      if (detail.chosen) return "theo cách đã chọn"
      return detail.tables?.length ? `${detail.tables.length} bảng` : undefined
    case "dataset_plan":
      if (detail.outcome === "ok") return detail.tables?.length ? `${detail.tables.length} bảng` : undefined
      return detail.outcome ? OUTCOMES[detail.outcome] : undefined
    default:
      return detail.outcome ? OUTCOMES[detail.outcome] : undefined
  }
}

// The analysis step is the answer itself, shown as streaming text rather than as a row of the trace.
// A step still marked started after the turn ended is where the turn failed.
export function traceSteps(steps: TurnStep[], live: boolean): ThinkingStep[] {
  return steps
    .filter((item) => item.step !== "analysis")
    .map((item) => ({
      label: STEP_LABELS[item.step],
      detail: stepDetail(item),
      status: item.status !== "started" ? "done" : live ? "running" : "error",
      notes: item.reasoning.map((line) => line.text.trim()).filter(Boolean),
    }))
}
