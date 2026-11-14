"use client"

import Link from "next/link"
import { ArrowRightIcon, CircleXIcon, ScaleIcon } from "lucide-react"

import { ColumnBars } from "@/components/stat-charts"
import { Coverage, RankList, ShareBar } from "@/components/stat-bars"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { useRuleOptions, useRules } from "./api"
import { RULE_STATES, ruleState, type RuleState } from "./labels"

const TOP = 5

// Same colors as the glossary card for the states both share; the bar keeps this order.
const ORDER: RuleState[] = ["active", "changed", "draft", "stale", "revoked"]
const COLORS: Record<RuleState, string> = {
  active: "var(--chart-1)",
  changed: "var(--chart-2)",
  draft: "var(--chart-3)",
  stale: "var(--chart-4)",
  revoked: "var(--muted-foreground)",
}

export function RuleStatsCard({ connectionId }: { connectionId: string }) {
  const { data: rules, error: rulesError } = useRules(connectionId)
  const { data: options, error: optionsError } = useRuleOptions(connectionId)
  const error = rulesError ?? optionsError
  const base = `/connections/${connectionId}`

  const states = new Map<RuleState, number>()
  for (const rule of rules ?? []) states.set(ruleState(rule), (states.get(ruleState(rule)) ?? 0) + 1)
  const live = (rules ?? []).filter((rule) => rule.current.status !== "revoked")
  const content = [
    { name: "Điều kiện", value: live.reduce((sum, rule) => sum + rule.current.conditions.length, 0) },
    { name: "Ngoại lệ", value: live.reduce((sum, rule) => sum + rule.current.exceptions.length, 0) },
    { name: "Ví dụ", value: live.reduce((sum, rule) => sum + rule.current.examples.length, 0) },
    { name: "Thuật ngữ", value: live.reduce((sum, rule) => sum + rule.current.glossary_term_ids.length, 0) },
    { name: "Metric", value: live.reduce((sum, rule) => sum + rule.current.metric_ids.length, 0) },
  ]
  const tables = new Map(options?.tables.map((table) => [table.table_id, table.name]))
  const perTable = new Map<string, number>()
  for (const rule of live) perTable.set(rule.table_id, (perTable.get(rule.table_id) ?? 0) + 1)
  const top = [...perTable].sort(([, a], [, b]) => b - a).slice(0, TOP)

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Quy tắc AI đang áp dụng</CardTitle>
        {rules && rules.length > 0 ? (
          <CardDescription>
            {live.length} quy tắc còn hiệu lực trên {perTable.size} bảng.
          </CardDescription>
        ) : null}
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`${base}/rules`}>
              Mở quy tắc
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        {error ? (
          <Alert variant="destructive">
            <CircleXIcon />
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ) : !rules || !options ? (
          <Skeleton className="h-72" />
        ) : rules.length === 0 ? (
          <Empty className="flex-1 p-4">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <ScaleIcon />
              </EmptyMedia>
              <EmptyTitle>Chưa có quy tắc</EmptyTitle>
              <EmptyDescription>Ghi lại cách chuyên gia hiểu dữ liệu, như thế nào là Ngày nắng nóng.</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button size="sm" variant="outline" asChild>
                <Link href={`${base}/rules`}>Thêm quy tắc</Link>
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
          <>
            <Coverage
              label="Quy tắc"
              unit="quy tắc"
              doneLabel="AI đang áp dụng"
              done={states.get("active") ?? 0}
              total={rules.length}
              large
            />
            <ShareBar
              label="Trạng thái quy tắc"
              unit="quy tắc"
              parts={ORDER.map((state) => ({
                key: state,
                label: RULE_STATES[state].label,
                value: states.get(state) ?? 0,
                color: COLORS[state],
              }))}
            />
            <div className="flex flex-col gap-4 border-t pt-4">
              <ColumnBars title="Nội dung của các quy tắc còn hiệu lực" unit="mục" rows={content} height={140} />
              {top.length ? (
                <div className="flex flex-col gap-2">
                  <h3 className="text-sm font-medium">Bảng nhiều quy tắc nhất</h3>
                  <RankList
                    unit="quy tắc"
                    items={top.map(([id, count]) => ({
                      id,
                      label: tables.get(id) ?? "Bảng đã xóa",
                      title: tables.get(id) ?? id,
                      value: count,
                      href: `${base}/rules?table=${id}`,
                    }))}
                  />
                </div>
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
