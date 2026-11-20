import type { ThinkingStep } from "@/components/thinking-trace"

import type { ToolStep } from "./types"
import type { QuestionState, Turn } from "./use-chat"

export const TOOL_LABELS: Record<string, string> = {
  get_metric: "Đọc định nghĩa chỉ số",
  get_table: "Xem mô tả bảng",
  get_expert_rule: "Đọc quy tắc",
  get_column_values: "Tra giá trị cột",
  query_metric: "Tính chỉ số",
  run_sql: "Chạy truy vấn",
  make_chart: "Dựng biểu đồ",
  ask_user: "Hỏi lại bạn",
}

const ARGUMENT_NAMES = ["metric", "table", "rule", "column", "purpose", "result_id"] as const

function toolNote(step: ToolStep): string {
  const label = TOOL_LABELS[step.tool] ?? step.tool
  const subject = ARGUMENT_NAMES.map((name) => step.arguments[name]).find((value) => typeof value === "string")
  const head = subject ? `${label}: ${subject}` : label
  if (step.error) return `${head} (lỗi: ${step.error})`
  if (step.sql) return `${head} (${step.truncated ? `hơn ${step.row_count}` : step.row_count} dòng)`
  return head
}

const isLive = (turn: Turn) => turn.phase === "sending" || turn.phase === "streaming"

function questionStep(item: QuestionState, split: boolean, live: boolean): ThinkingStep {
  const status =
    item.status === "answered" || item.status === "waiting"
      ? "done"
      : item.status === "running"
        ? live
          ? "running"
          : "error"
        : live
          ? "pending"
          : "error"
  const calls = item.steps.length
  return {
    label: split ? `Câu ${item.position}: ${item.question}` : "Truy vấn dữ liệu",
    detail: item.status === "waiting" ? "chờ bạn trả lời" : calls ? `${calls} bước` : undefined,
    status,
    notes: [
      ...item.steps.map(toolNote),
      ...(item.exhausted ? ["Hết lượt gọi công cụ, trả lời bằng kết quả đã có"] : []),
    ],
  }
}

// A step still running when the turn ended is where the turn failed.
export function traceSteps(turn: Turn): ThinkingStep[] {
  const live = isLive(turn)
  const steps: ThinkingStep[] = []
  const resumed = !!turn.request.resumeId || !!turn.continuedFrom
  const preprocess = turn.preprocess
  if (preprocess) {
    const notes = preprocess.is_split ? preprocess.questions.map((item) => `${item.position}. ${item.question}`) : []
    steps.push({
      label: "Hiểu câu hỏi",
      detail: preprocess.is_split ? `tách thành ${preprocess.questions.length} câu` : undefined,
      status: "done",
      notes,
    })
  } else if (!resumed && !turn.legacy && turn.questions.length === 0 && (live || turn.phase === "failed")) {
    steps.push({ label: "Hiểu câu hỏi", status: live ? "running" : "error" })
  }
  const split = preprocess?.is_split ?? turn.questions.length > 1
  steps.push(...turn.questions.map((item) => questionStep(item, split, live)))
  const answered = turn.questions.length > 0 && turn.questions.every((item) => item.status === "answered")
  if (split && answered && (live || turn.answer || turn.synthesizing)) {
    steps.push({ label: "Tổng hợp câu trả lời", status: turn.answer ? "done" : live ? "running" : "error" })
  }
  return steps
}
