"use client"

import { useMemo, useRef, useState } from "react"
import { ChevronDownIcon, CircleXIcon, EyeIcon, SigmaIcon, Table2Icon, Trash2Icon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { Combobox, type ComboboxOption } from "@/components/combobox"
import { SegmentedControl } from "@/components/segmented-control"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

import type { ModelTable } from "../business-model/types"
import { useTableDictionary } from "../data-dictionary/api"
import type { ColumnAggregation, ColumnDictionary } from "../data-dictionary/types"
import { createMetric, deleteMetric, updateMetric } from "./api"
import { CUSTOM_FORMAT, FORMAT_PRESETS, formatSample, metricTitle, suggestLabel, suggestName } from "./labels"
import type { Metric, MetricInput } from "./types"

type MetricEditorProps = {
  connectionId: string
  tables: ModelTable[]
  metrics: Metric[]
  metric: Metric | null
  initialTable: string | null
  onClose: () => void
  onSaved: (metric: Metric) => void
  onDeleted: () => void
  promotion?: MetricPromotion
}

// Promoting a user's own entry reuses this form: it opens with their wording and saves through the own-knowledge API.
export type MetricPromotion = {
  title: string
  seed: { table: string | null; label: string; description: string }
  create: (input: MetricInput) => Promise<Metric>
}

const isView = (tableType: string) => tableType.toLowerCase().includes("view")

function tableOption(table: ModelTable): ComboboxOption {
  const Icon = isView(table.table_type) ? EyeIcon : table.table_kind === "aggregate" ? SigmaIcon : Table2Icon
  return {
    value: table.table_id,
    label: table.display_name,
    description: `${table.schema_name}.${table.table_name}`,
    keywords: [table.table_name, table.schema_name],
    group: table.schema_name,
    icon: <Icon className="size-4 text-muted-foreground" />,
  }
}

const quote = (name: string) => (/^[a-z_][a-z0-9_]*$/.test(name) ? name : `"${name.replaceAll('"', '""')}"`)

function aggregate(fn: ColumnAggregation, column: string) {
  if (fn === "COUNT_DISTINCT") return `COUNT(DISTINCT ${quote(column)})`
  return `${fn}(${quote(column)})`
}

const nullable = (value: string) => (value.trim() ? value.trim() : null)

export function MetricEditor(props: MetricEditorProps) {
  const { connectionId, tables, metrics, metric, initialTable, onClose, onSaved, onDeleted, promotion } = props
  const byId = useMemo(() => new Map(tables.map((table) => [table.table_id, table])), [tables])
  const options = useMemo(() => tables.map(tableOption), [tables])
  const expressionRef = useRef<HTMLTextAreaElement>(null)

  const [tableId, setTableId] = useState<string | null>(metric?.table_id ?? promotion?.seed.table ?? initialTable)
  const [name, setName] = useState(metric?.name ?? "")
  const [nameTouched, setNameTouched] = useState(!!metric)
  const [label, setLabel] = useState(metric?.label ?? promotion?.seed.label ?? "")
  const [labelTouched, setLabelTouched] = useState(!!metric || !!promotion)
  const [expression, setExpression] = useState(metric?.expression ?? "")
  const [description, setDescription] = useState(metric?.description ?? promotion?.seed.description ?? "")
  const presetOf = (format: string | null | undefined) =>
    FORMAT_PRESETS.some((preset) => preset.value === (format ?? "")) ? (format ?? "") : CUSTOM_FORMAT
  const [formatChoice, setFormatChoice] = useState(presetOf(metric?.format))
  const [customFormat, setCustomFormat] = useState(metric?.format ?? "")
  const [currency, setCurrency] = useState(metric?.currency ?? "")
  const [metricType, setMetricType] = useState(metric?.metric_type ?? "")
  const [warning, setWarning] = useState(metric?.warning_text ?? "")
  const [advanced, setAdvanced] = useState(!!(metric?.metric_type || metric?.warning_text))
  const [busy, setBusy] = useState<"save" | "delete" | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [showErrors, setShowErrors] = useState(false)

  const table = tableId ? byId.get(tableId) : undefined
  const dictionary = useTableDictionary(tableId)
  const columns = dictionary.data?.table_id === tableId ? dictionary.data.columns : undefined
  const displayName = (column: string) => columns?.find((item) => item.name === column)?.display_name
  const format = formatChoice === CUSTOM_FORMAT ? customFormat : formatChoice
  const sample = formatSample(nullable(format), nullable(currency))

  const nameTaken =
    (error?.status === 409 && error.message.startsWith("Tên metric")) ||
    metrics.some((item) => item.id !== metric?.id && item.table_id === tableId && item.name === name.trim())
  const issues = {
    table: !tableId ? "Chọn bảng chứa metric." : null,
    name: !name.trim() ? "Đặt tên kỹ thuật cho metric." : null,
    expression: !expression.trim()
      ? "Viết biểu thức SQL tính metric."
      : expression.includes(";")
        ? "Biểu thức không được chứa dấu chấm phẩy."
        : null,
  }
  const valid = Object.values(issues).every((issue) => !issue) && !nameTaken

  function changeExpression(next: string) {
    setExpression(next)
    if (!nameTouched) setName(suggestName(next) ?? "")
    if (!labelTouched) setLabel(suggestLabel(next, displayName) ?? "")
  }

  // Inserts at the cursor, so a column can go inside a CASE WHEN as easily as into an empty field.
  function insert(text: string) {
    const area = expressionRef.current
    const start = area?.selectionStart ?? expression.length
    const end = area?.selectionEnd ?? expression.length
    changeExpression(expression.slice(0, start) + text + expression.slice(end))
    requestAnimationFrame(() => {
      area?.focus()
      area?.setSelectionRange(start + text.length, start + text.length)
    })
  }

  function input(): MetricInput {
    return {
      table_id: tableId!,
      name: name.trim(),
      expression: expression.trim(),
      label: nullable(label),
      description: nullable(description),
      format: nullable(format),
      currency: nullable(currency),
      metric_type: nullable(metricType),
      warning_text: nullable(warning),
    }
  }

  async function save() {
    setShowErrors(true)
    if (!valid) return
    setBusy("save")
    setError(null)
    try {
      const next = input()
      let saved: Metric
      if (metric) {
        // Only what changed goes out, so an edit never rewrites fields someone else touched meanwhile.
        const changes = Object.fromEntries(
          Object.entries(next).filter(([key, value]) => metric[key as keyof MetricInput] !== value),
        ) as Partial<MetricInput>
        saved = Object.keys(changes).length ? await updateMetric(connectionId, metric.id, changes) : metric
      } else {
        saved = promotion ? await promotion.create(next) : await createMetric(connectionId, next)
      }
      if (!promotion) toast.success(metric ? "Đã lưu metric" : "Đã tạo metric", { description: metricTitle(saved) })
      onSaved(saved)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không lưu được metric."))
    } finally {
      setBusy(null)
    }
  }

  async function remove() {
    if (!metric) return
    setBusy("delete")
    try {
      await deleteMetric(connectionId, metric.id)
      toast.success("Đã xóa metric", { description: metricTitle(metric) })
      onDeleted()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không xóa được metric."))
      setConfirmDelete(false)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section aria-label={metric ? "Sửa metric" : "Thêm metric"} className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-base font-medium">{promotion?.title ?? (metric ? "Sửa metric" : "Thêm metric")}</h2>
          <p className="text-sm text-muted-foreground">
            {promotion
              ? "Người dùng chỉ mô tả bằng lời. Hãy tự viết và kiểm tra biểu thức SQL; metric hoạt động ngay khi lưu."
              : "Một con số tính từ bảng, dùng lại được ở mọi biểu đồ."}
          </p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <form
          id="metric-form"
          className="flex flex-col gap-6 px-5 py-5"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <FieldGroup>
            <Field data-invalid={(showErrors && !!issues.table) || undefined}>
              <FieldLabel>Bảng</FieldLabel>
              <Combobox
                label="Bảng"
                placeholder="Chọn bảng chứa dữ liệu"
                searchPlaceholder="Tìm bảng"
                options={options}
                value={table ? tableOption(table) : null}
                onValueChange={(option) => {
                  setTableId(option?.value ?? null)
                  if (error?.status === 409) setError(null)
                }}
                width={360}
              />
              {showErrors && issues.table ? <FieldError>{issues.table}</FieldError> : null}
            </Field>

            <Field data-invalid={(showErrors && !!issues.expression) || undefined}>
              <FieldLabel htmlFor="metric-expression">Biểu thức SQL</FieldLabel>
              <Textarea
                ref={expressionRef}
                id="metric-expression"
                spellCheck={false}
                rows={4}
                maxLength={10000}
                className="max-h-64 font-mono text-xs"
                placeholder="VD: SUM(doanh_thu) hoặc COUNT(DISTINCT khach_hang_id)"
                aria-invalid={(showErrors && !!issues.expression) || undefined}
                value={expression}
                onChange={(event) => changeExpression(event.target.value)}
              />
              {showErrors && issues.expression ? (
                <FieldError>{issues.expression}</FieldError>
              ) : (
                <FieldDescription>Một biểu thức tổng hợp, không phải câu SELECT. Bấm cột bên dưới để chèn.</FieldDescription>
              )}
              <ColumnPicker
                loading={!!tableId && !columns && !dictionary.error}
                tableChosen={!!tableId}
                columns={columns ?? []}
                onInsert={insert}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={(nameTaken || (showErrors && !!issues.name)) || undefined}>
                <FieldLabel htmlFor="metric-name">Tên kỹ thuật</FieldLabel>
                <Input
                  id="metric-name"
                  maxLength={255}
                  spellCheck={false}
                  className="font-mono"
                  placeholder="VD: sum__doanh_thu"
                  aria-invalid={nameTaken || undefined}
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value)
                    setNameTouched(true)
                    if (error?.status === 409) setError(null)
                  }}
                />
                {nameTaken ? (
                  <FieldError>Bảng này đã có metric cùng tên.</FieldError>
                ) : showErrors && issues.name ? (
                  <FieldError>{issues.name}</FieldError>
                ) : null}
              </Field>
              <Field>
                <FieldLabel htmlFor="metric-label">Tên hiển thị</FieldLabel>
                <Input
                  id="metric-label"
                  maxLength={255}
                  placeholder="VD: Tổng doanh thu"
                  value={label}
                  onChange={(event) => {
                    setLabel(event.target.value)
                    setLabelTouched(true)
                  }}
                />
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor="metric-description">Mô tả</FieldLabel>
              <Textarea
                id="metric-description"
                rows={2}
                placeholder="Metric này đo gì, dùng khi nào. Không bắt buộc."
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </Field>
          </FieldGroup>

          <Separator />

          <FieldGroup>
            <Field>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <FieldLabel>Định dạng số</FieldLabel>
                {sample ? (
                  <span className="text-sm text-muted-foreground">
                    Hiển thị: <span className="font-mono text-foreground tabular-nums">{sample}</span>
                  </span>
                ) : null}
              </div>
              <SegmentedControl
                label="Định dạng số"
                size="sm"
                block
                value={formatChoice}
                onValueChange={setFormatChoice}
                options={[
                  ...FORMAT_PRESETS.map((preset) => ({ value: preset.value, label: preset.label })),
                  { value: CUSTOM_FORMAT, label: "Tùy chỉnh" },
                ]}
              />
              {formatChoice === CUSTOM_FORMAT ? (
                <Input
                  aria-label="Định dạng tùy chỉnh"
                  maxLength={128}
                  spellCheck={false}
                  className="font-mono"
                  placeholder="Theo d3-format, VD: ,.1f"
                  value={customFormat}
                  onChange={(event) => setCustomFormat(event.target.value)}
                />
              ) : null}
            </Field>
            <Field className="sm:max-w-48">
              <FieldLabel htmlFor="metric-currency">Đơn vị tiền tệ</FieldLabel>
              <Input
                id="metric-currency"
                maxLength={16}
                placeholder="VD: VND"
                value={currency}
                onChange={(event) => setCurrency(event.target.value)}
              />
            </Field>
          </FieldGroup>

          <Collapsible open={advanced} onOpenChange={setAdvanced}>
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="-ml-2">
                <ChevronDownIcon
                  data-icon="inline-start"
                  className={cn("transition-transform", !advanced && "-rotate-90")}
                />
                Thêm thông tin
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <FieldGroup className="pt-3">
                <Field className="sm:max-w-64">
                  <FieldLabel htmlFor="metric-type">Loại metric</FieldLabel>
                  <Input
                    id="metric-type"
                    maxLength={64}
                    placeholder="VD: sum, count"
                    value={metricType}
                    onChange={(event) => setMetricType(event.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="metric-warning">Cảnh báo khi dùng</FieldLabel>
                  <Textarea
                    id="metric-warning"
                    rows={2}
                    placeholder="VD: Chưa gồm đơn hàng bị hủy."
                    value={warning}
                    onChange={(event) => setWarning(event.target.value)}
                  />
                  <FieldDescription>Hiện cạnh metric để người dùng biết giới hạn của con số.</FieldDescription>
                </Field>
              </FieldGroup>
            </CollapsibleContent>
          </Collapsible>

          {error && !nameTaken ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </ScrollArea>

      <footer className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
        {metric ? (
          confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-sm">Xóa metric này?</span>
              <Button type="button" variant="destructive" size="sm" disabled={busy !== null} onClick={() => void remove()}>
                {busy === "delete" ? <Spinner data-icon="inline-start" /> : null}
                Xóa
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                Giữ lại
              </Button>
            </div>
          ) : (
            <Button type="button" variant="ghost" size="sm" className="text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2Icon data-icon="inline-start" />
              Xóa
            </Button>
          )
        ) : null}
        <div className="ml-auto flex gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" form="metric-form" disabled={busy !== null}>
            {busy === "save" ? <Spinner data-icon="inline-start" /> : null}
            {promotion ? "Đưa vào kho" : metric ? "Lưu thay đổi" : "Tạo metric"}
          </Button>
        </div>
      </footer>
    </section>
  )
}

type InsertMode = ColumnAggregation | "column"

const INSERT_MODES: { value: InsertMode; label: string }[] = [
  { value: "SUM", label: "SUM" },
  { value: "AVG", label: "AVG" },
  { value: "MIN", label: "MIN" },
  { value: "MAX", label: "MAX" },
  { value: "COUNT_DISTINCT", label: "COUNT DISTINCT" },
  { value: "column", label: "Chỉ tên cột" },
]

const ROLE_ORDER = ["measure", "key", "time", "dimension", "label", "row_kind", "attribute"]

function ColumnPicker({
  loading,
  tableChosen,
  columns,
  onInsert,
}: {
  loading: boolean
  tableChosen: boolean
  columns: ColumnDictionary[]
  onInsert: (text: string) => void
}) {
  const [mode, setMode] = useState<InsertMode>("SUM")
  const [query, setQuery] = useState("")
  if (!tableChosen) return <p className="text-sm text-muted-foreground">Chọn bảng để thấy cột gợi ý.</p>
  if (loading) return <Skeleton className="h-28" />

  const term = query.trim().toLowerCase()
  // Measures first: they are what a metric usually adds up.
  const shown = columns
    .filter((column) => !term || column.name.toLowerCase().includes(term) || column.display_name.toLowerCase().includes(term))
    .sort((a, b) => ROLE_ORDER.indexOf(a.semantic_role) - ROLE_ORDER.indexOf(b.semantic_role))

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border bg-muted/30 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">Bấm cột để chèn</span>
        <SegmentedControl
          label="Cách chèn cột"
          size="sm"
          value={mode}
          onValueChange={(value) => setMode(value as InsertMode)}
          options={INSERT_MODES}
        />
      </div>
      <div className="flex items-center gap-2">
        <Input
          aria-label="Lọc cột"
          placeholder="Lọc cột"
          className="h-7 flex-1 text-xs"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button type="button" variant="outline" size="xs" className="font-mono" onClick={() => onInsert("COUNT(*)")}>
          COUNT(*)
        </Button>
      </div>
      <div className="flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
        {shown.map((column) => {
          const text = mode === "column" ? quote(column.name) : aggregate(mode, column.name)
          return (
            <button
              key={column.column_id}
              type="button"
              title={`Chèn ${text} · ${column.display_name} · ${column.data_type}`}
              className="cursor-pointer rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
              onClick={() => onInsert(text)}
            >
              <Badge variant={column.semantic_role === "measure" ? "secondary" : "outline"} className="font-mono">
                {column.name}
              </Badge>
            </button>
          )
        })}
        {shown.length === 0 ? <span className="text-xs text-muted-foreground">Không có cột khớp.</span> : null}
      </div>
    </div>
  )
}
