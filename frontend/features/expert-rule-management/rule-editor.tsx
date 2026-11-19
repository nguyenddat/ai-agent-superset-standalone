"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { BookTextIcon, CircleXIcon, PlusIcon, SigmaIcon, Table2Icon, Trash2Icon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { Combobox, type ComboboxOption } from "@/components/combobox"
import { SegmentedControl } from "@/components/segmented-control"
import { TagInput } from "@/components/tag-input"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"

import { DomainPicker } from "../business-model/domains"
import { foldName, normalizeName } from "../glossary-management/labels"
import { createRule, saveRuleDraft } from "./api"
import { OPERATORS, OPERATORS_BY_KIND, columnKind, valueTypeFor } from "./labels"
import type { RuleRefs, TableRef } from "./rule-refs"
import type { ExpertRule, Operator, OptionColumn, RuleCondition, RuleContent, RuleCreate, ValueType } from "./types"

type RuleEditorProps = {
  connectionId: string
  rules: ExpertRule[]
  refs: RuleRefs
  rule: ExpertRule | null
  initialTable: string | null
  onClose: () => void
  onSaved: (rule: ExpertRule) => void
  onReload: () => void
  promotion?: RulePromotion
}

// Promoting a user's own entry reuses this form: it opens with their wording and saves through the own-knowledge API.
export type RulePromotion = {
  title: string
  seed: { name: string; table: string | null; description: string }
  create: (input: RuleCreate) => Promise<ExpertRule>
}

type ConditionDraft = {
  key: number
  column_id: string | null
  operator: Operator
  value_type: ValueType
  text: string
  items: string[]
  flag: boolean
}
type PairDraft = { key: number; first: string; second: string }

let nextKey = 0
const key = () => ++nextKey

function toDraft(condition: RuleCondition): ConditionDraft {
  const { value } = condition
  return {
    key: key(),
    column_id: condition.column_id,
    operator: condition.operator,
    value_type: condition.value_type,
    text: value === null || Array.isArray(value) || typeof value === "boolean" ? "" : String(value),
    items: Array.isArray(value) ? value.map(String) : [],
    flag: value === true,
  }
}

const emptyCondition = (): ConditionDraft => ({
  key: key(),
  column_id: null,
  operator: "equals",
  value_type: "string",
  text: "",
  items: [],
  flag: true,
})

function fromDraft(draft: ConditionDraft, column: OptionColumn | undefined): RuleCondition | string {
  if (!draft.column_id || !column) return "Chọn cột."
  const base = { column_id: draft.column_id, operator: draft.operator, value_type: draft.value_type }
  const numeric = columnKind(column.data_type) === "number"
  switch (draft.value_type) {
    case "null":
      return { ...base, value: null }
    case "boolean":
      return { ...base, value: draft.flag }
    case "number": {
      const value = Number(draft.text.trim().replace(",", "."))
      return draft.text.trim() && Number.isFinite(value) ? { ...base, value } : "Nhập một số."
    }
    case "array": {
      if (!draft.items.length) return "Thêm ít nhất một giá trị."
      if (!numeric) return { ...base, value: draft.items }
      const values = draft.items.map((item) => Number(item.replace(",", ".")))
      return values.every(Number.isFinite) ? { ...base, value: values } : "Mọi giá trị phải là số."
    }
    default:
      return draft.text.trim() ? { ...base, value: draft.text } : "Nhập giá trị."
  }
}

function tableOption(table: TableRef): ComboboxOption {
  return {
    value: table.table_id,
    label: table.displayName,
    description: table.schemaName ? `${table.schemaName}.${table.name}` : table.name,
    keywords: [table.name, table.schemaName],
    group: table.schemaName || undefined,
    icon: <Table2Icon className="size-4 text-muted-foreground" />,
  }
}

const pairIssue = (pair: PairDraft) => !!pair.first.trim() !== !!pair.second.trim()
const filled = (pair: PairDraft) => !!pair.first.trim() && !!pair.second.trim()

