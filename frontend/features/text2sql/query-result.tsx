"use client"

import { BarChart3Icon, CodeIcon, InfoIcon, TableIcon, TriangleAlertIcon } from "lucide-react"

import { CodeBlock } from "@/components/code-block"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

import { ChartPanel } from "./charts/chart-panel"
import { ChartView } from "./charts/chart-view"
import { ResultTable } from "./charts/result-table"
import { TOOL_LABELS } from "./labels"
import type { DataResult } from "./results"
import type { ChatActions, Turn } from "./use-chat"

const isKpi = (result: DataResult) =>
  result.step.rows.length === 1 && result.fields.length <= 4 && result.fields.every((field) => field.type === "number")

// One query behind the answer: its rows (labelled columns), its chart and its SQL with the technical notes.
export function QueryResult({ turn, result, actions }: { turn: Turn; result: DataResult; actions: ChatActions }) {
  const { step } = result
  const kpi = isKpi(result)
  return (
    <Card size="sm" className="w-full">
      <CardHeader>
        <CardTitle>{result.title}</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary">{TOOL_LABELS[step.tool] ?? step.tool}</Badge>
          <Badge variant="outline">{step.truncated ? `${step.rows.length} dòng đầu` : `${step.row_count} dòng`}</Badge>
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {step.truncated && (
          <Alert>
            <TriangleAlertIcon />
            <AlertTitle>Kết quả đã bị cắt bớt</AlertTitle>
            <AlertDescription>
              Chỉ có {step.rows.length} dòng đầu theo giới hạn truy vấn; biểu đồ chỉ vẽ các dòng này.
            </AlertDescription>
          </Alert>
        )}
        <Tabs defaultValue="table">
          <TabsList>
            <TabsTrigger value="table">
              <TableIcon />
              {kpi ? "Số liệu" : "Bảng"}
            </TabsTrigger>
            <TabsTrigger value="chart">
              <BarChart3Icon />
              Biểu đồ
            </TabsTrigger>
            <TabsTrigger value="sql">
              <CodeIcon />
              SQL
            </TabsTrigger>
          </TabsList>
          <TabsContent value="table" className="pt-2">
            {kpi ? (
              <ChartView
                spec={{ type: "kpi", encoding: { y: result.fields.map((field) => ({ field: field.name })) } }}
                fields={result.fields}
                rows={step.rows}
              />
            ) : (
              <ResultTable fields={result.fields} rows={step.rows} label={result.title} />
            )}
          </TabsContent>
          <TabsContent value="chart" className="pt-2">
            <ChartPanel turn={turn} result={result} actions={actions} />
          </TabsContent>
          <TabsContent value="sql" className="flex flex-col gap-2 pt-2">
            {step.sql && <CodeBlock code={step.sql} language="sql" collapseAfter={14} className="text-xs" />}
            <CodeBlock
              code={JSON.stringify(step.arguments, null, 2)}
              filename="Tham số của công cụ"
              highlight={false}
              className="text-xs"
            />
            {step.notes.length > 0 && (
              <div className="flex flex-col gap-1 rounded-lg border p-3 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Ghi chú kỹ thuật</span>
                {step.notes.map((note) => (
                  <span key={note} className="flex items-start gap-1.5">
                    <InfoIcon className="mt-px size-3.5 shrink-0" />
                    {note}
                  </span>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
