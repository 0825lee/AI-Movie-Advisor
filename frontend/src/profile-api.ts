export type ProfileEvidence = { title: string; originalTitle: string; rating: number | null; commentExcerpt: string | null }
export type ProfileConclusion = { dimension: string; label: string; reason: string; evidence: ProfileEvidence[] }
export type TasteProfile = {
  version: number; covered_count: number; summary: string
  preferences: ProfileConclusion[]; less_preferred: ProfileConclusion[]
  recent_changes: ProfileConclusion[]; limitations: string[]
}
export type ProfileState = {
  profile: TasteProfile | null; created_at: number | null; watched_count: number
  covered_count: number; pending_count: number; remaining: number; configured: boolean; generating: boolean
  job: { id: number; status: string; stage: string; version: number; batch_count: number; error: string | null; created_at: number } | null
}
