import { toast } from "sonner"

import { syncConnection } from "./api"
import type { DatabaseConnection } from "./types"

export async function syncWithToast(connection: DatabaseConnection) {
  try {
    const result = await syncConnection(connection.id)
    toast.success(`Đã đồng bộ "${connection.name}"`, {
      description: `${result.schema_count} schema · ${result.table_count} bảng và view · ${result.column_count} cột`,
    })
  } catch (e) {
    toast.error(`Không đồng bộ được "${connection.name}"`, {
      description: e instanceof Error ? e.message : String(e),
    })
  }
}
