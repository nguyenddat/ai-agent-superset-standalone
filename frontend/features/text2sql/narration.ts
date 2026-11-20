import type { ChatEvent } from "./types"

// The one line that says what the assistant is doing, from fixed templates (no extra LLM call).
const TOOL_NARRATION: Record<string, (subject: string | null) => string> = {
  get_metric: (subject) => (subject ? `Đang tìm chỉ số «${subject}»…` : "Đang tìm chỉ số…"),
  get_table: (subject) => (subject ? `Đang xem dữ liệu «${subject}»…` : "Đang xem dữ liệu…"),
  get_expert_rule: (subject) => (subject ? `Đang đọc quy tắc «${subject}»…` : "Đang đọc quy tắc…"),
  get_column_values: (subject) => (subject ? `Đang kiểm tra cách ghi «${subject}»…` : "Đang kiểm tra cách ghi…"),
  query_metric: (subject) => (subject ? `Đang truy vấn «${subject}»…` : "Đang truy vấn…"),
  run_sql: (subject) => (subject ? `Đang tính: ${subject}…` : "Đang chạy truy vấn…"),
  make_chart: () => "Đang dựng biểu đồ…",
}

export const FIRST_NARRATION = "Đang đọc câu hỏi…"

type State = { split: boolean; drafting: Set<string> }

// Returns the new line for an event, or null to keep the current one.
export function narrate(event: ChatEvent, state: State): string | null {
  const prefix = (position: number | null | undefined) => (state.split && position ? `Câu ${position}: ` : "")
  switch (event.event) {
    case "preprocess":
      return event.data.is_split ? `Đã tách thành ${event.data.questions.length} câu hỏi nhỏ` : null
    case "question_started":
      return event.data.resumed ? "Đang tiếp tục với câu trả lời của bạn…" : null
    case "tool_started": {
      const line = TOOL_NARRATION[event.data.tool]
      return line ? prefix(event.data.position) + line(event.data.subject) : null
    }
    case "tool":
      return event.data.error ? prefix(event.data.position) + "Truy vấn chưa được, đang thử cách khác…" : null
    case "answer_reset":
      return prefix(event.data.position) + "Đang tra thêm dữ liệu…"
    case "answer_delta": {
      const key = `${event.data.final}:${event.data.position}`
      if (state.drafting.has(key)) return null
      state.drafting.add(key)
      if (!event.data.final && event.data.position) return `Đang viết câu trả lời cho câu ${event.data.position}…`
      return "Đang viết câu trả lời…"
    }
    case "synthesize_started":
      return "Đang tổng hợp câu trả lời…"
    case "question_waiting":
      return "Đang chờ bạn trả lời"
    default:
      return null
  }
}
