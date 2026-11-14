import { BookTextIcon, ScaleIcon, SigmaIcon, type LucideIcon } from "lucide-react"

import type { BadgeTone } from "@/components/badge"

import type { KnowledgeKind, ReviewStatus } from "./types"

export const KINDS: Record<KnowledgeKind, { label: string; icon: LucideIcon }> = {
  glossary: { label: "Thuật ngữ", icon: BookTextIcon },
  metric: { label: "Metric", icon: SigmaIcon },
  expert_rule: { label: "Quy tắc", icon: ScaleIcon },
}

export const KIND_ORDER: KnowledgeKind[] = ["glossary", "metric", "expert_rule"]

export const REVIEW_STATES: Record<ReviewStatus, { label: string; tone: BadgeTone; hint: string }> = {
  pending: { label: "Chờ duyệt", tone: "warning", hint: "Chưa có admin nào xem. AI vẫn dùng cách hiểu này cho riêng người dùng." },
  kept_own: { label: "Giữ riêng", tone: "neutral", hint: "Admin quyết định để cách hiểu này là của riêng người dùng." },
  promoted: { label: "Đã vào kho", tone: "success", hint: "Đã tạo bản ghi trong kho từ cách hiểu này." },
}

export const formatTime = (value: string) =>
  new Date(value).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short", year: "numeric" })
