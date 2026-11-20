"use client"

import { useEffect, useRef, useState } from "react"
import { BarChart3Icon, RotateCcwIcon, SlidersHorizontalIcon, TableIcon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api"

import { shownChart, type DataResult } from "../results"
import type { ChatActions, Turn } from "../use-chat"
import { SupersededSave } from "../use-chat"
import { useChartCatalog } from "./catalog"
import { ChartEditor } from "./chart-editor"
import { ChartSwitcher } from "./chart-switcher"
import { ChartView } from "./chart-view"
import { ResultTable } from "./result-table"
import type { ChartSpec, ChartType } from "./spec"
import { defaultSpecFor } from "./suggest"

const DEBOUNCE_MS = 600

// One result's chart with its toolbar: type switcher, editor, table view and reset. Changes are checked by the
// backend (and saved with the turn when it is recorded); the chart always shows the last spec that passed.
type ChartPanelProps = { turn: Turn; result: DataResult; actions: ChatActions; title?: string }

export function ChartPanel({ turn, result, actions, title }: ChartPanelProps) {
  const { data: catalog } = useChartCatalog()
  const { spec, user } = shownChart(turn, result)
  const [draft, setDraft] = useState<ChartSpec | null>(null)
  const [editing, setEditing] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [asTable, setAsTable] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  const step = result.step
  const target = {
    resultId: result.id,
    fields: result.fields,
    rows: step.rows,
    complete: !step.truncated,
  }

  const submit = (next: ChartSpec) => {
    setSaving(true)
    actions
      .saveView(turn, target, next)
      .then((checked) => {
        setErrors([])
        setWarnings(checked.warnings)
      })
      .catch((error: unknown) => {
        if (error instanceof SupersededSave) return
        if (error instanceof ApiError && error.status === 400) setErrors(error.message.split("\n").filter(Boolean))
        else {
          const message = error instanceof Error ? error.message : "Không lưu được biểu đồ."
          setErrors([message])
          if (!editing) toast.error(message)
        }
      })
      .finally(() => setSaving(false))
  }

  const change = (next: ChartSpec) => {
    setDraft(next)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => submit(next), DEBOUNCE_MS)
  }

  const switchType = (type: ChartType) => {
    if (type === spec.type) return
    const next = defaultSpecFor(type, result.fields, step.rows, spec)
    setDraft(null)
    setAsTable(false)
    submit(next)
  }

  const reset = () => {
    if (timer.current) clearTimeout(timer.current)
    setDraft(null)
    setErrors([])
    setWarnings([])
    actions.resetView(turn, result.id).catch((error: unknown) => {
      if (error instanceof SupersededSave) return
      toast.error(error instanceof Error ? error.message : "Không đặt lại được biểu đồ.")
    })
  }

  const info = catalog?.types.find((item) => item.type === (draft ?? spec).type)
  // A suggested title can be a bare column name; its label or the result's own title reads better.
  const named = result.fields.find((field) => field.name === spec.title)
  const heading = named ? named.label || title || spec.title : spec.title || title
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {heading && <span className="mr-auto min-w-0 text-sm font-medium">{heading}</span>}
        <div className={heading ? "flex flex-wrap items-center gap-1.5" : "flex w-full flex-wrap items-center gap-1.5"}>
          <ChartSwitcher
            value={spec.type}
            types={result.types}
            enabled={catalog?.enabled}
            disabled={saving}
            onChange={switchType}
          />
          {spec.type !== "table" && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setDraft(spec)
                setEditing(true)
              }}
            >
              <SlidersHorizontalIcon data-icon="inline-start" />
              Tùy chỉnh
            </Button>
          )}
          {spec.type !== "table" && (
            <Button variant="ghost" size="sm" aria-pressed={asTable} onClick={() => setAsTable((value) => !value)}>
              {asTable ? <BarChart3Icon data-icon="inline-start" /> : <TableIcon data-icon="inline-start" />}
              {asTable ? "Xem biểu đồ" : "Xem dạng bảng"}
            </Button>
          )}
          {user && (
            <Button variant="ghost" size="sm" onClick={reset}>
              <RotateCcwIcon data-icon="inline-start" />
              Đặt lại
            </Button>
          )}
        </div>
      </div>
      {errors.length > 0 && !editing && (
        <p className="text-xs text-destructive" role="alert">
          {errors[0]}
        </p>
      )}
      {asTable ? (
        <ResultTable fields={result.fields} rows={step.rows} label={heading ?? "Kết quả"} />
      ) : (
        <ChartView spec={spec} fields={result.fields} rows={step.rows} suggested={result.chart} showTitle={false} />
      )}
      {spec.subtitle && !asTable && <p className="text-xs text-muted-foreground">{spec.subtitle}</p>}
      {draft && (
        <ChartEditor
          open={editing}
          onOpenChange={(open) => {
            setEditing(open)
            if (!open) setErrors([])
          }}
          spec={draft}
          info={info}
          fields={result.fields}
          rows={step.rows}
          errors={errors}
          warnings={warnings}
          saving={saving}
          onChange={change}
          onReset={user || result.chart ? reset : undefined}
        />
      )}
    </div>
  )
}
