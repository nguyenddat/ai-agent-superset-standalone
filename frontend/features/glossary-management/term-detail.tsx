"use client"

import { useState } from "react"
import Link from "next/link"
import {
  ArchiveRestoreIcon,
  BanIcon,
  CheckIcon,
  CircleXIcon,
  PencilIcon,
  Trash2Icon,
  TriangleAlertIcon,
  XIcon,
} from "lucide-react"
import { toast } from "sonner"

import { DiffReview, type ChangeDecision, type DiffChange } from "@/components/diff-review"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

import { DomainBadges } from "../business-model/domains"
import { dateFormat } from "../database-connections/connection-format"
import { approveContent, approveTerm, deleteTerm, refreshGlossary, revokeTerm, saveDraft } from "./api"
import { contentOf, linkKey, sameLinks, sameSynonyms, termState } from "./labels"
import { LINK_KINDS, type LinkTargets } from "./link-targets"
import { TermStatus } from "./term-status"
import type { GlossaryContent, GlossaryLink, GlossaryTerm, LinkKind } from "./types"

type TermDetailProps = {
  connectionId: string
  term: GlossaryTerm
  targets: LinkTargets
  onClose: () => void
  onEdit: () => void
  onDeleted: () => void
}

type Busy = "approve" | "revoke" | "restore" | "delete"
type Confirm = "revoke" | "delete"
type ChangeId = keyof GlossaryContent

const CHANGE_LABELS: Record<ChangeId, string> = {
  definition: "Định nghĩa",
  synonyms: "Từ đồng nghĩa",
  links: "Liên kết dữ liệu",
}

