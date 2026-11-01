import type { Detail } from './catalog-api'

export type RecommendationCardData = { movie_id: number; reason: string; movie: Detail }
export type RecommendationTask = {
  task_id: string; batch_id: string
  status: 'prepared' | 'running' | 'succeeded' | 'failed'
  request_text: string; target_count: number
  cards: RecommendationCardData[]; needs_refresh: boolean
  workflow_run_id: string | null; error: string | null; created_at: number
}
