"use client"

import { useMemo, useState } from "react"
import { CheckIcon, Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { ApiError } from "@/lib/api"

import { createDomain, deleteDomain, updateDomain } from "./api"
import { DOMAIN_COLORS } from "./venn-layout"
import type { BusinessDomain, ModelTable } from "./types"

type DomainDialogProps = {
  open: boolean
  domain: BusinessDomain | null
  tables: ModelTable[]
  usedColors: string[]
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}

export function DomainDialog({ open, domain, onOpenChange, ...props }: DomainDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{domain ? "Sửa miền nghiệp vụ" : "Thêm miền nghiệp vụ"}</DialogTitle>
          <DialogDescription>
            Gom các bảng cùng phục vụ một nghiệp vụ. Một bảng có thể thuộc nhiều miền.
          </DialogDescription>
        </DialogHeader>
        {open ? <DomainForm key={domain?.id ?? "new"} domain={domain} onClose={() => onOpenChange(false)} {...props} /> : null}
      </DialogContent>
    </Dialog>
  )
}

type DomainFormProps = Omit<DomainDialogProps, "open" | "onOpenChange"> & { onClose: () => void }

function DomainForm({ domain, tables, usedColors, onClose, onSaved }: DomainFormProps) {
  const [name, setName] = useState(domain?.name ?? "")
  const [description, setDescription] = useState(domain?.description ?? "")
  const [color, setColor] = useState(
    domain?.color ?? DOMAIN_COLORS.find((item) => !usedColors.includes(item)) ?? DOMAIN_COLORS[0],
  )
  const [selected, setSelected] = useState(() => new Set(domain?.table_ids ?? []))
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  const schemas = useMemo(() => {
    const groups = new Map<string, ModelTable[]>()
    for (const table of tables) groups.set(table.schema_name, [...(groups.get(table.schema_name) ?? []), table])
    return [...groups]
  }, [tables])
  const nameTaken = error?.status === 409

  const toggle = (tableId: string) =>
    setSelected((current) => {
      const next = new Set(current)
      if (!next.delete(tableId)) next.add(tableId)
      return next
    })

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true)
    setError(null)
    try {
      await action()
      toast.success(message)
      onSaved()
      onClose()
    } catch (e) {
      const apiError = e instanceof ApiError ? e : new ApiError(0, String(e))
      if (apiError.status === 409) setError(apiError)
      else toast.error(apiError.message)
    } finally {
      setBusy(false)
    }
  }

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    const input = {
      name: name.trim(),
      description: description.trim() || null,
      color,
      table_ids: [...selected],
    }
    const connectionTables = new Set(tables.map((table) => table.table_id))
    void run(
      () => (domain ? updateDomain(domain.id, input, connectionTables) : createDomain(input)),
      domain ? `Đã cập nhật miền "${input.name}".` : `Đã thêm miền "${input.name}".`,
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <FieldGroup>
        <Field data-invalid={nameTaken || undefined}>
          <FieldLabel htmlFor="domain-name">Tên miền</FieldLabel>
          <Input
            id="domain-name"
            value={name}
            maxLength={255}
            required
            autoFocus
            aria-invalid={nameTaken || undefined}
            placeholder="Ví dụ: Bán hàng"
            onChange={(event) => setName(event.target.value)}
          />
          {nameTaken ? <FieldError>{error.message}</FieldError> : null}
        </Field>
        <Field>
          <FieldLabel htmlFor="domain-description">Mô tả</FieldLabel>
          <Textarea
            id="domain-description"
            value={description}
            maxLength={2000}
            rows={2}
            placeholder="Nghiệp vụ này trả lời những câu hỏi gì?"
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel>Màu</FieldLabel>
          <ToggleGroup
            type="single"
            value={color}
            onValueChange={(value) => value && setColor(value)}
            spacing={1}
            className="flex-wrap"
          >
            {DOMAIN_COLORS.map((item) => (
              <ToggleGroupItem key={item} value={item} aria-label={item} className="size-8 p-0">
                <span
                  className="flex size-5 items-center justify-center rounded-full text-white"
                  style={{ background: item }}
                >
                  {item === color ? <CheckIcon className="size-3" /> : null}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        <Field>
          <div className="flex items-baseline justify-between">
            <FieldLabel>Bảng thuộc miền</FieldLabel>
            <span className="text-xs text-muted-foreground tabular-nums">Đã chọn {selected.size}</span>
          </div>
          <Command className="rounded-lg border">
            <CommandInput placeholder="Tìm theo tên bảng" />
            <CommandList className="max-h-64">
              <CommandEmpty>Không có bảng phù hợp.</CommandEmpty>
              {schemas.map(([schema, items]) => (
                <CommandGroup key={schema} heading={schema}>
                  {items.map((table) => (
                    <CommandItem
                      key={table.table_id}
                      value={`${table.display_name} ${table.schema_name}.${table.table_name} ${table.table_id}`}
                      onSelect={() => toggle(table.table_id)}
                    >
                      <Checkbox checked={selected.has(table.table_id)} tabIndex={-1} className="pointer-events-none" />
                      <span className="truncate">{table.display_name}</span>
                      {table.display_name !== table.table_name ? (
                        <span className="ml-auto truncate font-mono text-xs text-muted-foreground">{table.table_name}</span>
                      ) : null}
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
          <FieldDescription>Bảng chưa có từ điển sẽ được tạo từ điển mặc định khi lưu.</FieldDescription>
        </Field>
      </FieldGroup>

      <DialogFooter className="sm:justify-between">
        {domain ? (
          confirmDelete ? (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Xóa miền? Bảng không bị xóa.</span>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={busy}
                onClick={() => void run(() => deleteDomain(domain.id), `Đã xóa miền "${domain.name}".`)}
              >
                Xóa
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>
                Không
              </Button>
            </div>
          ) : (
            <Button type="button" variant="ghost" className="text-destructive" onClick={() => setConfirmDelete(true)}>
              <Trash2Icon data-icon="inline-start" />
              Xóa miền
            </Button>
          )
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" disabled={busy || !name.trim()}>
            {busy ? <Spinner data-icon="inline-start" /> : null}
            {domain ? "Lưu thay đổi" : "Thêm miền"}
          </Button>
        </div>
      </DialogFooter>
    </form>
  )
}
