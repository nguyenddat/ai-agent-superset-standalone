"use client"

import { useState } from "react"
import { CircleXIcon, DatabaseIcon, RefreshCwIcon } from "lucide-react"
import { toast } from "sonner"

import { NumberRoll } from "@/components/number-roll"
import { StatusButton, type ActionStatus } from "@/components/status-button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"

import { useConnections } from "../database-connections/api"
import { linkSupersetDatabase, syncSuperset, useSupersetDatabases } from "./api"
import type { SupersetDatabase, SupersetSyncResult } from "./types"

const UNLINKED = "__none__"

export function SupersetDialog({
  connectionId,
  open,
  onOpenChange,
}: {
  connectionId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { data: databases, error } = useSupersetDatabases()
  const [status, setStatus] = useState<ActionStatus>("idle")
  const [result, setResult] = useState<SupersetSyncResult | null>(null)

  async function sync() {
    setStatus("pending")
    try {
      const next = await syncSuperset()
      setResult(next)
      setStatus("success")
      toast.success("Đã đồng bộ từ Superset", {
        description: `${next.metrics} metric · ${next.databases} database · ${next.users} người dùng${
          next.deactivated ? ` · ${next.deactivated} metric không còn trên Superset` : ""
        }`,
      })
    } catch (caught) {
      setStatus("error")
      toast.error("Không đồng bộ được từ Superset", {
        description: caught instanceof Error ? caught.message : String(caught),
      })
    }
  }

  const ordered = [...(databases ?? [])].sort(
    (a, b) => Number(b.connection_id === connectionId) - Number(a.connection_id === connectionId) || a.name.localeCompare(b.name),
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Metric từ Superset</DialogTitle>
          <DialogDescription>
            Lấy metric đã định nghĩa trên Superset, rồi chọn database Superset nào trỏ tới kết nối này để metric của nó
            hiện ở đây.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-col">
              <span className="text-sm font-medium">Đồng bộ</span>
              <span className="text-sm text-muted-foreground">Đọc người dùng, database và metric. Không ghi gì lên Superset.</span>
            </div>
            <StatusButton
              size="sm"
              variant="outline"
              status={status}
              icon={<RefreshCwIcon className="size-3.5" />}
              labels={{ idle: "Đồng bộ ngay", pending: "Đang đồng bộ", success: "Đã đồng bộ", error: "Thử lại" }}
              onReset={() => setStatus("idle")}
              onClick={() => {
                if (status !== "pending") void sync()
              }}
            />
          </div>
          {result ? (
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ["Metric", result.metrics],
                ["Database", result.databases],
                ["Người dùng", result.users],
                ["Không còn", result.deactivated],
              ].map(([label, value]) => (
                <div key={label} className="flex flex-col rounded-md bg-muted/50 px-2.5 py-1.5">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="text-lg font-semibold tabular-nums">
                    <NumberRoll value={value as number} from={0} />
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Database trên Superset</h3>
          {error ? (
            <Alert variant="destructive">
              <CircleXIcon />
              <AlertDescription>{error.message}</AlertDescription>
            </Alert>
          ) : !databases ? (
            <Skeleton className="h-24" />
          ) : databases.length === 0 ? (
            <Empty className="border p-6">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <DatabaseIcon />
                </EmptyMedia>
                <EmptyTitle>Chưa có database nào</EmptyTitle>
                <EmptyDescription>Đồng bộ để lấy danh sách database đã khai báo trên Superset.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="flex max-h-72 flex-col divide-y overflow-y-auto rounded-lg border">
              {ordered.map((database) => (
                <DatabaseRow key={database.id} database={database} connectionId={connectionId} />
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DatabaseRow({ database, connectionId }: { database: SupersetDatabase; connectionId: string }) {
  const { data: connections } = useConnections()
  const [saving, setSaving] = useState(false)
  const host = (() => {
    try {
      return new URL(database.source_url).host
    } catch {
      return database.source_url
    }
  })()

  async function link(value: string) {
    setSaving(true)
    try {
      await linkSupersetDatabase(database.id, value === UNLINKED ? null : value)
      const name = connections?.find((item) => item.id === value)?.name
      toast.success(name ? `Đã liên kết "${database.name}" với "${name}"` : `Đã bỏ liên kết "${database.name}"`)
    } catch (caught) {
      toast.error("Không lưu được liên kết", { description: caught instanceof Error ? caught.message : String(caught) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="grid items-center gap-2 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_12rem] sm:gap-3">
      <div className="flex min-w-0 flex-col">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-sm font-medium">{database.name}</span>
          {database.backend ? <Badge variant="outline">{database.backend}</Badge> : null}
          {database.connection_id === connectionId ? <Badge>Kết nối này</Badge> : null}
        </div>
        <span className="truncate text-xs text-muted-foreground">
          {host} · #{database.source_id}
        </span>
      </div>
      <Select value={database.connection_id ?? UNLINKED} onValueChange={(value) => void link(value)} disabled={saving}>
        <SelectTrigger size="sm" className="w-full" aria-label={`Kết nối ứng với ${database.name}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectItem value={UNLINKED}>Chưa liên kết</SelectItem>
            {connections?.map((connection) => (
              <SelectItem key={connection.id} value={connection.id}>
                {connection.name}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </li>
  )
}
