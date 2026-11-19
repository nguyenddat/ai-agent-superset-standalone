"use client"

import { useMemo } from "react"

import { Combobox, type ComboboxOption } from "@/components/combobox"
import { cn } from "@/lib/utils"

import { useBusinessModel } from "./api"

// How glossary terms, expert rules and metrics name the business domains they belong to.
export type DomainRef = { id: string; name: string; color: string | null }

export const NO_DOMAIN = "Chưa phân miền"

export function DomainDot({ color, className }: { color: string | null; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2.5 shrink-0 rounded-full", className)}
      style={{ background: color ?? "var(--muted-foreground)" }}
    />
  )
}

export function DomainBadges({ domains, empty = NO_DOMAIN }: { domains: DomainRef[]; empty?: string }) {
  if (!domains.length) return <span className="text-sm text-muted-foreground">{empty}</span>
  return (
    <span className="flex flex-wrap gap-1.5">
      {domains.map((domain) => (
        <span key={domain.id} className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs">
          <DomainDot color={domain.color} />
          {domain.name}
        </span>
      ))}
    </span>
  )
}

export const domainNames = (domains: DomainRef[]) => domains.map((domain) => domain.name)

export const sameDomains = (domains: DomainRef[], ids: string[]) =>
  domains.length === ids.length && domains.every((domain) => ids.includes(domain.id))

// An item in several domains is listed under each of them; items without one come last.
export function groupByDomain<T>(items: T[], domainsOf: (item: T) => DomainRef[]) {
  const groups = new Map<string, { domain: DomainRef | null; items: T[] }>()
  for (const item of items) {
    const domains = domainsOf(item)
    for (const domain of domains.length ? domains : [null]) {
      const key = domain?.id ?? ""
      const group = groups.get(key) ?? { domain, items: [] }
      group.items.push(item)
      groups.set(key, group)
    }
  }
  return [...groups.values()].sort((a, b) =>
    a.domain === null ? 1 : b.domain === null ? -1 : a.domain.name.localeCompare(b.domain.name, "vi"),
  )
}

const option = (domain: DomainRef): ComboboxOption => ({
  value: domain.id,
  label: domain.name,
  icon: <DomainDot color={domain.color} />,
})

// Domains come only from the semantic model; they are created and edited in the Mô hình tab.
export function DomainPicker({
  connectionId,
  value,
  onChange,
  disabled,
}: {
  connectionId: string
  value: string[]
  onChange: (ids: string[]) => void
  disabled?: boolean
}) {
  const { data, isLoading } = useBusinessModel(connectionId)
  const options = useMemo(
    () => [...(data?.domains ?? [])].sort((a, b) => a.name.localeCompare(b.name, "vi")).map(option),
    [data],
  )
  const byId = new Map(options.map((item) => [item.value, item]))
  const selected = value.map((id) => byId.get(id) ?? { value: id, label: isLoading ? "Đang tải…" : "Miền đã bị xóa" })

  return (
    <Combobox
      multiple
      label="Miền nghiệp vụ"
      placeholder="Chưa thuộc miền nào"
      searchPlaceholder="Tìm miền nghiệp vụ"
      options={options}
      value={selected}
      onValueChange={(items) => onChange(items.map((item) => item.value))}
      emptyMessage={(query) =>
        query ? `Không thấy miền “${query}”` : "Chưa có miền nghiệp vụ; tạo miền ở tab Mô hình"
      }
      disabled={disabled}
      max={50}
    />
  )
}
