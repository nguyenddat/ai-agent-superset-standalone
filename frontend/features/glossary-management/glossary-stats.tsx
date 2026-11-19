"use client"

import Link from "next/link"
import { ArrowRightIcon, BookTextIcon, CircleXIcon } from "lucide-react"

import { GroupBars } from "@/components/stat-charts"
import { Coverage, ShareBar } from "@/components/stat-bars"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { groupByDomain, NO_DOMAIN } from "../business-model/domains"
import { useRuleOptions } from "../expert-rule-management/api"
import { useGlossary } from "./api"
import { TERM_STATES, termState, type TermState } from "./labels"

// Shared states keep one color across the glossary and rule cards; "in use" is always the first slot.
const COLORS: Record<TermState, string> = {
  approved: "var(--chart-1)",
  changed: "var(--chart-2)",
  draft: "var(--chart-3)",
  revoked: "var(--muted-foreground)",
}

export function GlossaryStatsCard({ connectionId }: { connectionId: string }) {
  const { data: terms, error: termsError } = useGlossary(connectionId)
  const { data: options, error: optionsError } = useRuleOptions(connectionId)
  const error = termsError ?? optionsError
  const base = `/connections/${connectionId}`

  const states = new Map<TermState, number>()
  for (const term of terms ?? []) states.set(termState(term), (states.get(termState(term)) ?? 0) + 1)
  const serving = (terms ?? []).filter((term) => term.serving).length
  const live = (terms ?? []).filter((term) => term.current.status !== "revoked")
  const groups = groupByDomain(live, (term) => term.business_domains)
  const synonyms = live.reduce((sum, term) => sum + term.current.synonyms.length, 0)
  const tables = options?.tables ?? []

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Thuật ngữ AI đang dùng</CardTitle>
        {terms && terms.length > 0 ? (
          <CardDescription>
            {live.length} thuật ngữ còn hiệu lực, {synonyms} từ đồng nghĩa.
          </CardDescription>
        ) : null}
        <CardAction>
          <Button variant="ghost" size="sm" asChild>
            <Link href={`${base}/glossary`}>
              Mở thuật ngữ
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
        ) : !terms || !options ? (
          <Skeleton className="h-72" />
        ) : terms.length === 0 ? (
          <Empty className="flex-1 p-4">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <BookTextIcon />
              </EmptyMedia>
              <EmptyTitle>Chưa có thuật ngữ</EmptyTitle>
              <EmptyDescription>Định nghĩa các từ nghiệp vụ như Khách hàng mới để AI hiểu đúng câu hỏi.</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button size="sm" variant="outline" asChild>
                <Link href={`${base}/glossary`}>Thêm thuật ngữ</Link>
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
          <>
            <Coverage label="Thuật ngữ" unit="thuật ngữ" doneLabel="AI đang dùng" done={serving} total={terms.length} large />
            <ShareBar
              label="Trạng thái thuật ngữ"
              unit="thuật ngữ"
              parts={(Object.keys(TERM_STATES) as TermState[]).map((state) => ({
                key: state,
                label: TERM_STATES[state].label,
                value: states.get(state) ?? 0,
                color: COLORS[state],
              }))}
            />
            <div className="flex flex-col gap-4 border-t pt-4">
              <Coverage
                label="Bảng có thuật ngữ đã duyệt"
                unit="bảng"
                doneLabel="có thuật ngữ đã duyệt"
                done={tables.filter((table) => table.glossary_terms.length > 0).length}
                total={tables.length}
              />
              {groups.length > 0 ? (
                <GroupBars
                  title="Thuật ngữ còn hiệu lực theo miền nghiệp vụ"
                  unit="thuật ngữ"
                  rows={groups.map((group) => ({ name: group.domain?.name ?? NO_DOMAIN, value: group.items.length }))}
                />
              ) : null}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
