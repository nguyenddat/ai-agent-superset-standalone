"use client"

import { useState } from "react"
import Link from "next/link"
import { ArchiveIcon, CircleXIcon, DatabaseZapIcon, RefreshCwIcon, TriangleAlertIcon, Undo2Icon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/badge"
import { SegmentedControl } from "@/components/segmented-control"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"

import type { ModelTable } from "../business-model/types"
import { foldName } from "../glossary-management/labels"
import type { Findings } from "./analysis"
import { reviewEntry } from "./api"
import { KIND_ORDER, KINDS, REVIEW_STATES, formatTime } from "./labels"
import { Overlap } from "./overlap"
import { useReviewer } from "./reviewer"
import type { KnowledgeKind, OwnEntry, ReviewAction } from "./types"

export type PromoteRequest = { kind: KnowledgeKind; approve: boolean; note: string | null; reviewer: string }

type Mode = ReviewAction | "promote" | null

export function EntryDetail({
  connectionId,
  entry,
  findings,
  table,
  onClose,
  onOpenEntry,
  onPromote,
  onReload,
}: {
  connectionId: string
  entry: OwnEntry
  findings: Findings
  table: ModelTable | undefined
  onClose: () => void
  onOpenEntry: (id: string) => void
  onPromote: (request: PromoteRequest) => void
  onReload: () => void
}) {
  const status = REVIEW_STATES[entry.review_status]
  const kind = KINDS[entry.kind]
  const [mode, setMode] = useState<Mode>(null)

  return (
    <section aria-label={`Tri thức riêng ${entry.name}`} className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h2 className="truncate text-base font-medium">{entry.name}</h2>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge tone={status.tone} dot title={status.hint}>
              {status.label}
            </Badge>
            <span className="inline-flex items-center gap-1">
              <kind.icon className="size-3.5" />
              {kind.label}
            </span>
            <span>·</span>
            <span className="truncate">{entry.user_id}</span>
          </div>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-6 px-5 py-5">
          <section className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Người dùng hiểu là</h3>
            <p className="rounded-lg border bg-muted/30 px-3 py-2.5 text-sm leading-relaxed">{entry.definition}</p>
            {entry.concept && foldName(entry.concept) !== foldName(entry.name) ? (
              <p className="text-xs text-muted-foreground">Khái niệm Agent hỏi: {entry.concept}</p>
            ) : null}
            <p className="text-xs text-muted-foreground">
              {entry.active_for_agent
                ? `AI đang dùng cách hiểu này khi trả lời ${entry.user_id}, sau ngữ nghĩa đã duyệt trong kho.`
                : "AI không dùng cách hiểu này nữa vì bản trong kho đang được dùng."}
            </p>
          </section>

          {entry.source_question ? (
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Câu hỏi làm phát sinh</h3>
              <blockquote className="border-l-2 pl-3 text-sm text-muted-foreground">“{entry.source_question}”</blockquote>
            </section>
          ) : null}

          <Overlap entry={entry} findings={findings} onOpenEntry={onOpenEntry} />

          {entry.reviewed_by ? (
            <section className="flex flex-col gap-1 rounded-lg border px-3 py-2.5 text-sm">
              <p>
                <span className="font-medium">{entry.reviewed_by}</span>
                <span className="text-muted-foreground"> · {formatTime(entry.reviewed_at!)}</span>
              </p>
              {entry.review_note ? <p className="text-muted-foreground">{entry.review_note}</p> : null}
            </section>
          ) : null}

          <dl className="grid grid-cols-[8rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted-foreground">Bảng ngữ cảnh</dt>
            <dd className="truncate">
              {table ? (
                <Link
                  href={`/connections/${connectionId}/dictionary?table=${table.table_id}`}
                  className="underline-offset-4 hover:underline"
                >
                  {table.display_name || table.table_name}
                </Link>
              ) : (
                <span className="text-muted-foreground">Không có</span>
              )}
            </dd>
            <dt className="text-muted-foreground">Ghi nhận</dt>
            <dd>{formatTime(entry.created_at)}</dd>
            <dt className="text-muted-foreground">Cập nhật</dt>
            <dd>
              {formatTime(entry.updated_at)} · phiên bản {entry.version}
            </dd>
          </dl>
        </div>
      </ScrollArea>

      {mode ? (
        <ActionForm
          key={mode}
          mode={mode}
          entry={entry}
          findings={findings}
          onCancel={() => setMode(null)}
          onDone={() => setMode(null)}
          onPromote={onPromote}
          onReload={onReload}
        />
      ) : (
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t px-5 py-3">
          {entry.review_status === "pending" ? null : (
            <Button variant="ghost" className="mr-auto" onClick={() => setMode("reopen")}>
              <Undo2Icon data-icon="inline-start" />
              Mở lại
            </Button>
          )}
          {entry.review_status === "pending" ? (
            <Button variant="outline" onClick={() => setMode("keep_own")}>
              <ArchiveIcon data-icon="inline-start" />
              Giữ riêng
            </Button>
          ) : null}
          {entry.review_status === "promoted" ? null : (
            <Button onClick={() => setMode("promote")}>
              <DatabaseZapIcon data-icon="inline-start" />
              Đưa vào kho
            </Button>
          )}
        </footer>
      )}
    </section>
  )
}

// Fills the note with what the reviewer is most likely deciding about, so the audit trail says why.
function suggestedNote(findings: Findings) {
  const live = findings.system.find((item) => item.state !== "revoked" && item.state !== "inactive")
  if (!live) return ""
  const what = `${KINDS[live.kind].label.toLowerCase()} “${live.name}”`
  return live.verdict === "different" ? `Khác với ${what} trong kho; giữ làm cách hiểu riêng.` : `Kho đã có ${what}.`
}

function ActionForm({
  mode,
  entry,
  findings,
  onCancel,
  onDone,
  onPromote,
  onReload,
}: {
  mode: Exclude<Mode, null>
  entry: OwnEntry
  findings: Findings
  onCancel: () => void
  onDone: () => void
  onPromote: (request: PromoteRequest) => void
  onReload: () => void
}) {
  const [reviewer, setReviewer] = useReviewer()
  const [name, setName] = useState(reviewer)
  const [note, setNote] = useState(mode === "keep_own" ? suggestedNote(findings) : "")
  const [kind, setKind] = useState<KnowledgeKind>(entry.kind)
  const [approve, setApprove] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [showErrors, setShowErrors] = useState(false)

  const missingName = !name.trim()
  // Glossary and rule names are unique per connection, so the create step would refuse this one.
  const clash = findings.system.find(
    (item) => item.kind === kind && kind !== "metric" && item.names.some((value) => foldName(value) === foldName(entry.name)),
  )

  async function submit() {
    setShowErrors(true)
    if (missingName) return
    const reviewerId = name.trim()
    setReviewer(reviewerId)
    const trimmed = note.trim() || null
    if (mode === "promote") {
      onPromote({ kind, approve: kind !== "metric" && approve, note: trimmed, reviewer: reviewerId })
      return
    }
    setBusy(true)
    setError(null)
    try {
      await reviewEntry(entry, mode, reviewerId, trimmed)
      toast.success(mode === "keep_own" ? "Đã giữ riêng" : "Đã mở lại", {
        description:
          mode === "keep_own"
            ? `${entry.name} là cách hiểu riêng của ${entry.user_id}.`
            : `${entry.name} quay về chờ duyệt.`,
      })
      onDone()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không lưu được quyết định."))
    } finally {
      setBusy(false)
    }
  }

  const title = mode === "promote" ? "Đưa vào kho" : mode === "keep_own" ? "Giữ riêng" : "Mở lại"
  const hint =
    mode === "promote"
      ? "Bước sau mở form của kho, điền sẵn từ cách hiểu của người dùng để bạn chỉnh."
      : mode === "keep_own"
        ? "Cách hiểu vẫn chỉ dùng cho người này. AI luôn ưu tiên ngữ nghĩa trong kho trước."
        : entry.review_status === "promoted"
          ? "Mục quay về chờ duyệt. Bản ghi đã tạo trong kho vẫn giữ nguyên, hãy tự thu hồi ở tab của nó nếu cần."
          : "Mục quay về chờ duyệt để xem xét lại."

  return (
    <form
      className="flex max-h-[60%] flex-col gap-3 overflow-y-auto border-t bg-muted/20 px-5 py-4"
      onSubmit={(event) => {
        event.preventDefault()
        void submit()
      }}
    >
      <div className="flex flex-col gap-0.5">
        <h3 className="text-sm font-medium">{title}</h3>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <FieldGroup className="gap-3">
        {mode === "promote" ? (
          <>
            <Field>
              <FieldLabel>Loại bản ghi trong kho</FieldLabel>
              <SegmentedControl
                label="Loại bản ghi trong kho"
                size="sm"
                value={kind}
                onValueChange={(value) => setKind(value as KnowledgeKind)}
                options={KIND_ORDER.map((value) => ({ value, label: KINDS[value].label }))}
              />
              {kind !== entry.kind ? (
                <FieldDescription>Agent ghi nhận đây là {KINDS[entry.kind].label.toLowerCase()}.</FieldDescription>
              ) : null}
            </Field>
            {clash ? (
              <Alert>
                <TriangleAlertIcon />
                <AlertTitle>Kho đã có {KINDS[kind].label.toLowerCase()} “{clash.name}”</AlertTitle>
                <AlertDescription>
                  Tên trùng sẽ bị từ chối. Hãy đặt tên khác ở bước sau, hoặc{" "}
                  <Link href={clash.href} className="underline underline-offset-4">
                    cập nhật bản có sẵn
                  </Link>{" "}
                  rồi chọn Giữ riêng.
                </AlertDescription>
              </Alert>
            ) : null}
            {kind === "metric" ? (
              <p className="text-xs text-muted-foreground">Metric không có bước duyệt: AI dùng ngay khi bạn lưu.</p>
            ) : (
              <Field orientation="horizontal">
                <Switch id="approve-now" checked={approve} onCheckedChange={setApprove} />
                <FieldLabel htmlFor="approve-now" className="font-normal">
                  Duyệt luôn để AI dùng ngay
                </FieldLabel>
              </Field>
            )}
          </>
        ) : null}
        <Field>
          <FieldLabel htmlFor="review-note">Ghi chú</FieldLabel>
          <Textarea
            id="review-note"
            rows={2}
            maxLength={1000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Lý do, để người duyệt sau hiểu quyết định này"
          />
        </Field>
        <Field data-invalid={(showErrors && missingName) || undefined}>
          <FieldLabel htmlFor="reviewer">Người duyệt</FieldLabel>
          <Input
            id="reviewer"
            value={name}
            maxLength={255}
            aria-invalid={(showErrors && missingName) || undefined}
            onChange={(event) => setName(event.target.value)}
            placeholder="Tên hoặc email của bạn"
          />
          <FieldDescription>
            {showErrors && missingName ? "Nhập tên để ghi vào lịch sử duyệt." : "Trình duyệt này sẽ nhớ cho lần sau."}
          </FieldDescription>
        </Field>
      </FieldGroup>
      {error ? (
        <Alert variant="destructive">
          <CircleXIcon />
          <AlertTitle>{error.status === 409 ? "Mục này vừa thay đổi" : "Không lưu được"}</AlertTitle>
          <AlertDescription>
            {error.status === 409
              ? "Người dùng đã sửa lại hoặc một admin khác vừa duyệt. Tải lại để xem bản mới nhất."
              : error.message}
          </AlertDescription>
          {error.status === 409 ? (
            <AlertAction>
              <Button size="sm" variant="outline" type="button" onClick={onReload}>
                <RefreshCwIcon data-icon="inline-start" />
                Tải lại
              </Button>
            </AlertAction>
          ) : null}
        </Alert>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Hủy
        </Button>
        <Button type="submit" disabled={busy || error?.status === 409}>
          {busy ? <Spinner data-icon="inline-start" /> : null}
          {mode === "promote" ? "Tiếp tục" : title}
        </Button>
      </div>
    </form>
  )
}
