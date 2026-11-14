"use client"

import { cn } from "@/lib/utils"
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

import { ChangedDot } from "./changed-dot"
import { same } from "./draft"
import { tableKinds } from "./labels"
import { type CatalogTable, TableStructure } from "./table-structure"
import type { ColumnDictionary, TableFields, TableKind } from "./types"

const NONE = "none"

export type TableChange = <Key extends keyof TableFields>(key: Key, value: TableFields[Key]) => void

type TableInfoFormProps = {
  fields: TableFields
  saved: TableFields
  columns: ColumnDictionary[]
  catalogTables: CatalogTable[]
  highlighted: boolean
  error: string | null
  onChange: TableChange
}

export function TableInfoForm({
  fields,
  saved,
  columns,
  catalogTables,
  highlighted,
  error,
  onChange,
}: TableInfoFormProps) {
  const fieldClass = cn("rounded-lg transition-colors duration-1000", highlighted && "bg-accent")
  const mark = (key: keyof TableFields) => !same(saved[key], fields[key]) && <ChangedDot />

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
        <FieldSet className="min-w-0">
          <FieldLegend>Mô tả nghiệp vụ</FieldLegend>
          <FieldGroup>
            <Field className={fieldClass} data-invalid={!fields.display_name.trim() || undefined}>
              <FieldLabel htmlFor="table-display-name">
                Tên hiển thị
                {mark("display_name")}
              </FieldLabel>
              <Input
                id="table-display-name"
                value={fields.display_name}
                maxLength={255}
                aria-invalid={!fields.display_name.trim() || undefined}
                onChange={(event) => onChange("display_name", event.target.value)}
              />
              {!fields.display_name.trim() && <FieldError>Tên hiển thị không được để trống.</FieldError>}
            </Field>

            <Field className={fieldClass}>
              <FieldLabel htmlFor="table-description">
                Mô tả
                {mark("description")}
              </FieldLabel>
              <Textarea
                id="table-description"
                className="min-h-20"
                maxLength={2000}
                placeholder="Bảng chứa dữ liệu gì, dùng để làm gì"
                value={fields.description ?? ""}
                onChange={(event) => onChange("description", event.target.value || null)}
              />
            </Field>

            <Field className={fieldClass}>
              <FieldLabel htmlFor="table-grain">
                Một dòng là gì
                {mark("grain_description")}
              </FieldLabel>
              <Textarea
                id="table-grain"
                maxLength={2000}
                placeholder="Ví dụ: Một lần quan sát thời tiết của một thành phố"
                value={fields.grain_description ?? ""}
                onChange={(event) => onChange("grain_description", event.target.value || null)}
              />
              <FieldDescription>Giúp AI agent hiểu mỗi dòng đại diện cho điều gì khi đếm hoặc tổng hợp.</FieldDescription>
            </Field>

            <Field className={fieldClass}>
              <FieldLabel>
                Loại bảng
                {mark("table_kind")}
              </FieldLabel>
              <ToggleGroup
                type="single"
                variant="outline"
                value={fields.table_kind ?? NONE}
                onValueChange={(value) => value && onChange("table_kind", value === NONE ? null : (value as TableKind))}
                className="flex-wrap"
              >
                <ToggleGroupItem value={NONE}>Chưa xác định</ToggleGroupItem>
                {tableKinds.map((kind) => (
                  <ToggleGroupItem key={kind.value} value={kind.value}>
                    {kind.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </Field>

            <Field orientation="horizontal" className={fieldClass}>
              <FieldContent>
                <FieldLabel htmlFor="table-pii">
                  Chứa dữ liệu cá nhân (PII)
                  {mark("contains_pii")}
                </FieldLabel>
                <FieldDescription>Họ tên, số điện thoại, email, địa chỉ... của một người.</FieldDescription>
              </FieldContent>
              <Switch
                id="table-pii"
                checked={fields.contains_pii}
                onCheckedChange={(checked) => onChange("contains_pii", checked)}
              />
            </Field>
          </FieldGroup>
        </FieldSet>

        <TableStructure
          fields={fields}
          saved={saved}
          columns={columns}
          catalogTables={catalogTables}
          className={fieldClass}
          onChange={onChange}
        />
      </div>

      {error && <FieldError>{error}</FieldError>}
    </div>
  )
}
