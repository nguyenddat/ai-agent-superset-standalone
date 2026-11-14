"use client"

import { useState } from "react"
import Link from "next/link"
import { ArrowUpRightIcon, GitCompareArrowsIcon } from "lucide-react"

import { Badge } from "@/components/badge"
import { WordDiff } from "@/components/diff-review"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

import { foldName } from "../glossary-management/labels"
import { SYSTEM_STATES, VERDICTS, type Findings, type PeerMatch, type SystemItem, type SystemMatch } from "./analysis"
import { KINDS, REVIEW_STATES } from "./labels"
import type { OwnEntry } from "./types"

export function Overlap({ entry, findings, onOpenEntry }: { entry: OwnEntry; findings: Findings; onOpenEntry: (id: string) => void }) {
  const { target, system, peers } = findings
  const lostTarget = entry.review_status === "promoted" && !!entry.promoted_id && !target

  return (
    <section aria-labelledby="overlap-heading" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="overlap-heading" className="text-sm font-medium">
          Trùng và mâu thuẫn
        </h3>
        {findings.conflicts ? (
          <Badge tone="danger" size="sm">{`${findings.conflicts} chỗ khác`}</Badge>
        ) : null}
        {findings.duplicates ? (
          <Badge tone="primary" size="sm">{`${findings.duplicates} bản trùng`}</Badge>
        ) : null}
      </div>

      {target ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-muted-foreground">Bản trong kho được tạo từ mục này</p>
          <SystemCard item={target} entry={entry} />
        </div>
      ) : null}
      {lostTarget ? (
        <Alert>
          <AlertTitle>Bản trong kho không còn</AlertTitle>
          <AlertDescription>Bản ghi tạo từ mục này đã bị xóa, nên AI dùng lại cách hiểu riêng của người dùng.</AlertDescription>
        </Alert>
      ) : null}

      {system.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-muted-foreground">Trong kho</p>
          {system.map((item) => (
            <SystemCard key={item.id} item={item} entry={entry} match={item} />
          ))}
        </div>
      ) : null}

      {peers.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-xs text-muted-foreground">Người dùng khác</p>
          {peers.map((peer) => (
            <PeerCard key={peer.entry.id} peer={peer} entry={entry} onOpen={() => onOpenEntry(peer.entry.id)} />
          ))}
        </div>
      ) : null}

      {!system.length && !peers.length ? (
        <p className="rounded-lg border border-dashed px-3 py-2.5 text-sm text-muted-foreground">
          Không thấy mục cùng tên trong kho hay của người dùng khác. Việc so chỉ dựa trên tên, nên cùng ý mà khác tên vẫn có
          thể lọt.
        </p>
      ) : null}
    </section>
  )
}

function matchLabel(entry: OwnEntry, item: SystemMatch) {
  if (foldName(item.name) === foldName(entry.name)) return "Cùng tên"
  return item.exact ? "Trùng từ đồng nghĩa" : "Tên gần giống"
}

function SystemCard({ item, entry, match }: { item: SystemItem; entry: OwnEntry; match?: SystemMatch }) {
  const kind = KINDS[item.kind]
  const state = SYSTEM_STATES[item.state]
  return (
    <Card
      icon={<kind.icon className="size-4 text-muted-foreground" />}
      title={
        <Link href={item.href} className="inline-flex min-w-0 items-center gap-1 font-medium underline-offset-4 hover:underline">
          <span className="truncate">{item.name}</span>
          <ArrowUpRightIcon className="size-3.5 shrink-0 text-muted-foreground" />
        </Link>
      }
      subtitle={[kind.label, match ? matchLabel(entry, match) : null].filter(Boolean).join(" · ")}
      badges={
        <>
          <Badge tone={state.tone} size="sm" dot>
            {state.label}
          </Badge>
          {match?.verdict ? (
            <Badge tone={VERDICTS[match.verdict].tone} size="sm" title={VERDICTS[match.verdict].hint}>
              {VERDICTS[match.verdict].label}
            </Badge>
          ) : null}
        </>
      }
      text={item.text}
      emptyText={item.kind === "metric" ? "Metric chưa có mô tả để so." : "Chưa có mô tả để so."}
      detail={item.detail}
      compare={match?.verdict && match.verdict !== "same" ? { other: item.text!, source: "kho" } : null}
      definition={entry.definition}
    />
  )
}

function PeerCard({ peer, entry, onOpen }: { peer: PeerMatch; entry: OwnEntry; onOpen: () => void }) {
  const other = peer.entry
  const status = REVIEW_STATES[other.review_status]
  return (
    <Card
      icon={<span className="text-xs font-medium text-muted-foreground uppercase">{other.user_id.slice(0, 1)}</span>}
      title={
        <button type="button" onClick={onOpen} className="truncate text-left font-medium underline-offset-4 hover:underline">
          {other.user_id}
        </button>
      }
      subtitle={[
        other.kind === entry.kind ? null : KINDS[other.kind].label,
        peer.exact ? "Cùng tên" : `Tên gần giống: “${other.name}”`,
      ]
        .filter(Boolean)
        .join(" · ")}
      badges={
        <>
          <Badge tone={status.tone} size="sm" dot>
            {status.label}
          </Badge>
          <Badge tone={VERDICTS[peer.verdict].tone} size="sm" title={VERDICTS[peer.verdict].hint}>
            {VERDICTS[peer.verdict].label}
          </Badge>
        </>
      }
      text={other.definition}
      emptyText=""
      detail={null}
      compare={peer.verdict === "same" ? null : { other: other.definition, source: other.user_id }}
      definition={entry.definition}
    />
  )
}

function Card({
  icon,
  title,
  subtitle,
  badges,
  text,
  emptyText,
  detail,
  compare,
  definition,
}: {
  icon: React.ReactNode
  title: React.ReactNode
  subtitle: string
  badges: React.ReactNode
  text: string | null
  emptyText: string
  detail: string | null
  compare: { other: string; source: string } | null
  definition: string
}) {
  const [diffing, setDiffing] = useState(false)
  return (
    <div className="flex flex-col gap-2 rounded-lg border px-3 py-2.5">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md border bg-background">{icon}</span>
        <div className="flex min-w-0 flex-1 flex-col text-sm">
          {title}
          {subtitle ? <span className="truncate text-xs text-muted-foreground">{subtitle}</span> : null}
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1">{badges}</div>
      </div>
      {diffing && compare ? (
        <div className="flex flex-col gap-1">
          <WordDiff before={compare.other} after={definition} />
          <p className="text-xs text-muted-foreground">
            Đỏ: chỉ có ở {compare.source === "kho" ? "bản trong kho" : compare.source}. Xanh: chỉ có ở cách hiểu đang xem.
          </p>
        </div>
      ) : text?.trim() ? (
        <p className="text-sm leading-relaxed">{text}</p>
      ) : emptyText ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : null}
      {detail ? <code className="truncate rounded bg-muted px-2 py-1 font-mono text-xs">{detail}</code> : null}
      {compare ? (
        <Button variant="ghost" size="xs" className="self-start" aria-pressed={diffing} onClick={() => setDiffing(!diffing)}>
          <GitCompareArrowsIcon data-icon="inline-start" />
          {diffing ? "Xem nguyên văn" : "So từng chữ"}
        </Button>
      ) : null}
    </div>
  )
}
