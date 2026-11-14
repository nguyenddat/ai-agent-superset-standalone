"use client"

import { useMemo } from "react"
import { Columns3Icon, SigmaIcon, Table2Icon, type LucideIcon } from "lucide-react"

import type { ComboboxOption } from "@/components/combobox"

import type { ModelTable } from "../business-model/types"
import { metricTitle } from "../metric-management/labels"
import type { Metric } from "../metric-management/types"
import { useConnectionColumns } from "./api"
import { linkKey } from "./labels"
import type { GlossaryLink, LinkKind } from "./types"

export const LINK_KINDS: Record<LinkKind, { label: string; icon: LucideIcon }> = {
  table: { label: "Bảng", icon: Table2Icon },
  column: { label: "Cột", icon: Columns3Icon },
  metric: { label: "Metric", icon: SigmaIcon },
}

export type LinkTarget = {
  link: GlossaryLink
  label: string
  detail: string
  href: string
  inactive: boolean
}

type ColumnEntry = { table: ModelTable; name: string; displayName: string; dataType: string }

// Tables and metrics are already loaded by the workspace; columns come from every table's dictionary, so they load
// only when `withColumns` is set.
export function useLinkTargets(connectionId: string, tables: ModelTable[], metrics: Metric[], withColumns: boolean) {
  const base = `/connections/${connectionId}`
  const columns = useConnectionColumns(
    tables.map((table) => table.table_id),
    withColumns,
  )

  return useMemo(() => {
    const tableById = new Map(tables.map((table) => [table.table_id, table]))
    const metricById = new Map(metrics.map((metric) => [metric.id, metric]))
    const columnById = new Map<string, ColumnEntry>()
    for (const dictionary of columns.data ?? []) {
      const table = tableById.get(dictionary.table_id)
      if (!table) continue
      for (const column of dictionary.columns) {
        columnById.set(column.column_id, {
          table,
          name: column.name,
          displayName: column.display_name,
          dataType: column.data_type,
        })
      }
    }

    function resolve(link: GlossaryLink): LinkTarget | null {
      if (link.kind === "table") {
        const table = tableById.get(link.id)
        if (!table) return null
        return {
          link,
          label: table.display_name,
          detail: `${table.schema_name}.${table.table_name}`,
          href: `${base}/dictionary?table=${table.table_id}`,
          inactive: false,
        }
      }
      if (link.kind === "column") {
        const column = columnById.get(link.id)
        if (!column) return null
        return {
          link,
          label: column.displayName,
          detail: `${column.table.table_name}.${column.name}`,
          href: `${base}/dictionary?table=${column.table.table_id}`,
          inactive: false,
        }
      }
      const metric = metricById.get(link.id)
      if (!metric) return null
      const table = metric.table_id ? tableById.get(metric.table_id) : undefined
      return {
        link,
        label: metricTitle(metric),
        detail: table ? `${table.table_name} · ${metric.name}` : metric.name,
        href: table ? `${base}/metrics?table=${table.table_id}` : `${base}/metrics`,
        inactive: !metric.is_active,
      }
    }

    const icon = (kind: LinkKind) => {
      const Icon = LINK_KINDS[kind].icon
      return <Icon className="size-4 text-muted-foreground" />
    }
    const options: ComboboxOption[] = [
      ...tables.map((table) => ({
        value: linkKey({ kind: "table", id: table.table_id }),
        label: table.display_name,
        description: `${table.schema_name}.${table.table_name}`,
        keywords: [table.table_name, table.schema_name],
        group: "Bảng",
        icon: icon("table"),
      })),
      ...metrics
        .filter((metric) => metric.is_active && metric.table_id && tableById.has(metric.table_id))
        .map((metric) => ({
          value: linkKey({ kind: "metric", id: metric.id }),
          label: metricTitle(metric),
          description: `${tableById.get(metric.table_id!)!.display_name} · ${metric.name}`,
          keywords: [metric.name, metric.expression],
          group: "Metric",
          icon: icon("metric"),
        })),
      ...[...columnById].map(([id, column]) => ({
        value: linkKey({ kind: "column", id }),
        label: column.displayName,
        description: `${column.table.table_name}.${column.name} · ${column.dataType}`,
        keywords: [column.name, column.table.table_name, column.table.display_name],
        group: `Cột · ${column.table.display_name}`,
        icon: icon("column"),
      })),
    ]

    return {
      resolve,
      options,
      columnsLoading: withColumns && !columns.data && !columns.error,
      columnsError: columns.error as Error | undefined,
    }
  }, [base, tables, metrics, columns.data, columns.error, withColumns])
}

export type LinkTargets = ReturnType<typeof useLinkTargets>
