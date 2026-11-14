"use client"

import { useCallback, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { CircleXIcon, RefreshCwIcon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"

import { useConnectionId } from "../database-connections/detail/connection-layout"
import { useDictionarySummary } from "./api"
import { DictionaryEditor } from "./dictionary-editor"
import { TablePicker } from "./table-picker"

export function DictionaryWorkspace() {
  const connectionId = useConnectionId()
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const { data: summary, error } = useDictionarySummary(connectionId)
  const [dirty, setDirty] = useState(false)
  const [pendingTableId, setPendingTableId] = useState<string | null>(null)

  const allTables = summary?.schemas.flatMap((schema) => schema.tables) ?? []
  const requested = searchParams.get("table")
  const current = allTables.find((table) => table.table_id === requested) ?? allTables[0]

  const openTable = useCallback(
    (nextTableId: string) => {
      setDirty(false)
      router.replace(`${pathname}?table=${nextTableId}`, { scroll: false })
    },
    [pathname, router],
  )
  const selectTable = (nextTableId: string) => {
    if (nextTableId === current?.table_id) return
    if (dirty) setPendingTableId(nextTableId)
    else openTable(nextTableId)
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <CircleXIcon />
        <AlertDescription>{error.message}</AlertDescription>
      </Alert>
    )
  }

  if (!summary) {
    return (
      <Card size="sm">
        <CardContent className="flex flex-col gap-3">
          <Skeleton className="h-8 w-64" />
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-12" />
          ))}
        </CardContent>
      </Card>
    )
  }

  if (!current) {
    return (
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <RefreshCwIcon />
          </EmptyMedia>
          <EmptyTitle>Chưa có bảng để mô tả</EmptyTitle>
          <EmptyDescription>Bấm &quot;Đồng bộ metadata&quot; ở đầu trang để đọc cấu trúc database nguồn.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <>
      <DictionaryEditor
        key={current.table_id}
        tableId={current.table_id}
        picker={(label) => (
          <TablePicker summary={summary} tableId={current.table_id} label={label} onSelect={selectTable} />
        )}
        fallbackLabel={current.display_name}
        catalogTables={allTables.filter((table) => table.layout === "indicator_catalog")}
        onDirtyChange={setDirty}
      />

      <AlertDialog open={pendingTableId !== null} onOpenChange={(open) => !open && setPendingTableId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Bỏ thay đổi chưa lưu?</AlertDialogTitle>
            <AlertDialogDescription>
              Bảng hiện tại còn thay đổi chưa lưu. Chuyển sang bảng khác sẽ bỏ các thay đổi đó.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Ở lại</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (pendingTableId) openTable(pendingTableId)
                setPendingTableId(null)
              }}
            >
              Bỏ thay đổi
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
