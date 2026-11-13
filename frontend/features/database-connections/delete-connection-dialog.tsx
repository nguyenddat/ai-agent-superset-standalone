"use client"

import { useState } from "react"
import { Trash2Icon } from "lucide-react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Spinner } from "@/components/ui/spinner"

import { deleteConnection } from "./api"
import type { DatabaseConnection } from "./types"

export function DeleteConnectionDialog({
  connection,
  onOpenChange,
  onDeleted,
}: {
  connection: DatabaseConnection | null
  onOpenChange: (open: boolean) => void
  onDeleted?: () => void
}) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete(event: React.MouseEvent) {
    event.preventDefault()
    if (!connection) return
    setDeleting(true)
    try {
      await deleteConnection(connection.id)
      toast.success(`Đã xóa kết nối "${connection.name}".`)
      onOpenChange(false)
      onDeleted?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <AlertDialog open={!!connection} onOpenChange={onOpenChange}>
      <AlertDialogContent size="sm">
        <AlertDialogHeader>
          <AlertDialogMedia>
            <Trash2Icon />
          </AlertDialogMedia>
          <AlertDialogTitle>Xóa kết nối &quot;{connection?.name}&quot;?</AlertDialogTitle>
          <AlertDialogDescription>
            Toàn bộ schema, bảng và cột đã đồng bộ của kết nối này cũng bị xóa. Database nguồn không bị ảnh hưởng.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Hủy</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={deleting} onClick={handleDelete}>
            {deleting && <Spinner data-icon="inline-start" />}
            Xóa kết nối
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
