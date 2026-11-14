"use client"

import { useState } from "react"
import { CircleCheckIcon, CircleXIcon, FolderTreeIcon, TableIcon } from "lucide-react"

import { TagInput } from "@/components/tag-input"
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

import { explainScope, MAX_PATTERN_LENGTH, MAX_PATTERNS, type MetadataScope, type ScopeField } from "./metadata-scope"

type ScopeGroup = {
  title: string
  description: string
  icon: typeof TableIcon
  include: { field: ScopeField; placeholder: string }
  exclude: { field: ScopeField; placeholder: string }
}

const groups: ScopeGroup[] = [
  {
    title: "Schema",
    description: "So khớp với tên schema.",
    icon: FolderTreeIcon,
    include: { field: "schema_includes", placeholder: "public, analytics_*" },
    exclude: { field: "schema_excludes", placeholder: "staging, tmp_*" },
  },
  {
    title: "Bảng và view",
    description: "So khớp với tên bảng hoặc schema.bảng.",
    icon: TableIcon,
    include: { field: "table_includes", placeholder: "fact_*, public.orders" },
    exclude: { field: "table_excludes", placeholder: "tmp_*, staging.*" },
  },
]

const validatePattern = (value: string) =>
  value.length > MAX_PATTERN_LENGTH ? `Mỗi mẫu tối đa ${MAX_PATTERN_LENGTH} ký tự.` : null

function PatternField({
  label,
  group,
  hint,
  placeholder,
  patterns,
  onChange,
}: {
  label: string
  group: string
  hint: string
  placeholder: string
  patterns: string[]
  onChange: (patterns: string[]) => void
}) {
  return (
    <Field>
      <FieldLabel>{label}</FieldLabel>
      <TagInput
        label={`${label}: ${group}`}
        placeholder={placeholder}
        max={MAX_PATTERNS}
        limitMessage={`Tối đa ${MAX_PATTERNS} mẫu.`}
        value={patterns.map((pattern) => ({ id: pattern, value: pattern }))}
        onValueChange={(tags) => onChange(tags.filter((tag) => !tag.error).map((tag) => tag.value))}
        validate={validatePattern}
      />
      <FieldDescription>{hint}</FieldDescription>
    </Field>
  )
}

export function ConnectionScopeStep({
  scope,
  onChange,
}: {
  scope: MetadataScope
  onChange: (scope: MetadataScope) => void
}) {
  const [sample, setSample] = useState("")
  const verdict = explainScope(scope, sample)
  const set = (field: ScopeField) => (patterns: string[]) => onChange({ ...scope, [field]: patterns })

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Chọn phần metadata được đồng bộ. Mẫu dùng <code className="font-mono">*</code> và{" "}
        <code className="font-mono">?</code>, phân biệt chữ hoa/thường; nhấn Enter hoặc dấu phẩy để thêm. Để trống
        &quot;Chỉ lấy&quot; nghĩa là lấy tất cả; &quot;Bỏ qua&quot; luôn được ưu tiên. Có thể bỏ qua bước này và sửa sau.
      </p>

      {groups.map(({ title, description, icon: Icon, include, exclude }) => (
        <section key={title} className="flex flex-col gap-3 rounded-xl border p-4">
          <header className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <Icon className="size-4" />
            </span>
            <div className="flex flex-col">
              <h3 className="text-sm font-medium">{title}</h3>
              <p className="text-xs text-muted-foreground">{description}</p>
            </div>
          </header>
          <div className="grid gap-4 sm:grid-cols-2">
            <PatternField
              label="Chỉ lấy"
              group={title}
              hint="Trống: lấy tất cả."
              placeholder={include.placeholder}
              patterns={scope[include.field]}
              onChange={set(include.field)}
            />
            <PatternField
              label="Bỏ qua"
              group={title}
              hint="Ưu tiên hơn Chỉ lấy."
              placeholder={exclude.placeholder}
              patterns={scope[exclude.field]}
              onChange={set(exclude.field)}
            />
          </div>
        </section>
      ))}

      <Field>
        <FieldLabel htmlFor="scope-sample">Thử một tên</FieldLabel>
        <Input
          id="scope-sample"
          value={sample}
          autoComplete="off"
          spellCheck={false}
          placeholder="schema hoặc schema.bảng, VD: public.orders"
          onChange={(event) => setSample(event.target.value)}
        />
        {verdict ? (
          <p
            className={cn(
              "flex items-center gap-1.5 text-sm",
              verdict.selected ? "text-foreground" : "text-destructive",
            )}
          >
            {verdict.selected ? <CircleCheckIcon className="size-4" /> : <CircleXIcon className="size-4" />}
            <span className="font-medium">{verdict.selected ? "Được lấy." : "Bị bỏ qua."}</span>
            <span className="text-muted-foreground">{verdict.reason}</span>
          </p>
        ) : (
          <FieldDescription>Kiểm tra nhanh bộ lọc trước khi lưu; kết quả giống khi đồng bộ.</FieldDescription>
        )}
      </Field>
    </div>
  )
}
