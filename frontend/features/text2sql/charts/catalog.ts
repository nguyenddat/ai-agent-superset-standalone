import useSWR from "swr"
import {
  ActivityIcon,
  AreaChartIcon,
  BarChart3Icon,
  BarChartBigIcon,
  BarChartHorizontalIcon,
  BoxIcon,
  CalendarDaysIcon,
  ChartCandlestickIcon,
  ChartColumnStackedIcon,
  ChartNoAxesColumnIcon,
  ChartScatterIcon,
  CircleDotIcon,
  DonutIcon,
  FilterIcon,
  GaugeIcon,
  Grid3x3Icon,
  HashIcon,
  LayersIcon,
  LineChartIcon,
  type LucideIcon,
  PieChartIcon,
  RadarIcon,
  SquareSplitHorizontalIcon,
  SunIcon,
  TableIcon,
  TrendingUpIcon,
  WavesIcon,
  WorkflowIcon,
} from "lucide-react"

import { apiFetch } from "@/lib/api"

import type { ChartType } from "./spec"

export type RoleInfo = {
  role: string
  required: boolean
  multiple: boolean
  min: number
  max: number
  accepts: string[]
}

export type ChartTypeInfo = {
  type: ChartType
  family: string
  label: string
  roles: RoleInfo[]
  min_rows: number
  max_rows: number | null
  max_series: number | null
  options_schema: { properties?: Record<string, JsonSchema>; $defs?: Record<string, JsonSchema> }
}

export type JsonSchema = {
  type?: string
  enum?: unknown[]
  default?: unknown
  title?: string
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  anyOf?: JsonSchema[]
  items?: JsonSchema
  maxItems?: number
}

export type ChartCatalog = { version: number; palette: string[]; enabled: ChartType[]; types: ChartTypeInfo[] }

export const FAMILIES = ["Con số", "So sánh", "Thành phần", "Xu hướng", "Phân bố", "Quan hệ", "Dòng chảy", "Bảng"]

// Labels for when the catalog has not loaded yet; the backend's GET /chart-types is the source of truth.
export const TYPE_LABELS: Record<ChartType, string> = {
  kpi: "Thẻ số",
  bullet: "Thanh mục tiêu",
  bar: "Cột",
  bar_horizontal: "Thanh ngang",
  bar_grouped: "Cột nhóm",
  lollipop: "Kẹo mút",
  dumbbell: "Quả tạ",
  diverging_bar: "Thanh phân kỳ",
  radial_bar: "Thanh tròn",
  radar: "Mạng nhện",
  bar_stacked: "Cột chồng",
  bar_stacked_100: "Cột chồng 100%",
  pie: "Tròn",
  donut: "Vành khuyên",
  treemap: "Ô vuông",
  sunburst: "Vành nhiều tầng",
  waterfall: "Thác nước",
  funnel: "Phễu",
  line: "Đường",
  area: "Vùng",
  area_stacked: "Vùng chồng",
  area_stacked_100: "Vùng chồng 100%",
  combo: "Cột và đường",
  sparkline_table: "Bảng đường nhỏ",
  calendar_heatmap: "Lịch nhiệt",
  histogram: "Tần suất",
  box_plot: "Hộp",
  heatmap: "Bản đồ nhiệt",
  scatter: "Phân tán",
  bubble: "Bong bóng",
  sankey: "Dòng chảy",
  table: "Bảng",
}

export const TYPE_FAMILIES: Record<ChartType, string> = {
  kpi: "Con số",
  bullet: "Con số",
  bar: "So sánh",
  bar_horizontal: "So sánh",
  bar_grouped: "So sánh",
  lollipop: "So sánh",
  dumbbell: "So sánh",
  diverging_bar: "So sánh",
  radial_bar: "So sánh",
  radar: "So sánh",
  bar_stacked: "Thành phần",
  bar_stacked_100: "Thành phần",
  pie: "Thành phần",
  donut: "Thành phần",
  treemap: "Thành phần",
  sunburst: "Thành phần",
  waterfall: "Thành phần",
  funnel: "Thành phần",
  line: "Xu hướng",
  area: "Xu hướng",
  area_stacked: "Xu hướng",
  area_stacked_100: "Xu hướng",
  combo: "Xu hướng",
  sparkline_table: "Xu hướng",
  calendar_heatmap: "Xu hướng",
  histogram: "Phân bố",
  box_plot: "Phân bố",
  heatmap: "Phân bố",
  scatter: "Quan hệ",
  bubble: "Quan hệ",
  sankey: "Dòng chảy",
  table: "Bảng",
}

export const TYPE_ICONS: Record<ChartType, LucideIcon> = {
  kpi: HashIcon,
  bullet: GaugeIcon,
  bar: BarChart3Icon,
  bar_horizontal: BarChartHorizontalIcon,
  bar_grouped: BarChartBigIcon,
  lollipop: CircleDotIcon,
  dumbbell: SquareSplitHorizontalIcon,
  diverging_bar: ChartNoAxesColumnIcon,
  radial_bar: ActivityIcon,
  radar: RadarIcon,
  bar_stacked: ChartColumnStackedIcon,
  bar_stacked_100: ChartColumnStackedIcon,
  pie: PieChartIcon,
  donut: DonutIcon,
  treemap: LayersIcon,
  sunburst: SunIcon,
  waterfall: ChartCandlestickIcon,
  funnel: FilterIcon,
  line: LineChartIcon,
  area: AreaChartIcon,
  area_stacked: AreaChartIcon,
  area_stacked_100: AreaChartIcon,
  combo: TrendingUpIcon,
  sparkline_table: WavesIcon,
  calendar_heatmap: CalendarDaysIcon,
  histogram: BarChart3Icon,
  box_plot: BoxIcon,
  heatmap: Grid3x3Icon,
  scatter: ChartScatterIcon,
  bubble: ChartScatterIcon,
  sankey: WorkflowIcon,
  table: TableIcon,
}

export const ROLE_LABELS: Record<string, string> = {
  x: "Trục x",
  y: "Số đo",
  series: "Chia màu theo",
  row: "Hàng",
  path: "Nhóm cha",
  size: "Kích thước",
  color: "Màu theo",
  goal: "Mục tiêu",
  compare: "So với",
  source: "Nguồn",
  target: "Đích",
  label: "Nhãn điểm",
}

const CHART_TYPES_PATH = "/api/v1/text2sql/chart-types"

// The catalog is static per deployment, so it is fetched once per page.
export function useChartCatalog() {
  return useSWR<ChartCatalog>(CHART_TYPES_PATH, (path: string) => apiFetch<ChartCatalog>(path), {
    revalidateOnFocus: false,
    revalidateIfStale: false,
  })
}

export const typeLabel = (type: string) => TYPE_LABELS[type as ChartType] ?? type
