"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { PencilIcon, Trash2Icon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Item, ItemActions, ItemContent, ItemDescription, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"

import { useConnection } from "../api"
import { ConnectionFormDialog } from "../connection-form-dialog"
import { describe, StatusBadge } from "../connection-format"
import { DeleteConnectionDialog } from "../delete-connection-dialog"
import { useConnectionId } from "./connection-layout"

export function ConnectionSettings() {
  const id = useConnectionId()
  const router = useRouter()
  const { data: connection } = useConnection(id)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (!connection) return <Skeleton className="h-64 rounded-xl" />

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>Thông tin kết nối</CardTitle>
          <CardDescription>Đổi tên, URI hoặc tạm dừng kết nối. Kết nối tạm dừng không đồng bộ được metadata.</CardDescription>
        </CardHeader>
        <CardContent>
          <Item variant="outline" size="sm">
            <ItemContent>
              <ItemTitle>{connection.name}</ItemTitle>
              <ItemDescription>{describe(connection)} · URI đã mã hóa</ItemDescription>
            </ItemContent>
            <ItemActions>
              <StatusBadge active={connection.is_active} />
            </ItemActions>
          </Item>
        </CardContent>
        <CardFooter className="justify-end">
          <Button variant="outline" onClick={() => setEditing(true)}>
            <PencilIcon data-icon="inline-start" />
            Sửa kết nối
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Xóa kết nối</CardTitle>
          <CardDescription>
            Xóa kết nối cùng toàn bộ schema, bảng và cột đã đồng bộ. Database nguồn không bị ảnh hưởng.
          </CardDescription>
        </CardHeader>
        <CardFooter className="justify-end">
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            <Trash2Icon data-icon="inline-start" />
            Xóa kết nối
          </Button>
        </CardFooter>
      </Card>

      <ConnectionFormDialog open={editing} onOpenChange={setEditing} connection={connection} />
      <DeleteConnectionDialog
        connection={deleting ? connection : null}
        onOpenChange={setDeleting}
        onDeleted={() => router.push("/")}
      />
    </div>
  )
}
