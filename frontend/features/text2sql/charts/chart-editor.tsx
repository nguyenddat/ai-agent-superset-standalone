"use client"

import { useId, type ReactNode } from "react"
import { PlusIcon, RotateCcwIcon, Trash2Icon, TriangleAlertIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"

import { ROLE_LABELS, typeLabel, type ChartTypeInfo, type JsonSchema, type RoleInfo } from "./catalog"
import { categoryKey, type Row } from "./data"
import { fieldTitle } from "./format"
import { tokenColor } from "./palette"
import { PALETTE, type ChartField, type ChartSpec, type Measure, type PaletteToken } from "./spec"

const NONE = "__none__"
const AUTO = "__auto__"

const AGGREGATES: [string, string][] = [
  ["auto", "Tự động"],
  ["none", "Giữ nguyên"],
  ["sum", "Tổng"],
  ["avg", "Trung bình"],
  ["min", "Nhỏ nhất"],
  ["max", "Lớn nhất"],
  ["count", "Đếm"],
  ["count_distinct", "Đếm không trùng"],
]

const TOKEN_LABELS: Record<PaletteToken, string> = {
  "series-1": "Xanh dương",
  "series-2": "Cam",
  "series-3": "Xanh ngọc",
  "series-4": "Vàng",
  "series-5": "Hồng",
  "series-6": "Xanh lá",
  "series-7": "Tím",
  "series-8": "Đỏ",
  muted: "Xám",
}

const OPTION_LABELS: Record<string, string> = {
  curve: "Kiểu đường",
  points: "Điểm trên đường",
  connect_nulls: "Nối qua chỗ thiếu dữ liệu",
  baseline: "Mốc so sánh",
  total: "Thêm cột tổng",
  total_label: "Nhãn cột tổng",
  show_conversion: "Hiện tỷ lệ chuyển đổi",
  show_percent: "Hiện phần trăm",
  sparkline: "Đường nhỏ",
  delta_good: "Chiều tốt",
  target_value: "Giá trị mục tiêu",
  ranges: "Các mốc nền (cách nhau bởi dấu chấm phẩy)",
  bins: "Số khoảng",
  bin_width: "Độ rộng mỗi khoảng",
  whisker: "Râu",
  outliers: "Hiện điểm ngoại lai",
  midpoint: "Điểm giữa thang màu",
  trend: "Đường xu hướng",
  fill: "Tô nền",
  show_last: "Hiện giá trị mới nhất",
  columns: "Cột hiển thị",
  heat: "Tô màu theo cột",
}

const ENUM_LABELS: Record<string, string> = {
  linear: "Thẳng",
  monotone: "Mềm",
  step: "Bậc thang",
  auto: "Tự động",
  show: "Hiện",
  hide: "Ẩn",
  up: "Tăng là tốt",
  down: "Giảm là tốt",
  tukey: "Tukey (1,5 khoảng tứ phân vị)",
  minmax: "Từ nhỏ nhất đến lớn nhất",
  none: "Không",
  line: "Đường",
  bar: "Cột",
}

const ORIENTABLE = new Set([
  "bar_grouped", "bar_stacked", "bar_stacked_100", "lollipop", "dumbbell", "diverging_bar", "waterfall",
])
const CARTESIAN = new Set([
  "bar", "bar_horizontal", "bar_grouped", "bar_stacked", "bar_stacked_100", "lollipop", "dumbbell",
  "diverging_bar", "waterfall", "line", "area", "area_stacked", "area_stacked_100", "combo", "scatter", "bubble",
  "histogram", "box_plot",
])
const FACETABLE = new Set(["bar", "bar_grouped", "line", "area", "area_stacked", "bar_stacked", "lollipop", "combo"])

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  )
}

