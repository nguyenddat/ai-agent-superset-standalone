import { requiredRoles } from "./labels"
import type { ColumnDictionary, ColumnFields, RoleAssignment, TableDictionary, TableFields } from "./types"

export type Draft = {
  table: Partial<TableFields>
  columns: Record<string, Partial<ColumnFields>>
}

export const emptyDraft: Draft = { table: {}, columns: {} }

export function tableFields(dictionary: TableDictionary): TableFields {
  return {
    display_name: dictionary.display_name,
    description: dictionary.description,
    grain_description: dictionary.grain_description,
    table_kind: dictionary.table_kind,
    contains_pii: dictionary.contains_pii,
    layout: dictionary.layout,
    indicator_catalog_table_id: dictionary.indicator_catalog?.table_id ?? null,
    column_roles: sortedRoles(dictionary.column_roles.map(({ role, qualifier, column_id }) => ({ role, qualifier, column_id }))),
    time_grains: dictionary.time_grains,
    indicator_aggregations: dictionary.indicator_aggregations,
  }
}

const roleOrder = (role: RoleAssignment) => `${role.role}:${role.qualifier ?? ""}`

function sortedRoles(roles: RoleAssignment[]) {
  return [...roles].sort((left, right) => roleOrder(left).localeCompare(roleOrder(right)))
}

export function roleColumn(roles: RoleAssignment[], role: string, qualifier: string | null = null) {
  return roles.find((item) => item.role === role && item.qualifier === qualifier)?.column_id ?? null
}

export function withRole(roles: RoleAssignment[], role: string, qualifier: string | null, columnId: string | null) {
  const others = roles.filter((item) => item.role !== role || item.qualifier !== qualifier)
  return sortedRoles(columnId ? [...others, { role, qualifier, column_id: columnId }] : others)
}

export function missingRoles(fields: TableFields) {
  return requiredRoles[fields.layout].filter((role) => !fields.column_roles.some((item) => item.role === role))
}

export function columnFields(column: ColumnDictionary): ColumnFields {
  return {
    display_name: column.display_name,
    description: column.description,
    business_term: column.business_term,
    semantic_role: column.semantic_role_is_default ? null : column.semantic_role,
    temporal_kind: column.temporal_kind,
    unit: column.unit,
    format: column.format,
    is_primary_key: column.is_primary_key,
    is_unique: column.is_unique,
    contains_pii: column.contains_pii,
    aggregations: column.aggregations,
    synonyms: column.synonyms,
    referenced_column: column.referenced_column,
  }
}

export const same = (left: unknown, right: unknown) => JSON.stringify(left ?? null) === JSON.stringify(right ?? null)

export function withChange<Fields extends object, Key extends keyof Fields>(
  changes: Partial<Fields>,
  saved: Fields,
  key: Key,
  value: Fields[Key],
): Partial<Fields> {
  const next = { ...changes }
  if (same(saved[key], value)) delete next[key]
  else next[key] = value
  return next
}

export function draftChangeCount(draft: Draft) {
  return (
    Object.keys(draft.table).length +
    Object.values(draft.columns).reduce((count, changes) => count + Object.keys(changes).length, 0)
  )
}

const optional = (value: string | null) => (value?.trim() ? value.trim() : null)

export function tablePayload(fields: TableFields) {
  return {
    ...fields,
    display_name: fields.display_name.trim(),
    description: optional(fields.description),
    grain_description: optional(fields.grain_description),
    time_grains: fields.time_grains.map((grain) => ({
      ...grain,
      row_kind_value: optional(grain.row_kind_value),
      label: optional(grain.label),
    })),
    indicator_aggregations: fields.indicator_aggregations.map((item) => ({
      ...item,
      source_code: item.source_code.trim(),
    })),
  }
}

export function columnPayload(column: ColumnDictionary, { referenced_column, ...fields }: ColumnFields) {
  return {
    column_id: column.column_id,
    ...fields,
    display_name: fields.display_name.trim(),
    description: optional(fields.description),
    business_term: optional(fields.business_term),
    unit: optional(fields.unit),
    format: optional(fields.format),
    referenced_column_id: referenced_column?.column_id ?? null,
  }
}

export function effectiveRole(column: ColumnDictionary, fields: ColumnFields) {
  return fields.semantic_role ?? (column.semantic_role_is_default ? column.semantic_role : null)
}

const hasBlankOrDuplicate = (values: string[]) =>
  values.some((value, index) => !value || values.indexOf(value) !== index)

export function tableProblem(fields: TableFields) {
  if (!fields.display_name.trim()) return "Tên hiển thị của bảng không được để trống."
  if (missingRoles(fields).length) return "Chưa gán đủ cột bắt buộc cho cách tổ chức chỉ số."
  if (
    roleColumn(fields.column_roles, "row_kind") &&
    hasBlankOrDuplicate(fields.time_grains.map((grain) => grain.row_kind_value?.trim() ?? ""))
  ) {
    return "Mỗi loại dòng cần một giá trị riêng, không để trống."
  }
  if (hasBlankOrDuplicate(fields.indicator_aggregations.map((item) => item.source_code.trim()))) {
    return "Mỗi mã cách tổng hợp cần một giá trị riêng, không để trống."
  }
  return null
}
