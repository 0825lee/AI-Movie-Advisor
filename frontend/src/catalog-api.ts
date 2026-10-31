export type MediaType = 'movie' | 'tv' | 'season'
export type SearchType = 'all' | 'movie' | 'tv'
export type CatalogRef = { media_type: MediaType; tmdb_id: number; season_number: number | null }
export type Candidate = CatalogRef & {
  title: string; original_title: string; year: number | null
  overview: string; poster_url: string | null
}
export type Detail = Candidate & {
  catalog_id: number; confirmed: boolean; fetched_at: number
  overview_language: string | null; original_language: string; runtime: number | null
  genres: { id: number | null; name: string }[]
  countries: { iso_3166_1: string | null; name: string }[]
  directors: { id: number | null; name: string }[]
  creators: { id: number | null; name: string }[]
  cast: { id: number | null; name: string }[]
  seasons: { season_number: number; name: string; year: number | null; episode_count: number }[]
  episode_count: number | null; tmdb_url: string
}
export type SearchResult = { items: Candidate[]; page: number; total_pages: number }
export type CatalogPage = { items: Detail[]; page: number; total: number }

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, options)
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败，请检查输入后重试。')
  return data as T
}

export function reference(item: CatalogRef): CatalogRef {
  return { media_type: item.media_type, tmdb_id: item.tmdb_id, season_number: item.season_number }
}

export function detailPath(item: CatalogRef, refresh = false): string {
  const params = new URLSearchParams({ media_type: item.media_type, tmdb_id: String(item.tmdb_id) })
  if (item.season_number !== null) params.set('season_number', String(item.season_number))
  if (refresh) params.set('refresh', 'true')
  return '/catalog/details?' + params
}

export function mediaLabel(type: MediaType): string {
  return { movie: '电影', tv: '剧集', season: '剧集' }[type]
}
