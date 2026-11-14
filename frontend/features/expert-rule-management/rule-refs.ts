import { useMemo } from "react"

import { useBusinessModel } from "../business-model/api"
import { useGlossary } from "../glossary-management/api"
import type { GlossaryTerm } from "../glossary-management/types"
import { useMetrics } from "../metric-management/api"
import type { Metric } from "../metric-management/types"
import { useRuleOptions } from "./api"
import type { OptionColumn, RuleOptionTable } from "./types"

export type TableRef = RuleOptionTable & { displayName: string; schemaName: string }

export type RuleRefs = {
  tables: TableRef[]
  tableById: Map<string, TableRef>
  columnById: Map<string, OptionColumn>
  termById: Map<string, GlossaryTerm>
  metricById: Map<string, Metric>
}

// The rule options name every table, column, eligible term and metric; the model adds display names, and the
// glossary and metric lists name links that are no longer eligible.
export function useRuleRefs(connectionId: string) {
  const options = useRuleOptions(connectionId)
  const model = useBusinessModel(connectionId)
  const glossary = useGlossary(connectionId)
  const metrics = useMetrics(connectionId)
  const error = options.error ?? model.error ?? glossary.error ?? metrics.error

  const refs = useMemo<RuleRefs | null>(() => {
    if (!options.data || !model.data || !glossary.data || !metrics.data) return null
    const modelTables = new Map(model.data.tables.map((table) => [table.table_id, table]))
    const tables = options.data.tables
      .map((table) => {
        const known = modelTables.get(table.table_id)
        return { ...table, displayName: known?.display_name ?? table.name, schemaName: known?.schema_name ?? "" }
      })
      .sort((a, b) => a.displayName.localeCompare(b.displayName, "vi"))
    return {
      tables,
      tableById: new Map(tables.map((table) => [table.table_id, table])),
      columnById: new Map(tables.flatMap((table) => table.columns.map((column) => [column.id, column] as const))),
      termById: new Map(glossary.data.map((term) => [term.id, term])),
      metricById: new Map(metrics.data.map((metric) => [metric.id, metric])),
    }
  }, [options.data, model.data, glossary.data, metrics.data])

  return { refs, error: error as Error | undefined }
}
