import type { Detail, MediaType } from './catalog-api'

export type LibraryStatus = 'wish' | 'watched'
export type LibraryWork = Omit<Detail, 'media_type' | 'tmdb_id' | 'tmdb_url' | 'confirmed' | 'fetched_at'> & {
  media_type: MediaType | 'work'
  tmdb_id: number | null
  tmdb_url: string | null
  source_url: string
  source_name: string
  info: string
  languages: string[]
}
export type LibraryState = {
  item_id: number | null
  status: LibraryStatus | null
  rating: number | null
  score: number | null
  comment: string
}
export type LibraryEntry = {
  id: number
  status: LibraryStatus
  rating: number | null
  score: number | null
  marked_at: number | null
  source: string
  comment: string
  catalog: LibraryWork
}
export type LibraryPageData = {
  items: LibraryEntry[]
  counts: { wish: number; watched: number }
  total: number
  page: number
  page_size: number
}
export type WorkRequest = { entry?: LibraryEntry; startRating?: boolean }

export function entryState(entry: LibraryEntry): LibraryState {
  return { item_id: entry.id, status: entry.status, rating: entry.rating, score: entry.score, comment: entry.comment }
}

const regionNames = new Intl.DisplayNames(['zh-CN'], { type: 'region' })
export function countryNames(work: Pick<Detail, 'countries'>): string {
  return work.countries.map(c => c.iso_3166_1 ? regionNames.of(c.iso_3166_1) || c.name : c.name).join(' / ')
}
