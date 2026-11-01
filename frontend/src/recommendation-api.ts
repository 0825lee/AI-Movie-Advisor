import type { Detail } from './catalog-api'

export type RecommendationCardData = { movie_id: number; reason: string; movie: Detail; library_status: 'wish' | 'watched' | null }
export type BlockedMoviePage = {
  items: { movie_id: number; movie: Detail; created_at: number }[]
  total: number; page: number; page_size: number
}
export type RecommendationMode = 'request' | 'personalized'
export type RecommendationTask = {
  task_id: string; batch_id: string
  mode: RecommendationMode; profile_version: number | null; profile_summary: string | null
  status: 'prepared' | 'running' | 'succeeded' | 'failed'
  request_text: string; target_count: number
  cards: RecommendationCardData[]; needs_refresh: boolean
  workflow_run_id: string | null; error: string | null; created_at: number
}
