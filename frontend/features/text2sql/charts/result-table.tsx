"use client"

import { useMemo } from "react"

import { DataTable, type DataTableColumn } from "@/components/data-table"

import { numberOf, type Row } from "./data"
import { cellText, fieldTitle, MISSING, todayIso } from "./format"
import { sequentialColor } from "./palette"
import type { ChartField } from "./spec"

type TableRow = { id: string; values: unknown[] }

// The rows of a query result with labelled, formatted columns; also the table view of every chart.
export function ResultTable({
  fields,
  rows,
  label,
  columns: only,
  heat,
}: {
  fields: ChartField[]
  rows: Row[]
  label: string
  columns?: string[]
  heat?: string | null
}) {
  const today = useMemo(() => todayIso(), [])
  const shown = useMemo(() => {
    const indexed = fields.map((field, index) => ({ field, index }))
    if (!only?.length) return indexed
    return only.map((name) => indexed.find((item) => item.field.name === name)).filter((item) => item !== undefined)
  }, [fields, only])
  const heatRange = useMemo(() => {
    const position = fields.findIndex((field) => field.name === heat)
    if (position < 0) return null
    const values = rows.map((row) => numberOf(row[position])).filter((value): value is number => value !== null)
    return values.length ? { position, min: Math.min(...values), max: Math.max(...values) } : null
  }, [fields, rows, heat])
  const columns = useMemo(
    () =>
      shown.map(({ field, index }, order): DataTableColumn<TableRow> => {
        const numeric = field.type === "number"
        return {
          key: String(index),
          header: fieldTitle(field),
          align: numeric ? "right" : "left",
          sortable: true,
          searchable: !numeric,
          value: (row) => {
            const value = row.values[index]
            if (numeric) return numberOf(value)
            return value === null || value === undefined ? null : String(value)
          },
          cell: (row) => {
            const value = row.values[index]
            const text = cellText(value, field, today)
            const muted = text === MISSING
            if (heatRange && heatRange.position === index && numberOf(value) !== null) {
              const span = heatRange.max - heatRange.min
              const ratio = span === 0 ? 1 : ((numberOf(value) as number) - heatRange.min) / span
              return (
                <span className="inline-flex items-center gap-1.5">
                  <span aria-hidden className="size-2.5 rounded-[3px]" style={{ background: sequentialColor(ratio) }} />
                  {text}
                </span>
              )
            }
            return muted ? <span className="text-muted-foreground">{text}</span> : text
          },
          card: order === 0 ? "title" : numeric ? "trailing" : "subtitle",
        }
      }),
    [shown, today, heatRange],
  )
  const data = useMemo(() => rows.map((values, index) => ({ id: String(index), values })), [rows])
  if (!rows.length) return <p className="py-2 text-sm text-muted-foreground">Truy vấn không trả về dòng nào.</p>
  return (
    <DataTable
      columns={columns}
      rows={data}
      label={label}
      searchPlaceholder="Tìm trong kết quả"
      searchable={rows.length > 10}
    />
  )
}
