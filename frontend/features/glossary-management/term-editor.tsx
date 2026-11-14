"use client"

import { useMemo, useState } from "react"
import { CircleXIcon, FolderIcon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { Combobox, type ComboboxOption } from "@/components/combobox"
import { TagInput } from "@/components/tag-input"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"

import { createTerm, saveDraft } from "./api"
import { foldName, linkKey, normalizeName, parseLinkKey, sameLinks, sameSynonyms } from "./labels"
import { LINK_KINDS, type LinkTargets } from "./link-targets"
import type { GlossaryCreate, GlossaryLink, GlossaryTerm } from "./types"

type TermEditorProps = {
  connectionId: string
  terms: GlossaryTerm[]
  term: GlossaryTerm | null
  initialGroup: string | null
  targets: LinkTargets
  onClose: () => void
  onSaved: (term: GlossaryTerm) => void
  onReload: () => void
  promotion?: TermPromotion
}

// Promoting a user's own entry reuses this form: it opens with their wording and saves through the own-knowledge API.
export type TermPromotion = {
  title: string
  seed: { name: string; definition: string; links: GlossaryLink[] }
  create: (input: GlossaryCreate) => Promise<GlossaryTerm>
}

const groupOption = (name: string): ComboboxOption => ({
  value: name,
  label: name,
  icon: <FolderIcon className="size-4 text-muted-foreground" />,
})

export function TermEditor(props: TermEditorProps) {
  const { connectionId, terms, term, initialGroup, targets, onClose, onSaved, onReload, promotion } = props
  const revision = term?.current

  const [name, setName] = useState(term?.canonical_name ?? promotion?.seed.name ?? "")
  const [group, setGroup] = useState<string | null>(term ? term.group_name : initialGroup)
  const [definition, setDefinition] = useState(revision?.definition ?? promotion?.seed.definition ?? "")
  const [synonyms, setSynonyms] = useState<string[]>(revision?.synonyms ?? [])
  const [links, setLinks] = useState<string[]>((revision?.links ?? promotion?.seed.links ?? []).map(linkKey))
  // The revision this edit started from: saving on top of a newer one is a conflict, not an overwrite.
  const [baseRevision] = useState(revision?.number ?? 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [showErrors, setShowErrors] = useState(false)

  const groups = useMemo(
    () => [...new Set(terms.flatMap((item) => (item.group_name ? [item.group_name] : [])))].sort((a, b) => a.localeCompare(b, "vi")),
    [terms],
  )
  const optionByKey = useMemo(() => new Map(targets.options.map((option) => [option.value, option])), [targets.options])
  // A column chosen earlier still shows while the column list loads.
  const selectedLinks = links.map(
    (key) =>
      optionByKey.get(key) ?? {
        value: key,
        label: targets.columnsLoading ? "Đang tải…" : "Không còn tồn tại",
        group: LINK_KINDS[parseLinkKey(key).kind].label,
      },
  )

  const nameTaken =
    (!term && error?.status === 409 && error.message.startsWith("Tên thuật ngữ")) ||
    (!term && !!name.trim() && terms.some((item) => foldName(item.canonical_name) === foldName(name)))
  const issues = {
    name: !term && !normalizeName(name) ? "Đặt tên cho thuật ngữ." : null,
    definition: !definition.trim() ? "Viết định nghĩa để AI và người đọc hiểu thuật ngữ." : null,
  }
  const valid = !issues.name && !issues.definition && !nameTaken
  const conflict = !!term && error?.status === 409

  async function save() {
    setShowErrors(true)
    if (!valid) return
    const content = {
      definition: definition.trim(),
      synonyms,
      links: links.map(parseLinkKey),
    }
    if (
      term &&
      revision!.status !== "revoked" &&
      revision!.definition === content.definition &&
      sameSynonyms(revision!.synonyms, content.synonyms) &&
      sameLinks(revision!.links, content.links) &&
      term.group_name === group
    ) {
      toast.info("Không có thay đổi để lưu")
      onSaved(term)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const saved = term
        ? await saveDraft(connectionId, term.id, { ...content, group_name: group, expected_revision: baseRevision })
        : await (promotion?.create ?? createTerm)({
            ...content,
            connection_id: connectionId,
            canonical_name: normalizeName(name),
            group_name: group,
          })
      if (!promotion) {
        toast.success(term ? "Đã lưu bản nháp" : "Đã tạo thuật ngữ", {
          description: `${saved.canonical_name} đang chờ duyệt.`,
        })
      }
      onSaved(saved)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError(0, "Không lưu được thuật ngữ."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label={term ? "Sửa thuật ngữ" : "Thêm thuật ngữ"} className="flex size-full min-h-0 flex-col bg-background">
      <header className="flex items-start justify-between gap-3 border-b px-5 py-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="truncate text-base font-medium">
            {promotion?.title ?? (term ? `Sửa ${term.canonical_name}` : "Thêm thuật ngữ")}
          </h2>
          <p className="text-sm text-muted-foreground">
            {promotion
              ? "Điền sẵn từ cách hiểu của người dùng. Hãy sửa cho đúng chuẩn của kho trước khi lưu."
              : "Lưu sẽ tạo bản nháp. AI chỉ dùng thuật ngữ sau khi được duyệt."}
          </p>
        </div>
        <Button variant="ghost" size="icon-sm" aria-label="Đóng" onClick={onClose}>
          <XIcon />
        </Button>
      </header>

      <ScrollArea className="min-h-0 flex-1">
        <form
          id="term-form"
          className="flex flex-col gap-6 px-5 py-5"
          onSubmit={(event) => {
            event.preventDefault()
            void save()
          }}
        >
          <FieldGroup>
            {term ? null : (
              <Field data-invalid={(nameTaken || (showErrors && !!issues.name)) || undefined}>
                <FieldLabel htmlFor="term-name">Tên thuật ngữ</FieldLabel>
                <Input
                  id="term-name"
                  maxLength={255}
                  placeholder="VD: Doanh thu thuần"
                  aria-invalid={(nameTaken || (showErrors && !!issues.name)) || undefined}
                  value={name}
                  onChange={(event) => {
                    setName(event.target.value)
                    if (error?.status === 409) setError(null)
                  }}
                />
                {nameTaken ? (
                  <FieldError>Kết nối này đã có thuật ngữ cùng tên.</FieldError>
                ) : showErrors && issues.name ? (
                  <FieldError>{issues.name}</FieldError>
                ) : (
                  <FieldDescription>Tên chuẩn mọi người thống nhất dùng. Không đổi được sau khi tạo.</FieldDescription>
                )}
              </Field>
            )}

            <Field>
              <FieldLabel>Nhóm</FieldLabel>
              <Combobox
                label="Nhóm"
                placeholder="Không thuộc nhóm nào"
                searchPlaceholder="Tìm hoặc tạo nhóm"
                options={groups.map(groupOption)}
                value={group ? groupOption(group) : null}
                onValueChange={(option) => setGroup(option ? normalizeName(option.value) || null : null)}
                onCreate={(query) => groupOption(normalizeName(query))}
                createLabel={(query) => `Tạo nhóm “${normalizeName(query)}”`}
                emptyMessage={() => "Chưa có nhóm nào"}
                clearable
              />
              <FieldDescription>Gom các thuật ngữ cùng lĩnh vực, như Kinh doanh hay Kho vận.</FieldDescription>
            </Field>

            <Field data-invalid={(showErrors && !!issues.definition) || undefined}>
              <FieldLabel htmlFor="term-definition">Định nghĩa</FieldLabel>
              <Textarea
                id="term-definition"
                rows={5}
                maxLength={10000}
                className="max-h-80"
                placeholder="VD: Tổng giá trị đơn hàng đã giao, trừ chiết khấu và hàng trả lại."
                aria-invalid={(showErrors && !!issues.definition) || undefined}
                value={definition}
                onChange={(event) => setDefinition(event.target.value)}
              />
              {showErrors && issues.definition ? (
                <FieldError>{issues.definition}</FieldError>
              ) : (
                <FieldDescription>Nói rõ cách tính và phạm vi, để không ai hiểu theo hai cách.</FieldDescription>
              )}
            </Field>

            <Field>
              <FieldLabel>Từ đồng nghĩa</FieldLabel>
              <TagInput
                label="Từ đồng nghĩa"
                placeholder="Tên khác người dùng hay gọi, ngăn cách bằng dấu phẩy"
                max={50}
                value={synonyms.map((synonym) => ({ id: synonym, value: synonym }))}
                onValueChange={(tags) => setSynonyms(tags.filter((tag) => !tag.error).map((tag) => normalizeName(tag.value)))}
                validate={(value) => {
                  if (normalizeName(value).length > 255) return "Tối đa 255 ký tự."
                  const folded = foldName(value)
                  if (folded === foldName(term?.canonical_name ?? name)) return "Trùng tên thuật ngữ."
                  if (synonyms.some((synonym) => synonym !== value && foldName(synonym) === folded)) return "Đã có từ này."
                  return null
                }}
              />
              <FieldDescription>Câu hỏi dùng những từ này cũng được hiểu là thuật ngữ trên.</FieldDescription>
            </Field>

            <Field>
              <FieldLabel>Liên kết dữ liệu</FieldLabel>
              <Combobox
                multiple
                label="Liên kết dữ liệu"
                placeholder="Chọn bảng, cột hoặc metric"
                searchPlaceholder="Tìm bảng, cột hoặc metric"
                options={targets.options}
                value={selectedLinks}
                onValueChange={(options) => setLinks(options.map((option) => option.value))}
                emptyMessage={(query) => (query ? `Không thấy “${query}”` : "Chưa có bảng hoặc metric")}
                max={100}
                width={380}
              />
              <FieldDescription>
                {targets.columnsLoading
                  ? "Đang tải danh sách cột…"
                  : targets.columnsError
                    ? `Không tải được danh sách cột: ${targets.columnsError.message}`
                    : "Nơi dữ liệu của thuật ngữ nằm, để AI biết truy vấn bảng, cột hay metric nào."}
              </FieldDescription>
            </Field>
          </FieldGroup>

          {conflict ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertTitle>Thuật ngữ vừa được thay đổi ở nơi khác</AlertTitle>
              <AlertDescription>Tải lại để sửa trên bản mới nhất. Nội dung bạn đang nhập sẽ bị bỏ.</AlertDescription>
              <AlertAction>
                <Button type="button" size="sm" variant="outline" onClick={onReload}>
                  Tải lại
                </Button>
              </AlertAction>
            </Alert>
          ) : error && !nameTaken ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </ScrollArea>

      <footer className="flex items-center justify-end gap-2 border-t px-5 py-3">
        <Button type="button" variant="ghost" onClick={onClose}>
          Hủy
        </Button>
        <Button type="submit" form="term-form" disabled={busy || conflict}>
          {busy ? <Spinner data-icon="inline-start" /> : null}
          {promotion ? "Đưa vào kho" : term ? "Lưu bản nháp" : "Tạo thuật ngữ"}
        </Button>
      </footer>
    </section>
  )
}
