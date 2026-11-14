import type { DependencyRole, TransformationOrigin } from "./types"

export const ROLES: { value: DependencyRole; label: string; hint: string; needsTarget: boolean }[] = [
  { value: "value", label: "Giá trị", hint: "Cột nguồn cung cấp giá trị cho cột đích.", needsTarget: true },
  { value: "group", label: "Nhóm", hint: "Cột dùng trong GROUP BY, quyết định mức tổng hợp.", needsTarget: false },
  { value: "join", label: "Join", hint: "Cột trong điều kiện JOIN, ảnh hưởng tập bản ghi.", needsTarget: false },
  { value: "filter", label: "Lọc", hint: "Cột trong WHERE/HAVING, ảnh hưởng tập bản ghi.", needsTarget: false },
]

export const roleLabel = (role: DependencyRole) => ROLES.find((item) => item.value === role)!.label

// Colour and dash pattern both tell the roles apart, so the legend still reads for colour-blind viewers.
export const ROLE_STROKE: Record<DependencyRole, { color: string; dash?: string }> = {
  value: { color: "var(--chart-1)" },
  group: { color: "var(--chart-2)", dash: "7 4" },
  join: { color: "var(--muted-foreground)", dash: "2 4" },
  filter: { color: "var(--muted-foreground)", dash: "10 4 2 4" },
}

export const ORIGINS: { value: TransformationOrigin; label: string; hint: string }[] = [
  { value: "manual", label: "Thủ công", hint: "Khai báo tay, không kèm SQL bắt buộc." },
  { value: "sql_job", label: "SQL job", hint: "SQL của ETL hoặc job tạo bảng đích." },
  { value: "view_sql", label: "SQL của view", hint: "Định nghĩa của view/materialized view đích." },
]

export const originLabel = (origin: TransformationOrigin | "manual_edge") =>
  origin === "manual_edge" ? "Cạnh khai báo ở Mô hình" : ORIGINS.find((item) => item.value === origin)!.label

export const isView = (tableType: string) => /VIEW/i.test(tableType)