function Item({ label, children, htmlFor }: { label: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] items-center gap-2">
      <Label htmlFor={htmlFor} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function Choice({
  value,
  options,
  onChange,
  label,
  id,
}: {
  value: string
  options: [string, ReactNode][]
  onChange: (value: string) => void
  label: string
  id?: string
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} size="sm" className="w-full" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map(([key, text]) => (
          <SelectItem key={key} value={key}>
            {text}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  const id = useId()
  return (
    <div className="flex items-center justify-between gap-3">
      <Label htmlFor={id} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      <Switch id={id} size="sm" checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

type BoxProps<T> = {
  value: T | null | undefined
  onChange: (value: T | null) => void
  label: string
  placeholder?: string
}

function NumberBox({ value, onChange, label, placeholder }: BoxProps<number>) {
  return (
    <Input
      type="number"
      inputMode="decimal"
      className="h-8"
      aria-label={label}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(event) => {
        const text = event.target.value.trim()
        const parsed = Number(text)
        onChange(text === "" || Number.isNaN(parsed) ? null : parsed)
      }}
    />
  )
}

function TextBox({ value, onChange, label, maxLength, placeholder }: BoxProps<string> & { maxLength?: number }) {
  return (
    <Input
      className="h-8"
      aria-label={label}
      maxLength={maxLength}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value ? event.target.value : null)}
    />
  )
}

const tokenOptions = (withAuto: boolean): [string, ReactNode][] => [
  ...(withAuto ? ([[AUTO, "Tự động"]] as [string, ReactNode][]) : []),
  ...PALETTE.map((token): [string, ReactNode] => [
    token,
    <span key={token} className="flex items-center gap-2">
      <span aria-hidden className="size-3 rounded-[3px]" style={{ background: tokenColor(token) }} />
      {TOKEN_LABELS[token]}
    </span>,
  ]),
]

// Columns a role accepts: numbers count as categories too unless they are measures, like the backend's field kinds.
function fieldsFor(role: RoleInfo, fields: ChartField[]) {
  return fields.filter(
    (field) =>
      role.accepts.includes(field.type) ||
      (field.type === "number" && field.role !== "measure" && role.accepts.includes("text")),
  )
}

type Edit = (change: (draft: ChartSpec) => void) => void

function clean<T extends object>(value: T): T {
  const kept = Object.entries(value).filter(([, item]) => item !== null && item !== undefined && item !== "")
  return Object.fromEntries(kept) as T
}

type EditorPart = { spec: ChartSpec; fields: ChartField[]; edit: Edit }

function RoleEditor({ role, spec, fields, edit }: EditorPart & { role: RoleInfo }) {
  const options = fieldsFor(role, fields)
  const fieldOptions: [string, ReactNode][] = options.map((field) => [field.name, fieldTitle(field)])
  const label = ROLE_LABELS[role.role] ?? role.role
  const encoding = spec.encoding ?? {}
  if (role.role === "y" || role.role === "path") {
    const list = (role.role === "y" ? encoding.y : encoding.path) ?? []
    const measures = role.role === "y"
    return (
      <div className="flex flex-col gap-2">
        {list.map((item, index) => (
          <div key={index} className="flex flex-col gap-2 rounded-md border p-2">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <Choice
                  label={`${label} ${index + 1}`}
                  value={item.field}
                  options={fieldOptions}
                  onChange={(value) =>
                    edit((draft) => {
                      const target = measures ? draft.encoding!.y! : draft.encoding!.path!
                      target[index] = { ...target[index], field: value, label: undefined }
                    })
                  }
                />
              </div>
              {list.length > role.min && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Bỏ ${label.toLowerCase()} ${index + 1}`}
                  onClick={() =>
                    edit((draft) => {
                      const target = measures ? draft.encoding!.y! : draft.encoding!.path!
                      target.splice(index, 1)
                    })
                  }
                >
                  <Trash2Icon />
                </Button>
              )}
            </div>
            {measures && (
              <div className="grid grid-cols-2 gap-2">
                <Choice
                  label={`Cách gộp số đo ${index + 1}`}
                  value={(item as Measure).aggregate ?? "auto"}
                  options={AGGREGATES}
                  onChange={(value) =>
                    edit((draft) => void (draft.encoding!.y![index].aggregate = value as Measure["aggregate"]))
                  }
                />
                <Choice
                  label={`Màu số đo ${index + 1}`}
                  value={(item as Measure).color ?? AUTO}
                  options={tokenOptions(true)}
                  onChange={(value) =>
                    edit((draft) => {
                      draft.encoding!.y![index].color = value === AUTO ? undefined : (value as PaletteToken)
                    })
                  }
                />
                {spec.type === "combo" && (
                  <Choice
                    label={`Dạng số đo ${index + 1}`}
                    value={(item as Measure).mark ?? (index === 0 ? "bar" : "line")}
                    options={[
                      ["bar", "Cột"],
                      ["line", "Đường"],
                      ["area", "Vùng"],
                    ]}
                    onChange={(value) =>
                      edit((draft) => void (draft.encoding!.y![index].mark = value as Measure["mark"]))
                    }
                  />
                )}
              </div>
            )}
          </div>
        ))}
        {list.length < role.max && options.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() =>
              edit((draft) => {
                draft.encoding ??= {}
                const used = new Set(list.map((item) => item.field))
                const next = options.find((field) => !used.has(field.name)) ?? options[0]
                if (measures) draft.encoding.y = [...(draft.encoding.y ?? []), { field: next.name }]
                else draft.encoding.path = [...(draft.encoding.path ?? []), { field: next.name }]
              })
            }
          >
            <PlusIcon data-icon="inline-start" />
            Thêm {label.toLowerCase()}
          </Button>
        )}
      </div>
    )
  }
  type Single = "x" | "series" | "row" | "size" | "color" | "goal" | "compare" | "source" | "target" | "label"
  const key = role.role as Single
  const current = encoding[key] as { field: string } | null | undefined
  return (
    <Choice
      label={label}
      value={current?.field ?? NONE}
      options={[...(role.required ? [] : ([[NONE, "Không dùng"]] as [string, ReactNode][])), ...fieldOptions]}
      onChange={(value) =>
        edit((draft) => {
          draft.encoding ??= {}
          if (value === NONE) delete draft.encoding[key]
          else draft.encoding[key] = { field: value } as never
        })
      }
    />
  )
}

function schemaKind(schema: JsonSchema): { type?: string; enum?: unknown[]; nullable: boolean; items?: JsonSchema } {
  const variants = schema.anyOf ?? [schema]
  const main = variants.find((item) => item.type !== "null") ?? schema
  const nullable = variants.some((item) => item.type === "null")
  return { type: main.type, enum: main.enum ?? schema.enum, nullable, items: main.items }
}

function OptionEditor({ name, schema, spec, fields, edit }: EditorPart & { name: string; schema: JsonSchema }) {
  const kind = schemaKind(schema)
  const label = OPTION_LABELS[name] ?? name
  const value = spec.options?.[name] ?? schema.default
  const set = (next: unknown) =>
    edit((draft) => {
      draft.options = { ...(draft.options ?? {}) }
      if (next === null || next === undefined || (Array.isArray(next) && !next.length)) delete draft.options[name]
      else draft.options[name] = next
    })
  if (name === "columns") {
    const chosen = Array.isArray(value) ? (value as string[]) : []
    return (
      <Item label={label}>
        <div className="flex flex-col gap-1.5">
          {fields.map((field) => {
            const checked = !chosen.length || chosen.includes(field.name)
            return (
              <label key={field.name} className="flex items-center gap-2 text-xs">
                <Checkbox
                  checked={checked}
                  onCheckedChange={(on) => {
                    const base = chosen.length ? chosen : fields.map((item) => item.name)
                    const added = [...new Set([...base, field.name])]
                    set(on ? added : base.filter((item) => item !== field.name))
                  }}
                />
                {fieldTitle(field)}
              </label>
            )
          })}
        </div>
      </Item>
    )
  }
  if (name === "heat") {
    const numbers = fields.filter((field) => field.type === "number")
    return (
      <Item label={label}>
        <Choice
          label={label}
          value={typeof value === "string" ? value : NONE}
          options={[[NONE, "Không"], ...numbers.map((field): [string, ReactNode] => [field.name, fieldTitle(field)])]}
          onChange={(next) => set(next === NONE ? null : next)}
        />
      </Item>
    )
  }
  if (kind.enum) {
    return (
      <Item label={label}>
        <Choice
          label={label}
          value={String(value ?? kind.enum[0])}
          options={kind.enum.map((item): [string, ReactNode] => [
            String(item),
            ENUM_LABELS[String(item)] ?? String(item),
          ])}
          onChange={set}
        />
      </Item>
    )
  }
  if (kind.type === "boolean") return <Toggle label={label} checked={Boolean(value)} onChange={set} />
  if (kind.type === "number" || kind.type === "integer") {
    return (
      <Item label={label}>
        <NumberBox
          label={label}
          value={typeof value === "number" ? value : null}
          onChange={(next) => set(next === null ? null : kind.type === "integer" ? Math.round(next) : next)}
        />
      </Item>
    )
  }
  if (kind.type === "array") {
    const list = Array.isArray(value) ? (value as unknown[]) : []
    return (
      <Item label={label}>
        <Input
          className="h-8"
          aria-label={label}
          defaultValue={list.join("; ")}
          onBlur={(event) =>
            set(
              event.target.value
                .split(";")
                .map((item) => Number(item.trim().replace(",", ".")))
                .filter((item) => Number.isFinite(item)),
            )
          }
        />
      </Item>
    )
  }
  if (kind.type === "string") {
    return (
      <Item label={label}>
        <TextBox label={label} value={typeof value === "string" ? value : ""} onChange={set} maxLength={30} />
      </Item>
    )
  }
  return null
}

export type ChartEditorProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  spec: ChartSpec
  info: ChartTypeInfo | undefined
  fields: ChartField[]
  rows: Row[]
  errors: string[]
  warnings: string[]
  saving: boolean
  onChange: (spec: ChartSpec) => void
  onReset?: () => void
}

// Every knob of the spec in one panel; each change is checked by the backend before the chart redraws.
export function ChartEditor(props: ChartEditorProps) {
  const { open, onOpenChange, spec, info, fields, rows, errors, warnings, saving, onChange, onReset } = props
  const edit: Edit = (change) => {
    const draft = structuredClone(spec)
    change(draft)
    onChange(draft)
  }
  const ids = { title: useId(), subtitle: useId() }
  const type = spec.type
  const cartesian = CARTESIAN.has(type)
  const transform = spec.transform ?? {}
  const axes = spec.axes ?? {}
  const seriesField = spec.encoding?.series?.field
  const seriesIndex = fields.findIndex((field) => field.name === seriesField)
  const valuesAt = (index: number, size: number) =>
    index >= 0 ? [...new Set(rows.map((row) => categoryKey(row[index])))].slice(0, size) : []
  const seriesValues = valuesAt(seriesIndex, 8)
  const xIndex = fields.findIndex((field) => field.name === spec.encoding?.x?.field)
  const xValues = valuesAt(xIndex, 40)
  const yFields = (spec.encoding?.y ?? []).map((item) => item.field)
  const options = Object.entries(info?.options_schema?.properties ?? {})
  const setAxis = (axis: "x" | "y", change: Record<string, unknown>) =>
    edit((draft) => {
      draft.axes = { ...(draft.axes ?? {}) }
      draft.axes[axis] = clean({ ...(draft.axes[axis] ?? {}), ...change })
    })
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>Tùy chỉnh biểu đồ</SheetTitle>
          <SheetDescription>
            Dạng {typeLabel(type)}. Mỗi thay đổi được kiểm tra rồi mới vẽ lại.
          </SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-4 py-4">
          {(errors.length > 0 || warnings.length > 0) && (
            <div className="flex flex-col gap-1.5" role={errors.length ? "alert" : "status"}>
              {errors.map((error) => (
                <p key={error} className="flex items-start gap-1.5 text-xs text-destructive">
                  <TriangleAlertIcon className="mt-px size-3.5 shrink-0" />
                  {error}
                </p>
              ))}
              {warnings.map((warning) => (
                <p key={warning} className="text-xs text-muted-foreground">
                  {warning}
                </p>
              ))}
            </div>
          )}
          <Section title="Tiêu đề">
            <Item label="Tiêu đề" htmlFor={ids.title}>
              <Input
                id={ids.title}
                className="h-8"
                maxLength={120}
                value={spec.title ?? ""}
                onChange={(event) => edit((draft) => void (draft.title = event.target.value || null))}
              />
            </Item>
            <Item label="Phụ đề" htmlFor={ids.subtitle}>
              <Input
                id={ids.subtitle}
                className="h-8"
                maxLength={200}
                value={spec.subtitle ?? ""}
                onChange={(event) => edit((draft) => void (draft.subtitle = event.target.value || null))}
              />
            </Item>
          </Section>
          {info && info.roles.length > 0 && (
            <>
              <Separator />
              <Section title="Dữ liệu">
                {info.roles.map((role) => (
                  <Item key={role.role} label={ROLE_LABELS[role.role] ?? role.role}>
                    <RoleEditor role={role} spec={spec} fields={fields} edit={edit} />
                  </Item>
                ))}
              </Section>
            </>
          )}
          {type !== "table" && type !== "kpi" && (
            <>
              <Separator />
              <Section title="Sắp xếp và lọc">
                <Item label="Sắp xếp theo">
                  <Choice
                    label="Sắp xếp theo"
                    value={transform.sort?.by ?? "none"}
                    options={[
                      ["none", "Thứ tự dữ liệu"],
                      ["x", "Trục x"],
                      ...yFields.map((name): [string, ReactNode] => [
                        name,
                        fieldTitle(
                          fields.find((field) => field.name === name) ?? { name, label: name, type: "number" },
                        ),
                      ]),
                    ]}
                    onChange={(value) =>
                      edit((draft) => {
                        const order = draft.transform?.sort?.order ?? "desc"
                        const sort = value === "none" ? null : { by: value, order }
                        draft.transform = { ...(draft.transform ?? {}), sort }
                      })
                    }
                  />
                </Item>
                {transform.sort && (
                  <Item label="Chiều">
                    <Choice
                      label="Chiều sắp xếp"
                      value={transform.sort.order ?? "desc"}
                      options={[
                        ["desc", "Giảm dần"],
                        ["asc", "Tăng dần"],
                      ]}
                      onChange={(value) =>
                        edit((draft) => {
                          draft.transform!.sort = { ...draft.transform!.sort!, order: value as "asc" | "desc" }
                        })
                      }
                    />
                  </Item>
                )}
                <Toggle
                  label="Chỉ giữ N nhóm lớn nhất"
                  checked={!!transform.top_n}
                  onChange={(on) =>
                    edit((draft) => {
                      draft.transform = { ...(draft.transform ?? {}), top_n: on ? { n: 10, other: true } : null }
                    })
                  }
                />
                {transform.top_n && (
                  <>
                    <Item label="Số nhóm">
                      <NumberBox
                        label="Số nhóm"
                        value={transform.top_n.n}
                        onChange={(value) =>
                          edit((draft) => {
                            const n = Math.min(50, Math.max(1, Math.round(value ?? 1)))
                            draft.transform!.top_n = { ...draft.transform!.top_n!, n }
                          })
                        }
                      />
                    </Item>
                    <Toggle
                      label="Gộp phần còn lại vào «Khác»"
                      checked={transform.top_n.other ?? true}
                      onChange={(on) =>
                        edit((draft) => void (draft.transform!.top_n = { ...draft.transform!.top_n!, other: on }))
                      }
                    />
                  </>
                )}
                {cartesian && (
                  <>
                    <Toggle
                      label="Cộng dồn"
                      checked={!!transform.cumulative}
                      onChange={(on) =>
                        edit((draft) => void (draft.transform = { ...(draft.transform ?? {}), cumulative: on }))
                      }
                    />
                    <Toggle
                      label="Quy về 100 ở điểm đầu"
                      checked={transform.index_to === "first"}
                      onChange={(on) =>
                        edit((draft) => {
                          draft.transform = { ...(draft.transform ?? {}), index_to: on ? "first" : "none" }
                        })
                      }
                    />
                  </>
                )}
              </Section>
            </>
          )}
          {cartesian && (
            <>
              <Separator />
              <Section title="Trục">
                {ORIENTABLE.has(type) && (
                  <Item label="Hướng">
                    <Choice
                      label="Hướng"
                      value={spec.orientation ?? "vertical"}
                      options={[
                        ["vertical", "Dọc"],
                        ["horizontal", "Ngang"],
                      ]}
                      onChange={(value) =>
                        edit((draft) => void (draft.orientation = value as "vertical" | "horizontal"))
                      }
                    />
                  </Item>
                )}
                <Item label="Tên trục phân loại">
                  <TextBox
                    label="Tên trục phân loại"
                    value={axes.x?.title}
                    maxLength={60}
                    onChange={(value) => setAxis("x", { title: value })}
                  />
                </Item>
                <Item label="Tên trục giá trị">
                  <TextBox
                    label="Tên trục giá trị"
                    value={axes.y?.title}
                    maxLength={60}
                    onChange={(value) => setAxis("y", { title: value })}
                  />
                </Item>
                <Item label="Nghiêng nhãn">
                  <Choice
                    label="Nghiêng nhãn trục"
                    value={String(axes.x?.tick_angle ?? 0)}
                    options={[
                      ["0", "Không"],
                      ["-45", "45°"],
                      ["-90", "90°"],
                    ]}
                    onChange={(value) => setAxis("x", { tick_angle: Number(value) })}
                  />
                </Item>
                <Item label="Nhỏ nhất">
                  <NumberBox
                    label="Giá trị nhỏ nhất của trục"
                    value={axes.y?.min}
                    placeholder="Tự động"
                    onChange={(value) => setAxis("y", { min: value })}
                  />
                </Item>
                <Item label="Lớn nhất">
                  <NumberBox
                    label="Giá trị lớn nhất của trục"
                    value={axes.y?.max}
                    placeholder="Tự động"
                    onChange={(value) => setAxis("y", { max: value })}
                  />
                </Item>
                <Toggle
                  label="Bắt đầu từ 0"
                  checked={axes.y?.zero ?? true}
                  onChange={(on) => setAxis("y", { zero: on })}
                />
                <Toggle
                  label="Thang log"
                  checked={axes.y?.scale === "log"}
                  onChange={(on) => setAxis("y", { scale: on ? "log" : "linear" })}
                />
                <Toggle
                  label="Ẩn trục giá trị"
                  checked={!!axes.y?.hide}
                  onChange={(on) => setAxis("y", { hide: on })}
                />
              </Section>
            </>
          )}
          {type !== "table" && (
            <>
              <Separator />
              <Section title="Định dạng số">
                <Item label="Kiểu">
                  <Choice
                    label="Kiểu số"
                    value={spec.format?.number?.style ?? AUTO}
                    options={[
                      [AUTO, "Theo dữ liệu"],
                      ["number", "Số"],
                      ["percent", "Phần trăm"],
                      ["compact", "Rút gọn (N, Tr, Tỷ)"],
                    ]}
                    onChange={(value) =>
                      edit((draft) => {
                        draft.format = { ...(draft.format ?? {}) }
                        const style = value as "number"
                        draft.format.number = value === AUTO ? null : clean({ ...(draft.format.number ?? {}), style })
                      })
                    }
                  />
                </Item>
                {spec.format?.number && (
                  <>
                    <Item label="Số chữ số lẻ">
                      <NumberBox
                        label="Số chữ số lẻ"
                        value={spec.format.number.decimals}
                        placeholder="Tự động"
                        onChange={(value) =>
                          edit((draft) => {
                            const decimals = value === null ? null : Math.min(4, Math.max(0, Math.round(value)))
                            draft.format!.number = clean({ ...draft.format!.number!, decimals })
                          })
                        }
                      />
                    </Item>
                    <Item label="Đơn vị">
                      <TextBox
                        label="Đơn vị"
                        value={spec.format.number.unit}
                        maxLength={12}
                        onChange={(value) =>
                          edit((draft) => {
                            draft.format!.number = clean({ ...draft.format!.number!, unit: value })
                          })
                        }
                      />
                    </Item>
                    {spec.format.number.style === "percent" && (
                      <Item label="Dữ liệu là">
                        <Choice
                          label="Dữ liệu phần trăm là"
                          value={spec.format.number.percent_input ?? "ratio"}
                          options={[
                            ["ratio", "Tỷ lệ (0,25 = 25%)"],
                            ["percent", "Phần trăm (25 = 25%)"],
                          ]}
                          onChange={(value) =>
                            edit((draft) => {
                              draft.format!.number = { ...draft.format!.number!, percent_input: value as "ratio" }
                            })
                          }
                        />
                      </Item>
                    )}
                  </>
                )}
              </Section>
            </>
          )}
          {cartesian && (
            <>
              <Separator />
              <Section title="Đường tham chiếu">
                {(spec.reference_lines ?? []).map((line, index) => (
                  <div key={index} className="grid grid-cols-[5.5rem_1fr_1fr_auto] items-center gap-2">
                    <Choice
                      label={`Trục của đường ${index + 1}`}
                      value={line.axis}
                      options={[
                        ["y", "Giá trị"],
                        ["x", "Phân loại"],
                      ]}
                      onChange={(value) =>
                        edit((draft) => void (draft.reference_lines![index].axis = value as "x" | "y"))
                      }
                    />
                    <Input
                      className="h-8"
                      aria-label={`Giá trị đường ${index + 1}`}
                      value={String(line.value)}
                      onChange={(event) =>
                        edit((draft) => {
                          const text = event.target.value
                          const parsed = Number(text.replace(",", "."))
                          const numeric = line.axis === "y" && text.trim() !== "" && !Number.isNaN(parsed)
                          draft.reference_lines![index].value = numeric ? parsed : text
                        })
                      }
                    />
                    <TextBox
                      label={`Nhãn đường ${index + 1}`}
                      value={line.label}
                      maxLength={60}
                      placeholder="Nhãn"
                      onChange={(value) => edit((draft) => void (draft.reference_lines![index].label = value))}
                    />
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Bỏ đường ${index + 1}`}
                      onClick={() => edit((draft) => void draft.reference_lines!.splice(index, 1))}
                    >
                      <Trash2Icon />
                    </Button>
                  </div>
                ))}
                {(spec.reference_lines ?? []).length < 5 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="self-start"
                    onClick={() =>
                      edit((draft) => {
                        draft.reference_lines = [...(draft.reference_lines ?? []), { axis: "y", value: 0 }]
                      })
                    }
                  >
                    <PlusIcon data-icon="inline-start" />
                    Thêm đường
                  </Button>
                )}
              </Section>
            </>
          )}
          {type !== "table" && (
            <>
              <Separator />
              <Section title="Chú giải, nhãn và màu">
                <Item label="Chú giải">
                  <Choice
                    label="Chú giải"
                    value={spec.legend?.show ?? "auto"}
                    options={[
                      ["auto", "Tự động"],
                      ["show", "Hiện"],
                      ["hide", "Ẩn"],
                    ]}
                    onChange={(value) =>
                      edit((draft) => void (draft.legend = { ...(draft.legend ?? {}), show: value as "auto" }))
                    }
                  />
                </Item>
                <Item label="Vị trí chú giải">
                  <Choice
                    label="Vị trí chú giải"
                    value={spec.legend?.position ?? "bottom"}
                    options={[
                      ["bottom", "Dưới"],
                      ["top", "Trên"],
                      ["right", "Phải"],
                    ]}
                    onChange={(value) =>
                      edit((draft) => void (draft.legend = { ...(draft.legend ?? {}), position: value as "bottom" }))
                    }
                  />
                </Item>
                {cartesian && (
                  <Item label="Nhãn số">
                    <Choice
                      label="Nhãn số trên biểu đồ"
                      value={spec.labels?.show ?? "auto"}
                      options={[
                        ["auto", "Tự động"],
                        ["none", "Không"],
                        ["endpoints", "Đầu và cuối"],
                        ["extremes", "Lớn nhất và nhỏ nhất"],
                        ["all", "Mọi điểm"],
                      ]}
                      onChange={(value) => edit((draft) => void (draft.labels = { show: value as "auto" }))}
                    />
                  </Item>
                )}
                <Item label="Cách tô màu">
                  <Choice
                    label="Cách tô màu"
                    value={spec.colors?.scheme ?? "categorical"}
                    options={[
                      ["categorical", "Mỗi nhóm một màu"],
                      ["emphasis", "Làm nổi bật vài giá trị"],
                      ["sequential", "Đậm nhạt theo giá trị"],
                      ["diverging", "Hai màu quanh mốc giữa"],
                    ]}
                    onChange={(value) =>
                      edit((draft) => void (draft.colors = { ...(draft.colors ?? {}), scheme: value as "categorical" }))
                    }
                  />
                </Item>
                {spec.colors?.scheme === "emphasis" && xValues.length > 0 && (
                  <Item label="Làm nổi bật (tối đa 3)">
                    <div className="flex max-h-40 flex-col gap-1.5 overflow-y-auto">
                      {xValues.map((value) => {
                        const highlight = spec.colors?.highlight ?? []
                        const checked = highlight.includes(value)
                        return (
                          <label key={value} className="flex items-center gap-2 text-xs">
                            <Checkbox
                              checked={checked}
                              disabled={!checked && highlight.length >= 3}
                              onCheckedChange={(on) =>
                                edit((draft) => {
                                  const current = draft.colors?.highlight ?? []
                                  const highlight = on ? [...current, value] : current.filter((item) => item !== value)
                                  draft.colors = { ...(draft.colors ?? {}), highlight }
                                })
                              }
                            />
                            {value}
                          </label>
                        )
                      })}
                    </div>
                  </Item>
                )}
                {seriesValues.map((value) => (
                  <Item key={value} label={`Màu «${value}»`}>
                    <Choice
                      label={`Màu của ${value}`}
                      value={spec.colors?.assign?.[value] ?? AUTO}
                      options={tokenOptions(true)}
                      onChange={(token) =>
                        edit((draft) => {
                          const assign = { ...(draft.colors?.assign ?? {}) }
                          if (token === AUTO) delete assign[value]
                          else assign[value] = token as PaletteToken
                          draft.colors = { ...(draft.colors ?? {}), assign }
                        })
                      }
                    />
                  </Item>
                ))}
              </Section>
            </>
          )}
          {FACETABLE.has(type) && (
            <>
              <Separator />
              <Section title="Chia nhỏ">
                <Item label="Chia thành nhiều biểu đồ">
                  <Choice
                    label="Chia thành nhiều biểu đồ"
                    value={spec.facet?.by ?? NONE}
                    options={[
                      [NONE, "Không"],
                      ["measure", "Theo số đo"],
                      ...(spec.encoding?.series ? ([["series", "Theo nhóm màu"]] as [string, ReactNode][]) : []),
                    ]}
                    onChange={(value) =>
                      edit((draft) => {
                        const columns = draft.facet?.columns ?? 2
                        draft.facet = value === NONE ? null : { by: value as "measure", columns }
                      })
                    }
                  />
                </Item>
                {spec.facet && (
                  <Item label="Số cột">
                    <Choice
                      label="Số cột"
                      value={String(spec.facet.columns ?? 2)}
                      options={["1", "2", "3", "4"].map((item): [string, ReactNode] => [item, item])}
                      onChange={(value) =>
                        edit((draft) => void (draft.facet = { ...draft.facet!, columns: Number(value) }))
                      }
                    />
                  </Item>
                )}
              </Section>
            </>
          )}
          {options.length > 0 && (
            <>
              <Separator />
              <Section title={`Tùy chọn riêng của dạng ${typeLabel(type)}`}>
                {options.map(([name, schema]) => (
                  <OptionEditor key={name} name={name} schema={schema} spec={spec} fields={fields} edit={edit} />
                ))}
              </Section>
            </>
          )}
        </div>
        <SheetFooter className="flex-row items-center justify-between border-t">
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground" aria-live="polite">
            {saving ? (
              <>
                <Spinner className="size-3.5" />
                Đang kiểm tra…
              </>
            ) : errors.length ? (
              "Chưa áp dụng được thay đổi"
            ) : (
              "Đã áp dụng"
            )}
          </span>
          <div className="flex gap-2">
            {onReset && (
              <Button variant="outline" size="sm" onClick={onReset}>
                <RotateCcwIcon data-icon="inline-start" />
                Đặt lại theo đề xuất
              </Button>
            )}
            <Button size="sm" onClick={() => onOpenChange(false)}>
              Xong
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
