"use client"

import Link from "next/link"
import { ArrowRightIcon, CircleXIcon, LinkIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { STATS_LIMIT, useDictionaryStats } from "./api"

const percent = (part: number, total: number) => (total ? Math.round((part / total) * 100) : 0)

function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className="h-1.5 overflow-hidden rounded-full bg-muted"
    >
      <div className="h-full rounded-full bg-chart-1" style={{ width: `${max ? (value / max) * 100 : 0}%` }} />
    </div>
  )
}

function Coverage({
  label,
  unit,
  described,
  total,
  large = false,
}: {
  label: string
  unit: string
  described: number
  total: number
  large?: boolean
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm">{label}</span>
        <span className="text-sm text-muted-foreground tabular-nums">
          <span className="text-foreground">{described}</span>/{total} {unit}
        </span>
      </div>
      {large && (
        <span className="text-3xl font-semibold tracking-tight tabular-nums">{percent(described, total)}%</span>
      )}
      <Meter value={described} max={total} label={`${label}: ${described}/${total} ${unit} đã mô tả`} />
    </div>
  )
}

type RankItem = {
  table_id: string
  schema_name: string
  table_name: string
  display_name: string
  value: number
  hint?: string
}

function RankList({ items, base, unit }: { items: RankItem[]; base: string; unit: string }) {
  const max = Math.max(...items.map((item) => item.value), 1)

  return (
    <ol className="flex flex-col">
      {items.map((item) => (
        <li key={item.table_id}>
          <Link
            href={`${base}/dictionary?table=${item.table_id}`}
            title={[`${item.schema_name}.${item.table_name}`, item.hint].filter(Boolean).join(" · ")}
            className="-mx-2 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_4rem] items-center gap-3 rounded-md px-2 py-1.5 text-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            <span className="truncate">{item.display_name}</span>
            <Meter value={item.value} max={max} label={`${item.display_name}: ${item.value} ${unit}`} />
            <span className="text-right text-muted-foreground tabular-nums">
              <span className="font-medium text-foreground">{item.value}</span> {unit}
            </span>
          </Link>
        </li>
      ))}
    </ol>
  )
}

export function DictionaryCoverageCard({ connectionId }: { connectionId: string }) {
  const { data: stats, error } = useDictionaryStats(connectionId)
  const base = `/connections/${connectionId}`

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Tỷ lệ bảng và cột đã mô tả</CardTitle>
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`${base}/dictionary`}>
              Mở từ điển
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {error ? (
          <Alert variant="destructive">
            <CircleXIcon />
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        ) : !stats ? (
          <Skeleton className="h-40" />
        ) : (
          <>
            <Coverage label="Bảng" unit="bảng" described={stats.described_table_count} total={stats.table_count} large />
            <Coverage label="Cột" unit="cột" described={stats.described_column_count} total={stats.column_count} large />
            {stats.schemas.length > 1 && (
              <div className="flex flex-col gap-3 border-t pt-4">
                {stats.schemas.map((schema) => (
                  <Coverage
                    key={schema.schema_id}
                    label={schema.schema_name}
                    unit="bảng"
                    described={schema.described_table_count}
                    total={schema.table_count}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function DictionaryRankCards({ connectionId }: { connectionId: string }) {
  const { data: stats, error } = useDictionaryStats(connectionId)
  const base = `/connections/${connectionId}`

  if (error || stats?.table_count === 0) return null
  if (!stats) {
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Card size="sm">
        <CardHeader>
          <CardTitle>Top {STATS_LIMIT} bảng nhiều cột nhất</CardTitle>
        </CardHeader>
        <CardContent>
          <RankList
            base={base}
            unit="cột"
            items={stats.most_columns.map((table) => ({
              ...table,
              value: table.column_count,
              hint: `${table.described_column_count}/${table.column_count} cột đã mô tả`,
            }))}
          />
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Top {STATS_LIMIT} bảng được tham chiếu nhiều nhất</CardTitle>
        </CardHeader>
        <CardContent className="flex-1">
          {stats.most_referenced.length ? (
            <RankList
              base={base}
              unit="bảng"
              items={stats.most_referenced.map((table) => ({ ...table, value: table.referencing_table_count }))}
            />
          ) : (
            <Empty className="h-full p-4">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <LinkIcon />
                </EmptyMedia>
                <EmptyTitle>Chưa có tham chiếu</EmptyTitle>
                <EmptyDescription>Chưa cột nào trong từ điển khai báo tham chiếu tới bảng khác.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
