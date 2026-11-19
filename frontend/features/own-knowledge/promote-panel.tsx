"use client"

import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { mutate } from "swr"

import { Skeleton } from "@/components/ui/skeleton"
import { ApiError } from "@/lib/api"

import type { ModelTable } from "../business-model/types"
import { approveRule } from "../expert-rule-management/api"
import { RuleEditor } from "../expert-rule-management/rule-editor"
import { useRuleRefs } from "../expert-rule-management/rule-refs"
import type { ExpertRule } from "../expert-rule-management/types"
import { approveTerm } from "../glossary-management/api"
import { useLinkTargets } from "../glossary-management/link-targets"
import { TermEditor } from "../glossary-management/term-editor"
import type { GlossaryTerm } from "../glossary-management/types"
import { MetricEditor } from "../metric-management/metric-editor"
import type { Metric } from "../metric-management/types"
import { entriesKey, promoteEntry } from "./api"
import type { PromoteRequest } from "./entry-detail"
import { KINDS } from "./labels"
import type { OwnEntry } from "./types"

type PromotePanelProps = {
  connectionId: string
  entry: OwnEntry
  request: PromoteRequest
  terms: GlossaryTerm[]
  metrics: Metric[]
  rules: ExpertRule[]
  tables: ModelTable[]
  onClose: () => void
  onDone: () => void
}

export function PromotePanel(props: PromotePanelProps) {
  const { connectionId, entry, request, onDone } = props
  const router = useRouter()
  const title = `Đưa “${entry.name}” vào kho`
  const base = `/connections/${connectionId}`

  function promote<T>(input: object) {
    return promoteEntry<T>(entry, request.kind, { ...input }, request.reviewer, request.note)
  }

  // Approval runs after promotion has landed, so a refused approval leaves a draft rather than undoing the promotion.
  async function finish(name: string, href: string, approve: (() => Promise<unknown>) | null) {
    let approved = false
    if (approve) {
      try {
        await approve()
        approved = true
        // Whether the AI still reads the user's own entry depends on the approval that just landed.
        await mutate(entriesKey(connectionId))
      } catch (caught) {
        toast.error("Đã đưa vào kho nhưng chưa duyệt được", {
          description: caught instanceof ApiError ? caught.message : "Hãy duyệt ở tab của bản ghi.",
        })
      }
    }
    const tab = KINDS[request.kind].label
    toast.success("Đã đưa vào kho", {
      description:
        request.kind === "metric"
          ? `Metric ${name} đã hoạt động.`
          : approved
            ? `${name} đã được duyệt, AI dùng ngay cho mọi người.`
            : `${name} đang chờ duyệt ở tab ${tab}.`,
      action: { label: `Mở tab ${tab}`, onClick: () => router.push(href) },
    })
    onDone()
  }

  if (request.kind === "glossary") {
    return (
      <GlossaryPromotion
        {...props}
        title={title}
        create={(input) => promote<GlossaryTerm>(input)}
        onSaved={(term) =>
          finish(
            term.canonical_name,
            `${base}/glossary?term=${term.id}`,
            request.approve ? () => approveTerm(connectionId, term.id, term.current.number) : null,
          )
        }
      />
    )
  }
  if (request.kind === "metric") {
    return (
      <MetricEditor
        connectionId={connectionId}
        tables={props.tables}
        metrics={props.metrics}
        metric={null}
        initialTable={null}
        onClose={props.onClose}
        onSaved={(metric) => finish(metric.label || metric.name, `${base}/metrics?table=${metric.table_id}`, null)}
        onDeleted={props.onClose}
        promotion={{
          title,
          seed: { table: entry.table_id, label: entry.name, description: entry.definition },
          create: (input) => promote<Metric>(input),
        }}
      />
    )
  }
  return (
    <RulePromotion
      {...props}
      title={title}
      create={(input) => promote<ExpertRule>(input)}
      onSaved={(rule) =>
        finish(
          rule.name,
          `${base}/rules?rule=${rule.id}`,
          request.approve ? () => approveRule(connectionId, rule.id, rule.current.number) : null,
        )
      }
    />
  )
}

function GlossaryPromotion({
  connectionId,
  entry,
  terms,
  metrics,
  tables,
  onClose,
  title,
  create,
  onSaved,
}: PromotePanelProps & {
  title: string
  create: (input: object) => Promise<GlossaryTerm>
  onSaved: (term: GlossaryTerm) => void
}) {
  const targets = useLinkTargets(connectionId, tables, metrics, true)
  return (
    <TermEditor
      connectionId={connectionId}
      terms={terms}
      term={null}
      initialDomainId={null}
      targets={targets}
      onClose={onClose}
      onSaved={onSaved}
      onReload={onClose}
      promotion={{
        title,
        seed: {
          name: entry.name,
          definition: entry.definition,
          links: entry.table_id ? [{ kind: "table", id: entry.table_id }] : [],
        },
        create,
      }}
    />
  )
}

function RulePromotion({
  connectionId,
  entry,
  rules,
  onClose,
  title,
  create,
  onSaved,
}: PromotePanelProps & {
  title: string
  create: (input: object) => Promise<ExpertRule>
  onSaved: (rule: ExpertRule) => void
}) {
  const { refs, error } = useRuleRefs(connectionId)
  if (error) return <p className="p-5 text-sm text-destructive">{error.message}</p>
  if (!refs) {
    return (
      <div className="flex flex-col gap-3 p-5">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-40" />
      </div>
    )
  }
  return (
    <RuleEditor
      connectionId={connectionId}
      rules={rules}
      refs={refs}
      rule={null}
      initialTable={null}
      onClose={onClose}
      onSaved={onSaved}
      onReload={onClose}
      promotion={{ title, seed: { name: entry.name, table: entry.table_id, description: entry.definition }, create }}
    />
  )
}
