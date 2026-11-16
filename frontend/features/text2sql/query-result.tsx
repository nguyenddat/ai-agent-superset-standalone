"use client"

import { useMemo } from "react"
import { CodeIcon, EyeOffIcon, ShieldCheckIcon, TableIcon, TriangleAlertIcon } from "lucide-react"

import { CodeBlock } from "@/components/code-block"
import { DataTable, type DataTableColumn } from "@/components/data-table"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import type { QueryData, ResultColumn, ResultValue } from "./types"

type Row = { id: string; values: ResultValue[] }

// Decimals arrive as strings ("350.00") because the backend serialises them with str().
const NUMERIC = /^-?\d+(\.\d+)?(e[+-]?\d+)?$/i

const asNumber = (value: ResultValue) =>
  typeof value === "number" ? value : typeof value === "string" && NUMERIC.test(value.trim()) ? Number(value) : null

const NUMERIC_TYPES = new Set(["integer", "decimal", "float"])
const plain = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 })
const whole = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 })
const percent = new Intl.NumberFormat("vi-VN", { style: "percent", maximumFractionDigits: 2 })
// Dates have no time zone, so reading them as UTC keeps the day the database returned.
const day = new Intl.DateTimeFormat("vi-VN", { timeZone: "UTC" })
const moment = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" })

type Formatter = (value: number) => string

function numberFormatter(column: ResultColumn): Formatter {
  if (column.format?.includes("%")) return (value) => percent.format(value)
  if (column.unit && /^[A-Z]{3}$/.test(column.unit)) {
    try {
      const currency = new Intl.NumberFormat("vi-VN", { style: "currency", currency: column.unit })
      return (value) => currency.format(value)
    } catch {
      // An unknown currency code falls back to the plain number.
    }
  }
  const base = column.data_type === "integer" ? whole : plain
  return column.unit ? (value) => `${base.format(value)} ${column.unit}` : (value) => base.format(value)
}

function dateText(value: ResultValue, type: ResultColumn["data_type"]) {
  if (typeof value !== "string") return null
  const time = Date.parse(value)
  if (Number.isNaN(time)) return null
  return type === "date" ? day.format(time) : moment.format(time)
}

function display(value: ResultValue, column: ResultColumn, formatter: Formatter | null) {
  if (value === null) return <span className="text-muted-foreground">trống</span>
  if (typeof value === "boolean") return value ? "Đúng" : "Sai"
  if (column.data_type === "date" || column.data_type === "datetime") return dateText(value, column.data_type) ?? String(value)
  const number = formatter ? asNumber(value) : null
  return number === null ? String(value) : formatter!(number)
}

export const columnTitle = (column: ResultColumn) => column.label?.trim() || column.name

function useColumns(data: QueryData) {
  return useMemo(() => {
    return data.columns.map((column, index): DataTableColumn<Row> => {
      const values = data.rows.map((row) => row[index]).filter((value) => value !== null)
      // Older results carry no data_type, so the values decide.
      const numeric = column.data_type
        ? NUMERIC_TYPES.has(column.data_type)
        : values.length > 0 && values.every((value) => asNumber(value) !== null)
      const metric = data.kind === "metric" && column.role === "metric" && !column.format && !column.unit
      const formatter = numeric ? numberFormatter(metric ? { ...column, format: data.metric?.format, unit: data.metric?.currency } : column) : null
      return {
        key: String(index),
        header: columnTitle(column),
        align: numeric ? "right" : "left",
        sortable: true,
        searchable: !numeric,
        value: (row) => {
          const value = row.values[index]
          return numeric ? asNumber(value) : value === null ? null : String(value)
        },
        cell: (row) => display(row.values[index], column, formatter),
        card: index === 0 ? "title" : numeric ? "trailing" : "subtitle",
      }
    })
  }, [data])
}

function parameterText(parameters: Record<string, unknown>) {
  return Object.entries(parameters)
    .map(([name, value]) => `${name} = ${JSON.stringify(value)}`)
    .join("\n")
}

export function QueryResult({ data }: { data: QueryData }) {
  const columns = useColumns(data)
  const rows = useMemo(() => data.rows.map((values, index) => ({ id: String(index), values })), [data.rows])
  const single = data.rows.length === 1 && data.columns.length === 1
  const masked = data.pii.masked_columns
  const title = data.kind === "metric" ? (data.metric?.label ?? "Metric") : "Kết quả truy vấn nhiều bảng"
  const hasParameters = Object.keys(data.parameters).length > 0
  const notes = [...data.rules_applied.map((rule) => `Áp dụng quy tắc ${rule}`), ...data.filters_overridden.map((rule) => `Ưu tiên điều kiện trong câu hỏi hơn quy tắc ${rule}`)]

  return (
    <Card size="sm" className="w-full">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{data.kind === "metric" ? "Metric" : "Dataset"}</Badge>
          <Badge variant="outline">
            {data.truncated ? `${data.rows.length} dòng đầu` : `${data.row_count} dòng`}
          </Badge>
          {masked.length > 0 && (
            <Badge variant="outline">
              <EyeOffIcon data-icon="inline-start" />
              Đã che {masked.length} cột cá nhân
            </Badge>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {data.truncated && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Kết quả đã bị cắt bớt</AlertTitle>
            <AlertDescription>Chỉ hiển thị {data.rows.length} dòng đầu theo giới hạn truy vấn.</AlertDescription>
          </Alert>
        )}
        {data.warnings.length > 0 && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Lưu ý về số liệu</AlertTitle>
            <AlertDescription>
              <ul className="ml-4 list-disc">
                {data.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}
        <Tabs defaultValue="table">
          <TabsList>
            <TabsTrigger value="table">
              <TableIcon />
              {single ? "Số liệu" : "Bảng"}
            </TabsTrigger>
            <TabsTrigger value="sql">
              <CodeIcon />
              SQL
            </TabsTrigger>
          </TabsList>
          <TabsContent value="table" className="pt-2">
            {single ? (
              <div className="flex flex-col gap-1 py-2">
                {data.kind === "dataset" && <span className="text-xs text-muted-foreground">{columnTitle(data.columns[0])}</span>}
                <span className="text-3xl font-semibold tabular-nums">{columns[0].cell!(rows[0])}</span>
              </div>
            ) : (
              <DataTable
                columns={columns}
                rows={rows}
                label={title}
                searchPlaceholder="Tìm trong kết quả"
                searchable={data.rows.length > 10}
              />
            )}
          </TabsContent>
          <TabsContent value="sql" className="flex flex-col gap-2 pt-2">
            <CodeBlock code={data.sql} language="sql" collapseAfter={14} className="text-xs" />
            {hasParameters && (
              <CodeBlock code={parameterText(data.parameters)} filename="Tham số" highlight={false} className="text-xs" />
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
      {notes.length > 0 && (
        <CardFooter className="flex flex-col items-start gap-1 border-t py-3 text-xs text-muted-foreground">
          {notes.map((note) => (
            <span key={note} className="flex items-start gap-1.5">
              <ShieldCheckIcon className="mt-px size-3.5 shrink-0" />
              {note}
            </span>
          ))}
        </CardFooter>
      )}
    </Card>
  )
}
