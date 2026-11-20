import { isChartSpec, isChartType, type ChartField, type ChartSpec, type ChartType } from "./charts/spec"
import { dateDisplay, nextDay, periodLabel } from "./charts/format"
import type { Explanation, ResultValue, ToolStep } from "./types"
import type { QuestionState, Turn } from "./use-chat"

// The tools whose rows are the data behind an answer; get_column_values only checks spelling.
export const DATA_TOOLS = new Set(["query_metric", "run_sql"])

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/

const humanize = (name: string) => {
  const words = name.replaceAll("_", " ").split(/\s+/).filter(Boolean).join(" ")
  return words ? words[0].toUpperCase() + words.slice(1) : name
}

// Only for results that came without fields (should not happen since the backend fills them for old turns too).
export function inferFields(columns: string[], rows: ResultValue[][]): ChartField[] {
  return columns.map((name, index) => {
    const values = rows.map((row) => row[index]).filter((value) => value !== null && value !== undefined)
    let type: ChartField["type"] = "text"
    if (!values.length) type = "other"
    else if (values.every((value) => typeof value === "boolean")) type = "boolean"
    else if (values.every((value) => typeof value === "number")) type = "number"
    else if (values.every((value) => typeof value === "string" && ISO_DATE.test(value))) type = "date"
    else if (values.every((value) => typeof value === "string" && (ISO_DATE.test(value) || ISO_DATETIME.test(value)))) {
      type = "datetime"
    }
    return { name, label: humanize(name), type, role: type === "number" ? "measure" : "dimension" }
  })
}

export type DataResult = {
  // result_id, or position-k for live steps of older backends.
  id: string
  position: number
  title: string
  step: ToolStep
  fields: ChartField[]
  // The agent's chart or the backend's suggestion; null for old turns.
  chart: ChartSpec | null
  types: ChartType[]
  display: ToolStep["display"]
  // The last successful query of its sub-question.
  last: boolean
  answered: boolean
}

const short = (text: string, size: number) => (text.length > size ? `${text.slice(0, size - 1)}…` : text)

// Every successful query behind the answer; a split question names the sub-question each result belongs to.
export function dataResults(turn: Turn): DataResult[] {
  const labels = new Map(
    (turn.preprocess?.questions ?? []).flatMap((item) =>
      item.metrics.map((metric) => [metric.name, metric.label ?? metric.name]),
    ),
  )
  const split = turn.preprocess?.is_split ?? turn.questions.length > 1
  return turn.questions.flatMap((item) => questionResults(item, labels, split))
}

function questionResults(item: QuestionState, labels: Map<string, string>, split: boolean): DataResult[] {
  const data = item.steps.filter((step) => DATA_TOOLS.has(step.tool) && !step.error && step.sql)
  return data.map((step, index) => {
    const metric = typeof step.arguments.metric === "string" ? step.arguments.metric : null
    const purpose = typeof step.arguments.purpose === "string" ? step.arguments.purpose.trim() : ""
    const fields = step.fields?.length ? step.fields : inferFields(step.columns, step.rows)
    // A reopened turn may lack the metric labels of the live run; the measure column carries the same label.
    const measure =
      fields.find((field) => field.name === metric)?.label ?? fields.find((field) => field.role === "measure")?.label
    const fallback = purpose ? short(purpose, 90) : "Kết quả truy vấn SQL"
    const name = metric ? (labels.get(metric) ?? measure ?? metric) : fallback
    const types = (step.chart_types ?? []).filter(isChartType)
    return {
      id: step.result_id ?? `${item.position}-${index + 1}`,
      position: item.position,
      title: split ? `Câu ${item.position}: ${name}` : name,
      step,
      fields,
      chart: isChartSpec(step.chart) ? step.chart : null,
      types: types.length ? types : ["table"],
      display: step.display ?? "none",
      last: index === data.length - 1,
      answered: item.status === "answered",
    }
  })
}

// Which results get a chart under the answer: the user's own non-table choice, the agent's chart, or the backend's
// suggestion for the last query of a sub-question. Only once that sub-question has its answer, to avoid flicker.
export function promotedResults(turn: Turn, results: DataResult[]): DataResult[] {
  return results.filter((result) => {
    const view = turn.views[result.id]?.chart
    if (view) return view.type !== "table"
    if (!result.answered) return false
    return result.display === "chart" || (result.display === "chart_if_last" && result.last)
  })
}

// The chart a result shows: the user's choice, then the agent's or suggested chart, then the table.
export function shownChart(turn: Turn, result: DataResult): { spec: ChartSpec; user: boolean } {
  const view = turn.views[result.id]?.chart
  if (view && isChartSpec(view)) return { spec: view, user: true }
  return { spec: result.chart ?? { type: "table" }, user: false }
}

// "Cách tính" lines: a period is re-labelled for the day it is read, the rest keep the backend's sentence.
export function explanationText(item: Explanation, today: string): string {
  if (item.kind === "period" && item.start && item.end) {
    return `Thời gian: ${periodLabel(item.start.slice(0, 10), nextDay(item.end.slice(0, 10)), today)}`
  }
  if (item.kind === "data_range" && item.start && item.end) {
    const start = dateDisplay(item.start.slice(0, 10), today, false)
    const end = dateDisplay(item.end.slice(0, 10), today, false)
    if (start && end) return `Không giới hạn thời gian: tính trên toàn bộ dữ liệu từ ${start} đến ${end}`
  }
  return item.text
}

// The explanations of a sub-question's results, without repeats.
export function questionExplanations(results: DataResult[]): Explanation[] {
  const seen = new Set<string>()
  return results.flatMap((result) =>
    (result.step.explanations ?? []).filter((item) => {
      if (seen.has(item.text)) return false
      seen.add(item.text)
      return true
    }),
  )
}
