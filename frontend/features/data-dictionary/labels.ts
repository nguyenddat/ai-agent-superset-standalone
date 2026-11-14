import type {
  ColumnAggregation,
  IndicatorAggregationValue,
  SemanticRole,
  TableKind,
  TableLayout,
  TemporalKind,
  TimeGrainValue,
} from "./types"

export const semanticRoles: { value: SemanticRole; label: string; description: string }[] = [
  { value: "key", label: "Khóa", description: "Định danh bản ghi hoặc tham chiếu sang bảng khác" },
  { value: "measure", label: "Số đo", description: "Giá trị số để tính tổng, trung bình..." },
  { value: "dimension", label: "Chiều", description: "Dùng để nhóm hoặc lọc dữ liệu" },
  { value: "label", label: "Nhãn", description: "Tên hiển thị của một thực thể" },
  { value: "time", label: "Thời gian", description: "Mốc thời gian của bản ghi" },
  { value: "row_kind", label: "Loại dòng", description: "Phân biệt các loại dòng trong cùng bảng" },
  { value: "attribute", label: "Thuộc tính", description: "Thông tin mô tả thêm" },
]

export const roleLabel = (role: SemanticRole) => semanticRoles.find((item) => item.value === role)?.label ?? role

export const columnAggregations: { value: ColumnAggregation; label: string }[] = [
  { value: "SUM", label: "Tổng" },
  { value: "AVG", label: "Trung bình" },
  { value: "MIN", label: "Nhỏ nhất" },
  { value: "MAX", label: "Lớn nhất" },
  { value: "COUNT", label: "Đếm" },
  { value: "COUNT_DISTINCT", label: "Đếm khác nhau" },
]

export const temporalKinds: { value: TemporalKind; label: string }[] = [
  { value: "date", label: "Ngày" },
  { value: "timestamp", label: "Ngày giờ" },
]

export const tableKinds: { value: TableKind; label: string }[] = [
  { value: "base", label: "Bảng gốc" },
  { value: "aggregate", label: "Bảng tổng hợp" },
]

export const tableLayouts: { value: TableLayout; label: string; description: string }[] = [
  { value: "wide", label: "Mỗi chỉ số một cột", description: "Bảng thông thường, mỗi số đo nằm ở một cột riêng." },
  {
    value: "indicator_values",
    label: "Chỉ số theo dòng",
    description: "Mỗi dòng ghi một chỉ số và giá trị của nó; cột mã chỉ số cho biết dòng là chỉ số nào.",
  },
  {
    value: "indicator_catalog",
    label: "Danh mục chỉ số",
    description: "Bảng giải thích mã, tên, đơn vị và cách tổng hợp của từng chỉ số.",
  },
]

export const timeGrains: { value: TimeGrainValue; label: string }[] = [
  { value: "instant", label: "Từng thời điểm" },
  { value: "hour", label: "Giờ" },
  { value: "day", label: "Ngày" },
  { value: "week", label: "Tuần" },
  { value: "month", label: "Tháng" },
  { value: "quarter", label: "Quý" },
  { value: "year", label: "Năm" },
]

export const indicatorAggregations: { value: IndicatorAggregationValue; label: string }[] = [
  { value: "SUM", label: "Tổng" },
  { value: "AVG", label: "Trung bình" },
  { value: "MIN", label: "Nhỏ nhất" },
  { value: "MAX", label: "Lớn nhất" },
  { value: "COUNT", label: "Đếm" },
  { value: "NONE", label: "Không tổng hợp" },
]

export type RoleSlot = { role: string; qualifier: string | null; label: string; description?: string }

export const valueSlots: RoleSlot[] = [
  { role: "value", qualifier: "number", label: "Cột giá trị số" },
  { role: "value", qualifier: "boolean", label: "Cột giá trị đúng/sai" },
  { role: "value", qualifier: "text", label: "Cột giá trị chữ" },
]

export const catalogSlots: RoleSlot[] = [
  { role: "catalog_key", qualifier: null, label: "Khóa chỉ số", description: "Giá trị khớp với cột mã chỉ số ở bảng dữ liệu." },
  { role: "catalog_code", qualifier: null, label: "Mã chỉ số" },
  { role: "catalog_name", qualifier: null, label: "Tên chỉ số" },
  { role: "catalog_unit", qualifier: null, label: "Đơn vị" },
  { role: "catalog_value_kind", qualifier: null, label: "Kiểu giá trị" },
  { role: "catalog_aggregation", qualifier: null, label: "Cách tổng hợp" },
]

export const requiredRoles: Record<TableLayout, string[]> = {
  wide: [],
  indicator_values: ["indicator_key", "value"],
  indicator_catalog: ["catalog_key", "catalog_code", "catalog_name"],
}

export const layoutRoles: Record<TableLayout, string[]> = {
  wide: ["time", "created_at", "row_kind"],
  indicator_values: ["time", "created_at", "row_kind", "indicator_key", "value"],
  indicator_catalog: ["time", "created_at", "row_kind", ...catalogSlots.map((slot) => slot.role)],
}
