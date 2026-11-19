import type { DomainRef } from "../business-model/domains"

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
  business_domains: DomainRef[]
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
  business_domain_ids: string[]
}

export type GlossaryUpdate = GlossaryContent & {
  expected_revision: number
  business_domain_ids: string[]
}