export function TermDetail({ connectionId, term, targets, onClose, onEdit, onDeleted }: TermDetailProps) {
  const state = termState(term)
  const { current, serving } = term
  const [busy, setBusy] = useState<Busy | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  // Decisions belong to one draft; a newer revision starts the review over.
  const [review, setReview] = useState<{ revision: number; decisions: Record<string, ChangeDecision> }>({
    revision: current.number,
    decisions: {},
  })
  const decisions = review.revision === current.number ? review.decisions : {}

  const linkText = (links: GlossaryLink[]) =>
    links
      .map((link) => {
        const target = targets.resolve(link)
        return `${LINK_KINDS[link.kind].label} ${target ? target.label : "…"}`
      })
      .join(", ")

  const changes: DiffChange[] = []
  if (state === "changed" && serving) {
    const change = (id: ChangeId, before: string, after: string) =>
      changes.push({ id, label: CHANGE_LABELS[id], before, after })
    if (current.definition !== serving.definition) change("definition", serving.definition, current.definition)
    if (!sameSynonyms(current.synonyms, serving.synonyms)) {
      change("synonyms", serving.synonyms.join(", "), current.synonyms.join(", "))
    }
    if (!sameLinks(current.links, serving.links)) change("links", linkText(serving.links), linkText(current.links))
  }
  const rejected = changes.filter((change) => decisions[change.id] === "rejected").map((change) => change.id as ChangeId)
  const keepsNothing = changes.length > 0 && rejected.length === changes.length

  async function run(kind: Busy, action: () => Promise<unknown>, success: string) {
    setBusy(kind)
    setError(null)
    try {
      await action()
      toast.success(success, { description: term.canonical_name })
      setConfirm(null)
      return true
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không thực hiện được thao tác."))
      return false
    } finally {
      setBusy(null)
    }
  }

  function approve() {
    if (!rejected.length || !serving) {
      return run("approve", () => approveTerm(connectionId, term.id, current.number), "Đã duyệt thuật ngữ")
    }
    const content = contentOf(current)
    for (const id of rejected) Object.assign(content, { [id]: serving[id] })
    return run(
      "approve",
      () => approveContent(connectionId, term, content),
      keepsNothing ? "Đã bỏ bản nháp, giữ bản đang dùng" : `Đã duyệt, bỏ ${rejected.length} thay đổi`,
    )
  }

  const approveLabel = keepsNothing
    ? "Bỏ bản nháp"
    : rejected.length
      ? `Duyệt, bỏ ${rejected.length} thay đổi`
      : "Duyệt"

  return (
    <section aria-label={`Thuật ngữ ${term.canonical_name}`} className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h2 className="truncate text-lg font-semibold tracking-tight">{term.canonical_name}</h2>
          <div className="flex flex-wrap items-center gap-2">
            <TermStatus term={term} explained />
            <DomainBadges domains={term.business_domains} />
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-6 px-5 py-5">
          {state === "changed" ? (
            changes.length ? (
              <DiffReview
                key={current.number}
                title={`So với bản đang dùng #${serving!.number}`}
                changes={changes}
                decisions={decisions}
                onDecisionsChange={(next) => setReview({ revision: current.number, decisions: next })}
              />
            ) : (
              <Alert>
                <TriangleAlertIcon />
                <AlertDescription>Bản nháp giống hệt bản đang dùng. Duyệt để đóng bản nháp.</AlertDescription>
              </Alert>
            )
          ) : null}

          <TermSection title={state === "changed" ? `Định nghĩa trong bản nháp #${current.number}` : "Định nghĩa"}>
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{current.definition}</p>
          </TermSection>

          <TermSection title="Từ đồng nghĩa">
            {current.synonyms.length ? (
              <div className="flex flex-wrap gap-1.5">
                {current.synonyms.map((synonym) => (
                  <Badge key={synonym} variant="secondary">
                    {synonym}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Chưa có. Thêm tên khác để AI nhận ra thuật ngữ trong câu hỏi.</p>
            )}
          </TermSection>

          <TermSection title="Liên kết dữ liệu">
            <LinkList links={current.links} targets={targets} />
          </TermSection>

          <Separator />

          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Bản hiện tại</dt>
            <dd>
              #{current.number} · {dateFormat.format(new Date(current.created_at))}
            </dd>
            <dt className="text-muted-foreground">AI đang dùng</dt>
            <dd>{serving ? `Bản #${serving.number}` : "Không có bản nào"}</dd>
            <dt className="text-muted-foreground">Tạo lúc</dt>
            <dd>{dateFormat.format(new Date(term.created_at))}</dd>
          </dl>

          {error ? (
            <Alert variant="destructive">
              <CircleXIcon />
              {error.status === 409 ? <AlertTitle>Không thực hiện được</AlertTitle> : null}
              <AlertDescription>{error.message}</AlertDescription>
              {error.status === 409 ? (
                <AlertAction>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={async () => {
                      await refreshGlossary(connectionId)
                      setError(null)
                    }}
                  >
                    Tải lại
                  </Button>
                </AlertAction>
              ) : null}
            </Alert>
          ) : null}
        </div>
      </ScrollArea>

      <footer className="flex flex-wrap items-center gap-2 border-t px-5 py-3">
        {confirm ? (
          <div className="flex w-full flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1 text-sm">
              {confirm === "delete"
                ? "Xóa thuật ngữ cùng mọi phiên bản?"
                : state === "changed"
                  ? "Thu hồi? AI ngừng dùng ngay và bản nháp chưa duyệt bị bỏ."
                  : "Thu hồi? AI sẽ ngừng dùng thuật ngữ này ngay."}
            </span>
            <Button
              variant="destructive"
              size="sm"
              disabled={busy !== null}
              onClick={() =>
                confirm === "delete"
                  ? void run("delete", () => deleteTerm(connectionId, term.id), "Đã xóa thuật ngữ").then(
                      (done) => done && onDeleted(),
                    )
                  : void run("revoke", () => revokeTerm(connectionId, term.id, current.number), "Đã thu hồi thuật ngữ")
              }
            >
              {busy === confirm ? <Spinner data-icon="inline-start" /> : null}
              {confirm === "delete" ? "Xóa" : "Thu hồi"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirm(null)}>
              Giữ lại
            </Button>
          </div>
        ) : (
          <>
            <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setConfirm("delete")}>
              <Trash2Icon data-icon="inline-start" />
              Xóa
            </Button>
            <div className="ml-auto flex flex-wrap justify-end gap-2">
              {serving ? (
                <Button variant="outline" onClick={() => setConfirm("revoke")}>
                  <BanIcon data-icon="inline-start" />
                  Thu hồi
                </Button>
              ) : null}
              {state === "revoked" ? (
                <Button
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() =>
                    void run(
                      "restore",
                      () =>
                        saveDraft(connectionId, term.id, {
                          ...contentOf(current),
                          business_domain_ids: term.business_domains.map((domain) => domain.id),
                          expected_revision: current.number,
                        }),
                      "Đã khôi phục thành bản nháp",
                    )
                  }
                >
                  {busy === "restore" ? (
                    <Spinner data-icon="inline-start" />
                  ) : (
                    <ArchiveRestoreIcon data-icon="inline-start" />
                  )}
                  Khôi phục
                </Button>
              ) : null}
              <Button variant={state === "approved" || state === "revoked" ? "default" : "outline"} onClick={onEdit}>
                <PencilIcon data-icon="inline-start" />
                Sửa
              </Button>
              {state === "draft" || state === "changed" ? (
                <Button
                  variant={keepsNothing ? "outline" : "default"}
                  disabled={busy !== null}
                  onClick={() => void approve()}
                >
                  {busy === "approve" ? <Spinner data-icon="inline-start" /> : <CheckIcon data-icon="inline-start" />}
                  {approveLabel}
                </Button>
              ) : null}
            </div>
          </>
        )}
      </footer>
    </section>
  )
}

function TermSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </div>
  )
}

const KIND_ORDER: LinkKind[] = ["table", "column", "metric"]

function LinkList({ links, targets }: { links: GlossaryLink[]; targets: LinkTargets }) {
  if (!links.length) {
    return <p className="text-sm text-muted-foreground">Chưa liên kết. AI sẽ không biết lấy dữ liệu của thuật ngữ ở đâu.</p>
  }

  const sorted = [...links].sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
  return (
    <ul className="flex flex-col divide-y overflow-hidden rounded-lg border">
      {sorted.map((link) => {
        const target = targets.resolve(link)
        const { icon: Icon, label: kindLabel } = LINK_KINDS[link.kind]
        return (
          <li key={linkKey(link)}>
            {target ? (
              <Link
                href={target.href}
                className={cn(
                  "grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2 outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
                  target.inactive && "opacity-60",
                )}
              >
                <Icon aria-hidden className="size-4 text-muted-foreground" />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-sm">{target.label}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">{target.detail}</span>
                </span>
                <span className="text-xs text-muted-foreground">{target.inactive ? "Đã gỡ" : kindLabel}</span>
              </Link>
            ) : (
              <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2">
                <Icon aria-hidden className="size-4 text-muted-foreground" />
                {targets.columnsLoading && link.kind === "column" ? (
                  <Skeleton className="h-8 w-40" />
                ) : (
                  <span className="text-sm text-muted-foreground">Không đọc được tên</span>
                )}
                <span className="text-xs text-muted-foreground">{kindLabel}</span>
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