export function RuleEditor(props: RuleEditorProps) {
  const { connectionId, rules, refs, rule, initialTable, onClose, onSaved, onReload, promotion } = props
  const revision = rule?.current

  const [name, setName] = useState(rule?.name ?? promotion?.seed.name ?? "")
  const [tableId, setTableId] = useState<string | null>(rule?.table_id ?? promotion?.seed.table ?? initialTable)
  const [domainIds, setDomainIds] = useState<string[]>(rule?.business_domains.map((domain) => domain.id) ?? [])
  const [description, setDescription] = useState(revision?.description ?? promotion?.seed.description ?? "")
  const [conditions, setConditions] = useState<ConditionDraft[]>(
    revision ? revision.conditions.map(toDraft) : [emptyCondition()],
  )
  const [exceptions, setExceptions] = useState<PairDraft[]>(
    revision?.exceptions.map((item) => ({ key: key(), first: item.when, second: item.outcome })) ?? [],
  )
  const [examples, setExamples] = useState<PairDraft[]>(
    revision?.examples.map((item) => ({ key: key(), first: item.question, second: item.intent })) ?? [],
  )
  const [terms, setTerms] = useState<string[]>(revision?.glossary_term_ids ?? [])
  const [metrics, setMetrics] = useState<string[]>(revision?.metric_ids ?? [])
  // The revision this edit started from: saving on top of a newer one is a conflict, not an overwrite.
  const [baseRevision] = useState(revision?.number ?? 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [showErrors, setShowErrors] = useState(false)

  const table = tableId ? refs.tableById.get(tableId) : undefined
  const columnById = useMemo(() => new Map(table?.columns.map((column) => [column.id, column])), [table])
  const termOptions: ComboboxOption[] = (table?.glossary_terms ?? []).map((term) => ({
    value: term.id,
    label: term.name,
    icon: <BookTextIcon className="size-4 text-muted-foreground" />,
  }))
  const metricOptions: ComboboxOption[] = (table?.metrics ?? []).map((metric) => {
    const known = refs.metricById.get(metric.id)
    return {
      value: metric.id,
      label: known?.label?.trim() || metric.name,
      description: known?.expression,
      keywords: [metric.name],
      icon: <SigmaIcon className="size-4 text-muted-foreground" />,
    }
  })
  // A link chosen earlier that the table no longer offers still shows, so the user sees what to replace.
  const selected = (ids: string[], options: ComboboxOption[], nameOf: (id: string) => string | undefined) =>
    ids.map(
      (id) =>
        options.find((option) => option.value === id) ?? {
          value: id,
          label: nameOf(id) ?? "Không rõ",
          description: "Không còn chọn được cho bảng này",
        },
    )

  const built = conditions.map((draft) => fromDraft(draft, draft.column_id ? columnById.get(draft.column_id) : undefined))
  const nameTaken =
    (!rule && error?.status === 409 && error.message.startsWith("Tên expert rule")) ||
    (!rule && !!name.trim() && rules.some((item) => foldName(item.name) === foldName(name)))
  const staleTerms = terms.filter((id) => !termOptions.some((option) => option.value === id))
  const staleMetrics = metrics.filter((id) => !metricOptions.some((option) => option.value === id))
  const issues = {
    name: !rule && !normalizeName(name) ? "Đặt tên cho quy tắc." : null,
    table: !tableId ? "Chọn bảng mà quy tắc áp dụng." : null,
    conditions: conditions.length ? null : "Thêm ít nhất một điều kiện.",
    exceptions: exceptions.some(pairIssue) ? "Mỗi ngoại lệ cần cả trường hợp và cách xử lý." : null,
    examples: examples.some(pairIssue) ? "Mỗi ví dụ cần cả câu hỏi và ý định." : null,
    terms: !terms.length
      ? "Chọn ít nhất một thuật ngữ."
      : staleTerms.length
        ? "Bỏ thuật ngữ không còn chọn được."
        : null,
    metrics: staleMetrics.length ? "Bỏ metric không còn chọn được." : null,
  }
  const valid =
    !nameTaken && Object.values(issues).every((issue) => !issue) && built.every((item) => typeof item !== "string")
  const conflict = !!rule && error?.status === 409

  function changeTable(next: string | null) {
    if (next === tableId) return
    setTableId(next)
    // Columns, terms and metrics all belong to the table, so they go with it.
    setConditions((items) => items.map((item) => ({ ...item, column_id: null })))
    setTerms([])
    setMetrics([])
  }

  async function save() {
    setShowErrors(true)
    if (!valid) return
    const content: RuleContent = {
      description: description.trim() || null,
      conditions: built as RuleCondition[],
      exceptions: exceptions.filter(filled).map((pair) => ({ when: pair.first.trim(), outcome: pair.second.trim() })),
      examples: examples.filter(filled).map((pair) => ({ question: pair.first.trim(), intent: pair.second.trim() })),
      glossary_term_ids: terms,
      metric_ids: metrics,
    }
    setBusy(true)
    setError(null)
    try {
      const saved = rule
        ? await saveRuleDraft(connectionId, rule.id, { ...content, business_domain_ids: domainIds, expected_revision: baseRevision })
        : await (promotion?.create ?? createRule)({
            ...content,
            connection_id: connectionId,
            table_id: tableId!,
            name: normalizeName(name),
            business_domain_ids: domainIds,
          })
      if (rule && saved.current.number === rule.current.number) {
        toast.info("Không có thay đổi nội dung", { description: saved.name })
      } else if (!promotion) {
        toast.success(rule ? "Đã lưu bản nháp" : "Đã tạo quy tắc", { description: `${saved.name} đang chờ duyệt.` })
      }
      onSaved(saved)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không lưu được quy tắc."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label={rule ? "Sửa quy tắc" : "Thêm quy tắc"} className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="truncate text-base font-medium">{promotion?.title ?? (rule ? `Sửa ${rule.name}` : "Thêm quy tắc")}</h2>
          <p className="text-sm text-muted-foreground">
            {promotion
              ? "Người dùng chỉ mô tả bằng lời. Hãy dựng điều kiện và chọn thuật ngữ cho đúng trước khi lưu."
              : "Lưu sẽ tạo bản nháp. AI chỉ áp dụng quy tắc sau khi được duyệt."}
          </p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      {/* Radix sizes the viewport content as a table, which lets the nowrap selects push the form past the panel. */}
      <ScrollArea className="min-h-0 flex-1 [&_[data-slot=scroll-area-viewport]>div]:block!">
        <form
          id="rule-form"
          className="flex flex-col gap-6 px-5 py-5"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <FieldGroup>
            {rule ? null : (
              <>
                <Field data-invalid={(nameTaken || (showErrors && !!issues.name)) || undefined}>
                  <FieldLabel htmlFor="rule-name">Tên quy tắc</FieldLabel>
                  <Input
                    id="rule-name"
                    maxLength={255}
                    placeholder="VD: Ngày nắng nóng"
                    aria-invalid={(nameTaken || (showErrors && !!issues.name)) || undefined}
                    value={name}
                    onChange={(event) => {
                      setName(event.target.value)
                      if (error?.status === 409) setError(null)
                    }}
                  />
                  {nameTaken ? (
                    <FieldError>Kết nối này đã có quy tắc cùng tên.</FieldError>
                  ) : showErrors && issues.name ? (
                    <FieldError>{issues.name}</FieldError>
                  ) : null}
                </Field>
                <Field data-invalid={(showErrors && !!issues.table) || undefined}>
                  <FieldLabel>Bảng</FieldLabel>
                  <Combobox
                    label="Bảng"
                    placeholder="Chọn bảng quy tắc áp dụng"
                    searchPlaceholder="Tìm bảng"
                    options={refs.tables.map(tableOption)}
                    value={table ? tableOption(table) : null}
                    onValueChange={(option) => changeTable(option?.value ?? null)}
                    width={360}
                  />
                  {showErrors && issues.table ? (
                    <FieldError>{issues.table}</FieldError>
                  ) : (
                    <FieldDescription>Điều kiện, thuật ngữ và metric đều lấy từ bảng này. Không đổi được sau khi tạo.</FieldDescription>
                  )}
                </Field>
              </>
            )}

            <Field>
              <FieldLabel>Miền nghiệp vụ</FieldLabel>
              <DomainPicker connectionId={connectionId} value={domainIds} onChange={setDomainIds} />
              <FieldDescription>Một quy tắc có thể thuộc nhiều miền của semantic model.</FieldDescription>
            </Field>

            <Field>
              <FieldLabel htmlFor="rule-description">Mô tả</FieldLabel>
              <Textarea
                id="rule-description"
                rows={3}
                maxLength={10000}
                placeholder="VD: Ngày có nhiệt độ cao nhất từ 35 độ C trở lên được tính là ngày nắng nóng."
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <FieldDescription>Quy tắc nói gì, bằng lời của chuyên gia. Không bắt buộc.</FieldDescription>
            </Field>
          </FieldGroup>

          <Separator />

          <FieldSet className="min-w-0">
            <FieldLegend>Điều kiện</FieldLegend>
            <FieldDescription>Mỗi điều kiện so một cột của bảng với một giá trị.</FieldDescription>
            {!table ? (
              <p className="text-sm text-muted-foreground">Chọn bảng để thấy các cột.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {conditions.map((draft, index) => (
                  <ConditionRow
                    key={draft.key}
                    index={index}
                    draft={draft}
                    columns={table.columns}
                    error={showErrors && typeof built[index] === "string" ? (built[index] as string) : null}
                    onChange={(next) => setConditions((items) => items.map((item) => (item.key === draft.key ? next : item)))}
                    onRemove={() => setConditions((items) => items.filter((item) => item.key !== draft.key))}
                  />
                ))}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  disabled={conditions.length >= 50}
                  onClick={() => setConditions((items) => [...items, emptyCondition()])}
                >
                  <PlusIcon data-icon="inline-start" />
                  Thêm điều kiện
                </Button>
              </div>
            )}
            {showErrors && issues.conditions ? <FieldError>{issues.conditions}</FieldError> : null}
          </FieldSet>

          <PairList
            legend="Ngoại lệ"
            description="Trường hợp quy tắc không áp dụng như bình thường, và khi đó xử lý thế nào."
            firstLabel="Khi"
            firstPlaceholder="VD: Trạm đang bảo trì"
            secondLabel="Thì"
            secondPlaceholder="VD: Bỏ qua số đo của ngày đó"
            addLabel="Thêm ngoại lệ"
            items={exceptions}
            onChange={setExceptions}
            error={showErrors ? issues.exceptions : null}
          />

          <PairList
            legend="Câu hỏi ví dụ"
            description="Câu hỏi người dùng hay đặt mà quy tắc này trả lời, và ý định đằng sau."
            firstLabel="Câu hỏi"
            firstPlaceholder="VD: Tuần này có mấy ngày nắng nóng?"
            secondLabel="Ý định"
            secondPlaceholder="VD: Đếm số ngày thỏa quy tắc trong tuần"
            addLabel="Thêm ví dụ"
            items={examples}
            onChange={setExamples}
            error={showErrors ? issues.examples : null}
          />

          <Separator />

          <FieldGroup>
            <Field data-invalid={(showErrors && !!issues.terms) || undefined}>
              <FieldLabel>Thuật ngữ liên quan</FieldLabel>
              {table && !termOptions.length && !terms.length ? (
                <Alert>
                  <BookTextIcon />
                  <AlertTitle>Bảng này chưa có thuật ngữ dùng được</AlertTitle>
                  <AlertDescription>
                    Quy tắc cần ít nhất một thuật ngữ đã duyệt có liên kết tới bảng {table.displayName}.
                  </AlertDescription>
                  <AlertAction>
                    <Button size="sm" variant="outline" asChild>
                      <Link href={`/connections/${connectionId}/glossary`}>Mở Thuật ngữ</Link>
                    </Button>
                  </AlertAction>
                </Alert>
              ) : (
                <Combobox
                  multiple
                  label="Thuật ngữ liên quan"
                  placeholder={table ? "Chọn thuật ngữ" : "Chọn bảng trước"}
                  searchPlaceholder="Tìm thuật ngữ"
                  options={termOptions}
                  value={selected(terms, termOptions, (id) => refs.termById.get(id)?.canonical_name)}
                  onValueChange={(options) => setTerms(options.map((option) => option.value))}
                  emptyMessage={(query) => (query ? `Không thấy “${query}”` : "Chưa có thuật ngữ dùng được")}
                  disabled={!table}
                  max={50}
                />
              )}
              {showErrors && issues.terms ? (
                <FieldError>{issues.terms}</FieldError>
              ) : (
                <FieldDescription>Chỉ gồm thuật ngữ đã duyệt và có liên kết tới bảng này.</FieldDescription>
              )}
            </Field>

            <Field data-invalid={(showErrors && !!issues.metrics) || undefined}>
              <FieldLabel>Metric</FieldLabel>
              <Combobox
                multiple
                label="Metric"
                placeholder={table ? "Không bắt buộc" : "Chọn bảng trước"}
                searchPlaceholder="Tìm metric"
                options={metricOptions}
                value={selected(metrics, metricOptions, (id) => refs.metricById.get(id)?.name)}
                onValueChange={(options) => setMetrics(options.map((option) => option.value))}
                emptyMessage={(query) => (query ? `Không thấy “${query}”` : "Bảng này chưa có metric")}
                disabled={!table}
                max={50}
              />
              {showErrors && issues.metrics ? (
                <FieldError>{issues.metrics}</FieldError>
              ) : (
                <FieldDescription>Con số quy tắc dùng tới, nếu có.</FieldDescription>
              )}
            </Field>
          </FieldGroup>

          {conflict ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertTitle>Quy tắc vừa được thay đổi ở nơi khác</AlertTitle>
              <AlertDescription>Tải lại để sửa trên bản mới nhất. Nội dung bạn đang nhập sẽ bị bỏ.</AlertDescription>
              <AlertAction>
                <Button type="button" size="sm" variant="outline" onClick={onReload}>
                  Tải lại
                </Button>
              </AlertAction>
            </Alert>
          ) : error && !nameTaken ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </ScrollArea>

      <footer className="flex items-center justify-end gap-2 border-t px-5 py-3">
        <Button type="button" variant="ghost" onClick={onClose}>
          Hủy
        </Button>
        <Button type="submit" form="rule-form" disabled={busy || conflict}>
          {busy ? <Spinner data-icon="inline-start" /> : null}
          {promotion ? "Đưa vào kho" : rule ? "Lưu bản nháp" : "Tạo quy tắc"}
        </Button>
      </footer>
    </section>
  )
}

function ConditionRow({
  index,
  draft,
  columns,
  error,
  onChange,
  onRemove,
}: {
  index: number
  draft: ConditionDraft
  columns: OptionColumn[]
  error: string | null
  onChange: (draft: ConditionDraft) => void
  onRemove: () => void
}) {
  const column = columns.find((item) => item.id === draft.column_id)
  const kind = column ? columnKind(column.data_type) : "text"
  const operators = OPERATORS_BY_KIND[kind]
  const label = `điều kiện ${index + 1}`

  // A new column or operator decides the value's type; a stored condition keeps its own until then.
  function retype(next: Partial<Pick<ConditionDraft, "column_id" | "operator">>) {
    const nextColumn = columns.find((item) => item.id === (next.column_id ?? draft.column_id))
    const nextKind = nextColumn ? columnKind(nextColumn.data_type) : "text"
    const allowed = OPERATORS_BY_KIND[nextKind]
    const operator = allowed.includes(next.operator ?? draft.operator) ? (next.operator ?? draft.operator) : allowed[0]!
    onChange({ ...draft, ...next, operator, value_type: valueTypeFor(operator, nextKind) })
  }

  return (
    <Field
      data-invalid={!!error || undefined}
      className="@container gap-2 rounded-lg border bg-muted/30 p-3"
      role="group"
      aria-label={label}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Select value={draft.column_id ?? ""} onValueChange={(value) => retype({ column_id: value })}>
          <SelectTrigger aria-label={`Cột của ${label}`} className="min-w-0 flex-1 basis-full @sm:basis-0" aria-invalid={(!!error && !column) || undefined}>
            <SelectValue placeholder="Chọn cột" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {columns.map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  <span className="font-mono">{item.name}</span>
                  <span className="text-xs text-muted-foreground">{item.data_type}</span>
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Select value={draft.operator} onValueChange={(value) => retype({ operator: value as Operator })}>
          <SelectTrigger aria-label={`Phép so của ${label}`} className="min-w-0 flex-1 @sm:w-40 @sm:flex-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {operators.map((operator) => (
                <SelectItem key={operator} value={operator}>
                  {OPERATORS[operator]}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button type="button" variant="ghost" size="icon-sm" aria-label={`Bỏ ${label}`} onClick={onRemove}>
          <Trash2Icon />
        </Button>
      </div>
      {draft.value_type === "null" ? null : draft.value_type === "boolean" ? (
        <SegmentedControl
          label={`Giá trị của ${label}`}
          size="sm"
          value={draft.flag ? "true" : "false"}
          onValueChange={(value) => onChange({ ...draft, flag: value === "true" })}
          options={[
            { value: "true", label: "Đúng" },
            { value: "false", label: "Sai" },
          ]}
        />
      ) : draft.value_type === "array" ? (
        <TagInput
          label={`Giá trị của ${label}`}
          placeholder="Các giá trị, ngăn cách bằng dấu phẩy"
          max={100}
          value={draft.items.map((item) => ({ id: item, value: item }))}
          onValueChange={(tags) => onChange({ ...draft, items: tags.filter((tag) => !tag.error).map((tag) => tag.value) })}
          validate={(value) =>
            kind === "number" && !Number.isFinite(Number(value.replace(",", "."))) ? "Cần là số." : null
          }
        />
      ) : (
        <Input
          aria-label={`Giá trị của ${label}`}
          inputMode={draft.value_type === "number" ? "decimal" : undefined}
          maxLength={2000}
          placeholder={draft.value_type === "number" ? "VD: 35" : "VD: Hà Nội"}
          aria-invalid={(!!error && !!column) || undefined}
          value={draft.text}
          onChange={(event) => onChange({ ...draft, text: event.target.value })}
        />
      )}
      {error ? <FieldError>{error}</FieldError> : null}
    </Field>
  )
}

function PairList({
  legend,
  description,
  firstLabel,
  firstPlaceholder,
  secondLabel,
  secondPlaceholder,
  addLabel,
  items,
  onChange,
  error,
}: {
  legend: string
  description: string
  firstLabel: string
  firstPlaceholder: string
  secondLabel: string
  secondPlaceholder: string
  addLabel: string
  items: PairDraft[]
  onChange: (items: PairDraft[]) => void
  error: string | null
}) {
  const update = (key: number, change: Partial<PairDraft>) =>
    onChange(items.map((item) => (item.key === key ? { ...item, ...change } : item)))

  return (
    <FieldSet className="min-w-0">
      <FieldLegend>{legend}</FieldLegend>
      <FieldDescription>{description}</FieldDescription>
      <div className="flex flex-col gap-2">
        {items.map((item, index) => (
          <div key={item.key} className="flex items-start gap-2 rounded-lg border bg-muted/30 p-3">
            <div className="grid min-w-0 flex-1 gap-2">
              <Textarea
                aria-label={`${firstLabel} ${index + 1}`}
                rows={1}
                maxLength={2000}
                className="min-h-8"
                placeholder={`${firstLabel}: ${firstPlaceholder.replace("VD: ", "")}`}
                aria-invalid={(!!error && pairIssue(item) && !item.first.trim()) || undefined}
                value={item.first}
                onChange={(event) => update(item.key, { first: event.target.value })}
              />
              <Textarea
                aria-label={`${secondLabel} ${index + 1}`}
                rows={1}
                maxLength={2000}
                className="min-h-8"
                placeholder={`${secondLabel}: ${secondPlaceholder.replace("VD: ", "")}`}
                aria-invalid={(!!error && pairIssue(item) && !item.second.trim()) || undefined}
                value={item.second}
                onChange={(event) => update(item.key, { second: event.target.value })}
              />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={`Bỏ ${legend.toLowerCase()} ${index + 1}`}
              onClick={() => onChange(items.filter((other) => other.key !== item.key))}
            >
              <Trash2Icon />
            </Button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          disabled={items.length >= 50}
          onClick={() => onChange([...items, { key: key(), first: "", second: "" }])}
        >
          <PlusIcon data-icon="inline-start" />
          {addLabel}
        </Button>
      </div>
      {error ? <FieldError>{error}</FieldError> : null}
    </FieldSet>
  )
}
