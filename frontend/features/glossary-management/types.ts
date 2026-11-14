export type LinkKind = "table" | "column" | "metric"
export type RevisionStatus = "draft" | "approved" | "revoked"

export type GlossaryLink = {
  kind: LinkKind
  id: string
}

export type GlossaryRevision = {
  number: number
  status: RevisionStatus
  definition: string
  synonyms: string[]
  links: GlossaryLink[]
  created_at: string
}

export type GlossaryTerm = {
  id: string
  connection_id: string
  canonical_name: string
  group_name: string | null
  current: GlossaryRevision
  serving: GlossaryRevision | null
  created_at: string
  updated_at: string
}

export type GlossaryContent = {
  definition: string
  synonyms: string[]
  links: GlossaryLink[]
}

export type GlossaryCreate = GlossaryContent & {
  connection_id: string
  canonical_name: string
  group_name: string | null
}

export type GlossaryUpdate = GlossaryContent & {
  expected_revision: number
  group_name: string | null
}
