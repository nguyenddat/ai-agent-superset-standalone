import type { BadgeTone } from "@/components/badge"

import type { GlossaryContent, GlossaryLink, GlossaryRevision, GlossaryTerm } from "./types"

// What a reader cares about: is the AI using this term, and is there something waiting for review.
export type TermState = "approved" | "changed" | "draft" | "revoked"

export function termState(term: GlossaryTerm): TermState {
  if (term.current.status === "approved") return "approved"
  if (term.current.status === "revoked") return "revoked"
  return term.serving ? "changed" : "draft"
}

export const TERM_STATES: Record<TermState, { label: string; tone: BadgeTone; hint: string }> = {
  approved: { label: "Đã duyệt", tone: "success", hint: "AI đang dùng định nghĩa này." },
  changed: {
    label: "Chờ duyệt thay đổi",
    tone: "warning",
    hint: "AI vẫn dùng bản đã duyệt cho đến khi bản nháp mới được duyệt.",
  },
  draft: { label: "Chờ duyệt", tone: "warning", hint: "AI chưa dùng thuật ngữ này cho đến khi được duyệt." },
  revoked: { label: "Đã thu hồi", tone: "neutral", hint: "AI không còn dùng thuật ngữ này." },
}

// Mirrors the backend: runs of spaces collapse, and names compare without case.
export const normalizeName = (value: string) => value.split(/\s+/).filter(Boolean).join(" ")
export const foldName = (value: string) => normalizeName(value).toLocaleLowerCase("vi")

export const linkKey = (link: GlossaryLink) => `${link.kind}:${link.id}`

export function parseLinkKey(key: string): GlossaryLink {
  const [kind, id] = key.split(":") as [GlossaryLink["kind"], string]
  return { kind, id }
}

export const contentOf = (revision: GlossaryRevision): GlossaryContent => ({
  definition: revision.definition,
  synonyms: revision.synonyms,
  links: revision.links,
})

export const sameLinks = (a: GlossaryLink[], b: GlossaryLink[]) => {
  const keys = new Set(a.map(linkKey))
  return a.length === b.length && b.every((link) => keys.has(linkKey(link)))
}

export const sameSynonyms = (a: string[], b: string[]) => a.length === b.length && a.every((value, index) => value === b[index])
