"use client"

import { useCallback, useMemo, useState } from "react"
import { CircleXIcon, PlusIcon } from "lucide-react"
import { toast } from "sonner"

import { EmptyState } from "@/components/empty-state"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

import { useConnectionId } from "../database-connections/detail/connection-layout"
import { refreshModel, updateDomain, updateModel, useBusinessModel } from "./api"
import { DomainCanvas, regionNodeId, type CanvasFocus, type ColoredDomain } from "./domain-canvas"
import { DomainDialog } from "./domain-dialog"
import { ModelSidebar } from "./model-sidebar"
import type { BusinessDomain, BusinessModel } from "./types"
import { domainColor } from "./venn-layout"

const FRAME = "grid min-h-[560px] gap-3 lg:h-[calc(100svh-12.75rem)] lg:grid-cols-[17rem_minmax(0,1fr)]"

export function ModelWorkspace() {
  const connectionId = useConnectionId()
  const { data: model, error } = useBusinessModel(connectionId)

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!model) {
    return (
      <div className={FRAME}>
        <Skeleton className="hidden rounded-xl lg:block" />
        <Skeleton className="rounded-xl" />
      </div>
    )
  }

  if (model.tables.length === 0) {
    return (
      <div className="rounded-xl border">
        <EmptyState
          scene="chart"
          title="Chưa có bảng để mô hình hóa"
          description="Đồng bộ metadata của kết nối để lấy danh sách bảng, rồi gom chúng vào các miền nghiệp vụ."
        />
      </div>
    )
  }

  return <ModelEditor connectionId={connectionId} model={model} />
}

function ModelEditor({ connectionId, model }: { connectionId: string; model: BusinessModel }) {
  const [focus, setFocus] = useState<CanvasFocus | null>(null)
  const [dialog, setDialog] = useState<{ open: boolean; domain: BusinessDomain | null }>({ open: false, domain: null })

  const domains = useMemo<ColoredDomain[]>(
    () => model.domains.map((domain, index) => ({ domain, color: domainColor(domain, index) })),
    [model.domains],
  )
  const tableIds = useMemo(() => new Set(model.tables.map((table) => table.table_id)), [model.tables])
  const tableName = (tableId: string) => model.tables.find((table) => table.table_id === tableId)?.display_name ?? ""

  // Writes the members of several domains at once: the canvas shows the change at once and goes back if a write fails.
  async function applyMembers(members: Map<string, string[]>) {
    const written = new Map(model.domains.map((domain) => [domain.id, domain]))
    await updateModel(connectionId, (current) => ({
      ...current,
      domains: current.domains.map((domain) =>
        members.has(domain.id) ? { ...domain, table_ids: members.get(domain.id)! } : domain,
      ),
    }))
    try {
      await Promise.all(
        [...members].map(([domainId, table_ids]) => {
          const { name, description, color } = written.get(domainId)!
          return updateDomain(domainId, { name, description, color, table_ids }, tableIds)
        }),
      )
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      await refreshModel(connectionId)
    }
  }

  function setTableDomains(tableId: string, domainIds: string[]) {
    const wanted = new Set(domainIds)
    const changed = model.domains.filter((domain) => domain.table_ids.includes(tableId) !== wanted.has(domain.id))
    if (changed.length === 0) return
    const members = new Map(
      changed.map((domain) => [
        domain.id,
        wanted.has(domain.id) ? [...domain.table_ids, tableId] : domain.table_ids.filter((id) => id !== tableId),
      ]),
    )
    const before = new Map(changed.map((domain) => [domain.id, domain.table_ids]))
    const names = model.domains.filter((domain) => wanted.has(domain.id)).map((domain) => domain.name)
    void applyMembers(members)
    toast.success(
      names.length > 0
        ? `"${tableName(tableId)}" giờ thuộc ${names.map((name) => `"${name}"`).join(" và ")}.`
        : `Đã bỏ "${tableName(tableId)}" khỏi mọi miền.`,
      { action: { label: "Hoàn tác", onClick: () => void applyMembers(before) } },
    )
  }

  const editDomain = useCallback((domain: BusinessDomain) => setDialog({ open: true, domain }), [])
  const createDomain = () => setDialog({ open: true, domain: null })
  const domainById = (domainId: string) => model.domains.find((domain) => domain.id === domainId)!

  return (
    <div className={FRAME}>
      <ModelSidebar
        domains={domains}
        tables={model.tables}
        onFocus={(nodeIds) => setFocus({ nodeIds, nonce: Date.now() })}
        onFocusDomain={(domainId) => setFocus({ nodeIds: [regionNodeId(domainId)], nonce: Date.now() })}
        onCreateDomain={createDomain}
        onEditDomain={(domainId) => editDomain(domainById(domainId))}
      />

      <div className="relative min-h-[560px] overflow-hidden rounded-xl border bg-background">
        {domains.length > 0 ? (
          <DomainCanvas
            connectionId={connectionId}
            model={model}
            domains={domains}
            focus={focus}
            onEditDomain={editDomain}
            onSetDomains={setTableDomains}
          />
        ) : (
          <div className="flex size-full items-center justify-center">
            <EmptyState
              scene="inbox"
              title="Chưa có miền nghiệp vụ"
              description="Tạo miền đầu tiên rồi kéo các bảng ở cột bên trái vào vùng của miền."
              action={
                <Button onClick={createDomain}>
                  <PlusIcon data-icon="inline-start" />
                  Thêm miền nghiệp vụ
                </Button>
              }
            />
          </div>
        )}
        {domains.length > 0 ? (
          <div className="pointer-events-none absolute inset-x-3 top-3 flex items-start justify-between gap-3">
            <p className="hidden rounded-lg bg-background/80 px-2.5 py-1.5 text-xs text-muted-foreground backdrop-blur md:block">
              Kéo bảng vào vùng của miền, thả vào chỗ giao nhau để thuộc cả hai miền · nhấp đúp để mở từ điển
            </p>
            <div className="pointer-events-auto ml-auto flex items-center gap-2">
              <Button size="sm" onClick={createDomain}>
                <PlusIcon data-icon="inline-start" />
                Thêm miền
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <DomainDialog
        open={dialog.open}
        domain={dialog.domain}
        tables={model.tables}
        usedColors={domains.map((item) => item.color)}
        onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
        onSaved={() => void refreshModel(connectionId)}
      />
    </div>
  )
}
