import type { DatabaseConnection } from "./types"

export type ScopeField = "schema_includes" | "schema_excludes" | "table_includes" | "table_excludes"
export type MetadataScope = Pick<DatabaseConnection, ScopeField>

export const SCOPE_FIELDS: ScopeField[] = ["schema_includes", "schema_excludes", "table_includes", "table_excludes"]
export const MAX_PATTERNS = 100
export const MAX_PATTERN_LENGTH = 255

export const emptyScope = (): MetadataScope => ({
  schema_includes: [],
  schema_excludes: [],
  table_includes: [],
  table_excludes: [],
})

// Same rules as Python's fnmatchcase, which the backend uses: * and ? wildcards, [abc] and [!abc] sets, case-sensitive.
function globToRegExp(pattern: string) {
  let source = ""
  for (let index = 0; index < pattern.length; index += 1) {
    const char = pattern[index]
    if (char === "*") source += ".*"
    else if (char === "?") source += "."
    else if (char === "[") {
      const end = pattern.indexOf("]", index + 2)
      if (end === -1) source += "\\["
      else {
        let set = pattern.slice(index + 1, end).replaceAll("\\", "\\\\")
        if (set.startsWith("!")) set = `^${set.slice(1)}`
        else if (set.startsWith("^")) set = `\\${set}`
        source += `[${set}]`
        index = end
      }
    } else source += char.replace(/[.+^${}()|\\\]]/g, "\\$&")
  }
  return new RegExp(`^${source}$`, "s")
}

const matching = (candidates: string[], patterns: string[]) =>
  patterns.find((pattern) => candidates.some((candidate) => globToRegExp(pattern).test(candidate)))

export type ScopeVerdict = { selected: boolean; reason: string }

/** Whether a schema, or a table written as `schema.table`, falls inside the scope, and the rule that decides it. */
export function explainScope(scope: MetadataScope, name: string): ScopeVerdict | null {
  const [schema, ...rest] = name.trim().split(".")
  const table = rest.join(".")
  if (!schema) return null
  if (schema === "information_schema" || schema.startsWith("pg_")) {
    return { selected: false, reason: "Schema hệ thống luôn bị bỏ qua." }
  }
  const schemaExcluded = matching([schema], scope.schema_excludes)
  if (schemaExcluded) return { selected: false, reason: `Schema khớp mẫu bỏ qua "${schemaExcluded}".` }
  const schemaIncluded = matching([schema], scope.schema_includes)
  if (scope.schema_includes.length > 0 && !schemaIncluded) {
    return { selected: false, reason: "Schema không khớp mẫu nào trong \"Chỉ lấy schema\"." }
  }
  if (!table) {
    return {
      selected: true,
      reason: schemaIncluded ? `Schema khớp mẫu "${schemaIncluded}".` : "Schema được lấy vì không giới hạn schema.",
    }
  }
  const candidates = [table, `${schema}.${table}`]
  const tableExcluded = matching(candidates, scope.table_excludes)
  if (tableExcluded) return { selected: false, reason: `Bảng khớp mẫu bỏ qua "${tableExcluded}".` }
  const tableIncluded = matching(candidates, scope.table_includes)
  if (scope.table_includes.length > 0 && !tableIncluded) {
    return { selected: false, reason: "Bảng không khớp mẫu nào trong \"Chỉ lấy bảng\"." }
  }
  return {
    selected: true,
    reason: tableIncluded ? `Bảng khớp mẫu "${tableIncluded}".` : "Bảng được lấy vì không giới hạn bảng.",
  }
}

export const sameScope = (a: MetadataScope, b: MetadataScope) =>
  SCOPE_FIELDS.every((field) => JSON.stringify(a[field]) === JSON.stringify(b[field]))
