"use client"

import { useState } from "react"
import Link from "next/link"
import { useParams, usePathname } from "next/navigation"
import {
  ArrowLeftIcon,
  BookOpenIcon,
  CircleXIcon,
  DatabaseIcon,
  LayoutDashboardIcon,
  NetworkIcon,
  RefreshCwIcon,
  SettingsIcon,
  TableIcon,
  WorkflowIcon,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ApiError } from "@/lib/api"

import { useConnection } from "../api"
import { StatusBadge } from "../connection-format"
import { syncWithToast } from "../sync-with-toast"

const sections = [
  { segment: "", label: "Tổng quan", icon: LayoutDashboardIcon },
  { segment: "metadata", label: "Metadata", icon: TableIcon },
  { segment: "dictionary", label: "Từ điển", icon: BookOpenIcon },
  { segment: "model", label: "Mô hình", icon: NetworkIcon },
  { segment: "lineage", label: "Dòng dữ liệu", icon: WorkflowIcon },
  { segment: "settings", label: "Cài đặt", icon: SettingsIcon },
]

export function useConnectionId() {
  return useParams<{ id: string }>().id
}

export function ConnectionLayout({ children }: { children: React.ReactNode }) {
  const id = useConnectionId()
  const pathname = usePathname()
  const { data: connection, error } = useConnection(id)
  const [syncing, setSyncing] = useState(false)
  const base = `/connections/${id}`
  const active = sections.find((s) => s.segment && pathname.startsWith(`${base}/${s.segment}`))?.segment ?? ""

  const back = (
    <Button variant="ghost" size="sm" className="-ml-2 self-start" asChild>
      <Link href="/">
        <ArrowLeftIcon data-icon="inline-start" />
        Tất cả kết nối
      </Link>
    </Button>
  )

  if (error instanceof ApiError && error.status === 404) {
    return (
      <>
        {back}
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <DatabaseIcon />
            </EmptyMedia>
            <EmptyTitle>Không tìm thấy kết nối</EmptyTitle>
            <EmptyDescription>Kết nối này không tồn tại hoặc đã bị xóa.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button variant="outline" asChild>
              <Link href="/">Về danh sách kết nối</Link>
            </Button>
          </EmptyContent>
        </Empty>
      </>
    )
  }

  if (error) {
    return (
      <>
        {back}
        <Alert variant="destructive">
          <CircleXIcon />
          <AlertTitle>Không tải được kết nối</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      </>
    )
  }

  return (
    <>
      <div className="flex flex-col gap-1">
        {back}
        <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          {connection ? (
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="truncate text-2xl font-semibold tracking-tight">{connection.name}</h1>
                <StatusBadge active={connection.is_active} />
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <Skeleton className="h-8 w-64" />
            </div>
          )}
          <Button
            variant="outline"
            className="shrink-0"
            disabled={!connection?.is_active || syncing}
            onClick={async () => {
              if (!connection) return
              setSyncing(true)
              await syncWithToast(connection)
              setSyncing(false)
            }}
          >
            {syncing ? <Spinner data-icon="inline-start" /> : <RefreshCwIcon data-icon="inline-start" />}
            Đồng bộ metadata
          </Button>
        </header>
        <nav aria-label="Mục của kết nối" className="mt-2 overflow-x-auto overflow-y-hidden border-b">
          <Tabs value={active}>
            <TabsList variant="line" className="h-10">
              {sections.map(({ segment, label, icon: Icon }) => (
                <TabsTrigger key={segment} value={segment} asChild>
                  <Link href={segment ? `${base}/${segment}` : base}>
                    <Icon />
                    {label}
                  </Link>
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </nav>
      </div>

      {children}
    </>
  )
}
