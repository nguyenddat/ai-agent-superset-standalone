import { Badge } from "@/components/ui/badge"

import type { DatabaseConnection } from "./types"

export const dateFormat = new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" })

export function describe(connection: DatabaseConnection) {
  return connection.driver ? `${connection.dialect} · ${connection.driver}` : connection.dialect
}

export function StatusBadge({ active }: { active: boolean }) {
  return <Badge variant={active ? "secondary" : "outline"}>{active ? "Đang hoạt động" : "Tạm dừng"}</Badge>
}
