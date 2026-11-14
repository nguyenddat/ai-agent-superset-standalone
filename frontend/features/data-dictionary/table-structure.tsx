"use client"

import { PlusIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { cn } from "@/lib/utils"

import { ChangedDot } from "./changed-dot"
import { missingRoles, roleColumn, same, withRole } from "./draft"
import {
  catalogSlots,
  indicatorAggregations,
  layoutRoles,
  requiredRoles,
  type RoleSlot,
  tableLayouts,
  timeGrains,
  valueSlots,
} from "./labels"
import type { TableChange } from "./table-info-form"
import type {
  ColumnDictionary,
  IndicatorAggregationValue,
  TableFields,
  TableLayout,
  TimeGrain,
  TimeGrainValue,
} from "./types"

const NONE = "none"
const MAX_GRAINS = 50
const MAX_INDICATOR_CODES = 20

export type CatalogTable = { table_id: string; table_name: string; display_name: string }

type TableStructureProps = {
  fields: TableFields
  saved: TableFields
  columns: ColumnDictionary[]
  catalogTables: CatalogTable[]
  className?: string
  onChange: TableChange
}

export function TableStructure({ fields, saved, columns, catalogTables, className, onChange }: TableStructureProps) {
  const roles = fields.column_roles
  const rowKind = roleColumn(roles, "row_kind")
  const missing = missingRoles(fields)
  const timeColumns = columns.filter((column) => column.temporal_kind)
  const layoutInfo = tableLayouts.find((layout) => layout.value === fields.layout)

  const roleChanged = (role: string, qualifier: string | null = null) =>
    roleColumn(saved.column_roles, role, qualifier) !== roleColumn(roles, role, qualifier)

  const setRole = (role: string, qualifier: string | null, columnId: string | null) => {
    onChange("column_roles", withRole(roles, role, qualifier, columnId))
    if (role === "row_kind" && Boolean(rowKind) !== Boolean(columnId)) {
      onChange(
        "time_grains",
        columnId
          ? fields.time_grains.map((grain) => ({ ...grain, row_kind_value: "" }))
          : fields.time_grains.slice(0, 1).map((grain) => ({ ...grain, row_kind_value: null })),
      )
    }
    if (role === "catalog_aggregation" && !columnId) onChange("indicator_aggregations", [])
  }

  const setLayout = (layout: TableLayout) => {
    onChange("layout", layout)
    onChange(
      "column_roles",
      roles.filter((item) => layoutRoles[layout].includes(item.role)),
    )
    if (layout !== "indicator_values") onChange("indicator_catalog_table_id", null)
    if (layout !== "indicator_catalog") onChange("indicator_aggregations", [])
  }

  const roleField = (slot: RoleSlot, options: ColumnDictionary[] = columns) => {
    const id = `role-${slot.role}-${slot.qualifier ?? "any"}`
    const value = roleColumn(roles, slot.role, slot.qualifier)
    const required = slot.role !== "value" && requiredRoles[fields.layout].includes(slot.role)
    const invalid = missing.includes(slot.role)
    return (
      <Field key={id}>
        <FieldLabel htmlFor={id}>
          {slot.label}
          {required && <span aria-hidden className="-ml-1 text-destructive">*</span>}
          {roleChanged(slot.role, slot.qualifier) && <ChangedDot />}
        </FieldLabel>
        <ColumnSelect
          id={id}
          columns={options}
          allColumns={columns}
          value={value}
          invalid={invalid}
          onChange={(columnId) => setRole(slot.role, slot.qualifier, columnId)}
        />
        {slot.description && <FieldDescription>{slot.description}</FieldDescription>}
      </Field>
    )
  }

  return (
    <div className={cn("flex min-w-0 flex-col gap-6", className)}>
      <FieldSet className="min-w-0">
        <FieldLegend>Thời gian</FieldLegend>
        <FieldGroup className="grid gap-x-4 gap-y-6 sm:grid-cols-2">
          {roleField(
            {
              role: "time",
              qualifier: null,
              label: "Cột thời gian chính",
              description: timeColumns.length
                ? "Mặc định dùng khi lọc hoặc nhóm theo thời gian."
                : "Bảng không có cột kiểu ngày hoặc ngày giờ.",
            },
            timeColumns,
          )}
          {roleField({ role: "created_at", qualifier: null, label: "Cột thời điểm tạo bản ghi" }, timeColumns)}
          {roleField({
            role: "row_kind",
            qualifier: null,
            label: "Cột phân loại dòng",
            description: "Chỉ khai báo khi bảng trộn nhiều loại dòng có độ chi tiết thời gian khác nhau.",
          })}
          {!rowKind && (
            <Field>
              <FieldLabel htmlFor="time-grain">
                Độ chi tiết thời gian
                {!same(saved.time_grains, fields.time_grains) && <ChangedDot />}
              </FieldLabel>
              <Select
                value={fields.time_grains[0]?.time_grain ?? NONE}
                onValueChange={(value) =>
                  onChange(
                    "time_grains",
                    value === NONE
                      ? []
                      : [{ row_kind_value: null, label: fields.time_grains[0]?.label ?? null, time_grain: value as TimeGrainValue }],
                  )
                }
              >
                <SelectTrigger id="time-grain" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE}>Chưa xác định</SelectItem>
                    {timeGrains.map((grain) => (
                      <SelectItem key={grain.value} value={grain.value}>
                        {grain.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>Mỗi dòng ứng với khoảng thời gian nào.</FieldDescription>
            </Field>
          )}
        </FieldGroup>
        {rowKind && (
          <GrainList
            grains={fields.time_grains}
            changed={!same(saved.time_grains, fields.time_grains)}
            onChange={(grains) => onChange("time_grains", grains)}
          />
        )}
      </FieldSet>

      <FieldSeparator />

      <FieldSet className="min-w-0">
        <FieldLegend>
          <span className="flex items-center gap-1.5">
            Cách tổ chức chỉ số
            {!same(saved.layout, fields.layout) && <ChangedDot />}
          </span>
        </FieldLegend>
        <Field>
          <ToggleGroup
            type="single"
            variant="outline"
            aria-label="Cách tổ chức chỉ số"
            value={fields.layout}
            onValueChange={(value) => value && setLayout(value as TableLayout)}
            className="flex-wrap"
          >
            {tableLayouts.map((layout) => (
              <ToggleGroupItem key={layout.value} value={layout.value}>
                {layout.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <FieldDescription>{layoutInfo?.description}</FieldDescription>
        </Field>

        {fields.layout === "indicator_values" && (
          <FieldGroup className="grid gap-x-4 gap-y-6 sm:grid-cols-2">
            {roleField({
              role: "indicator_key",
              qualifier: null,
              label: "Cột mã chỉ số",
              description: "Cho biết dòng là giá trị của chỉ số nào.",
            })}
            <Field>
              <FieldLabel htmlFor="indicator-catalog">
                Bảng danh mục chỉ số
                {!same(saved.indicator_catalog_table_id, fields.indicator_catalog_table_id) && <ChangedDot />}
              </FieldLabel>
              <Select
                value={fields.indicator_catalog_table_id ?? NONE}
                onValueChange={(value) => onChange("indicator_catalog_table_id", value === NONE ? null : value)}
              >
                <SelectTrigger id="indicator-catalog" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value={NONE}>Không có</SelectItem>
                    {catalogTables.map((table) => (
                      <SelectItem key={table.table_id} value={table.table_id}>
                        {table.display_name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>
                {catalogTables.length
                  ? "Bảng giải thích tên, đơn vị của từng mã chỉ số."
                  : "Chưa có bảng nào được lưu với cách tổ chức Danh mục chỉ số."}
              </FieldDescription>
            </Field>
            {valueSlots.map((slot) => roleField(slot))}
            {missing.includes("value") && (
              <FieldError className="sm:col-span-2">Cần ít nhất một cột giá trị.</FieldError>
            )}
          </FieldGroup>
        )}

        {fields.layout === "indicator_catalog" && (
          <>
            <FieldGroup className="grid gap-x-4 gap-y-6 sm:grid-cols-2">
              {catalogSlots.map((slot) => roleField(slot))}
            </FieldGroup>
            {roleColumn(roles, "catalog_aggregation") && (
              <AggregationList
                items={fields.indicator_aggregations}
                changed={!same(saved.indicator_aggregations, fields.indicator_aggregations)}
                onChange={(items) => onChange("indicator_aggregations", items)}
              />
            )}
          </>
        )}
      </FieldSet>
    </div>
  )
}

function ColumnSelect({
  id,
  columns,
  allColumns,
  value,
  invalid,
  onChange,
}: {
  id: string
  columns: ColumnDictionary[]
  allColumns: ColumnDictionary[]
  value: string | null
  invalid: boolean
  onChange: (columnId: string | null) => void
}) {
  const current = allColumns.find((column) => column.column_id === value)
  const options = current && !columns.includes(current) ? [current, ...columns] : columns

  return (
    <Select value={value ?? NONE} onValueChange={(next) => onChange(next === NONE ? null : next)}>
      <SelectTrigger id={id} className="w-full" aria-invalid={invalid || undefined}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectItem value={NONE}>Không có</SelectItem>
          {options.map((column) => (
            <SelectItem key={column.column_id} value={column.column_id}>
              <span className="font-mono">{column.name}</span>
              {column.display_name !== column.name && (
                <span className="truncate text-muted-foreground">{column.display_name}</span>
              )}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

function GrainList({
  grains,
  changed,
  onChange,
}: {
  grains: TimeGrain[]
  changed: boolean
  onChange: (grains: TimeGrain[]) => void
}) {
  const update = (index: number, patch: Partial<TimeGrain>) =>
    onChange(grains.map((grain, position) => (position === index ? { ...grain, ...patch } : grain)))
  const values = grains.map((grain) => grain.row_kind_value?.trim() ?? "")

  return (
    <Field>
      <FieldLabel>
        Độ chi tiết theo loại dòng
        {changed && <ChangedDot />}
      </FieldLabel>
      {grains.length > 0 && (
        <div className="flex flex-col gap-2">
          {grains.map((grain, index) => {
            const value = values[index]
            const invalid = !value || values.indexOf(value) !== index
            return (
              <div key={index} className="grid grid-cols-[1fr_8.5rem_auto] gap-2 sm:grid-cols-[1fr_8.5rem_1fr_auto]">
                <Input
                  aria-label={`Giá trị loại dòng ${index + 1}`}
                  placeholder="Giá trị loại dòng"
                  maxLength={255}
                  value={grain.row_kind_value ?? ""}
                  aria-invalid={invalid || undefined}
                  onChange={(event) => update(index, { row_kind_value: event.target.value })}
                />
                <Select
                  value={grain.time_grain}
                  onValueChange={(next) => update(index, { time_grain: next as TimeGrainValue })}
                >
                  <SelectTrigger aria-label={`Độ chi tiết của loại dòng ${index + 1}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {timeGrains.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <Input
                  aria-label={`Tên hiển thị của loại dòng ${index + 1}`}
                  placeholder="Tên hiển thị (không bắt buộc)"
                  maxLength={255}
                  className="col-span-2 row-start-2 sm:col-span-1 sm:row-start-auto"
                  value={grain.label ?? ""}
                  onChange={(event) => update(index, { label: event.target.value || null })}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Xóa loại dòng ${index + 1}`}
                  className="col-start-3 row-start-1 sm:col-start-auto"
                  onClick={() => onChange(grains.filter((_, position) => position !== index))}
                >
                  <XIcon />
                </Button>
              </div>
            )
          })}
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        className="w-fit"
        disabled={grains.length >= MAX_GRAINS}
        onClick={() => onChange([...grains, { row_kind_value: "", label: null, time_grain: "day" }])}
      >
        <PlusIcon data-icon="inline-start" />
        Thêm loại dòng
      </Button>
      <FieldDescription>Mỗi giá trị của cột phân loại dòng ứng với một độ chi tiết thời gian.</FieldDescription>
    </Field>
  )
}

function AggregationList({
  items,
  changed,
  onChange,
}: {
  items: TableFields["indicator_aggregations"]
  changed: boolean
  onChange: (items: TableFields["indicator_aggregations"]) => void
}) {
  const update = (index: number, patch: Partial<TableFields["indicator_aggregations"][number]>) =>
    onChange(items.map((item, position) => (position === index ? { ...item, ...patch } : item)))
  const codes = items.map((item) => item.source_code.trim())

  return (
    <Field>
      <FieldLabel>
        Ánh xạ cách tổng hợp
        {changed && <ChangedDot />}
      </FieldLabel>
      {items.length > 0 && (
        <div className="flex flex-col gap-2">
          {items.map((item, index) => {
            const invalid = !codes[index] || codes.indexOf(codes[index]) !== index
            return (
              <div key={index} className="grid grid-cols-[1fr_10rem_auto] gap-2">
                <Input
                  aria-label={`Mã cách tổng hợp ${index + 1}`}
                  placeholder="Mã trong dữ liệu, ví dụ: avg"
                  maxLength={64}
                  value={item.source_code}
                  aria-invalid={invalid || undefined}
                  onChange={(event) => update(index, { source_code: event.target.value })}
                />
                <Select
                  value={item.aggregation}
                  onValueChange={(next) => update(index, { aggregation: next as IndicatorAggregationValue })}
                >
                  <SelectTrigger aria-label={`Phép tổng hợp của mã ${index + 1}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {indicatorAggregations.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Xóa mã ${index + 1}`}
                  onClick={() => onChange(items.filter((_, position) => position !== index))}
                >
                  <XIcon />
                </Button>
              </div>
            )
          })}
        </div>
      )}
      <Button
        variant="outline"
        size="sm"
        className="w-fit"
        disabled={items.length >= MAX_INDICATOR_CODES}
        onClick={() => onChange([...items, { source_code: "", aggregation: "SUM" }])}
      >
        <PlusIcon data-icon="inline-start" />
        Thêm mã
      </Button>
      <FieldDescription>
        Mã ghi trong cột Cách tổng hợp của danh mục ứng với phép tính nào khi gộp giá trị chỉ số.
      </FieldDescription>
    </Field>
  )
}
