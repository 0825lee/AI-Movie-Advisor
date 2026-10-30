import type { Detail } from './catalog-api'

export type LibraryStatus = 'wish' | 'watched'
export type LibraryState = {
  item_id: number | null
  status: LibraryStatus | null
  rating: number | null
  score: number | null
}
export type LibraryEntry = {
  id: number
  status: LibraryStatus
  rating: number | null
  score: number | null
  marked_at: number
  source: string
  catalog: Detail
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
  return { item_id: entry.id, status: entry.status, rating: entry.rating, score: entry.score }
}

const regionNames = new Intl.DisplayNames(['zh-CN'], { type: 'region' })
export function countryNames(work: Detail): string {
  return work.countries.map(c => regionNames.of(c.iso_3166_1) || c.name).join(' / ')
}
