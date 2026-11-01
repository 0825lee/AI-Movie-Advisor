import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../catalog-api'
import { countryNames } from '../library-api'
import type { BlockedMoviePage } from '../recommendation-api'

export default function BlockedMoviesList({ onCount }: { onCount: (total: number) => void }) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<BlockedMoviePage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let current = true
    setLoading(true); setError('')
    api<BlockedMoviePage>('/recommendations/blocked?' + new URLSearchParams({ query, page: String(page) }))
      .then(result => { if (current) { setData(result); if (!query) onCount(result.total) } })
      .catch(reason => { if (current) setError(reason.message) })
      .finally(() => { if (current) setLoading(false) })
    return () => { current = false }
  }, [query, page, revision, onCount])
  function search(event: FormEvent) { event.preventDefault(); setQuery(draft.trim()); setPage(1) }
  const pages = data ? Math.ceil(data.total / data.page_size) : 0
  return <>
    <form className="library-filters blocked-filters" onSubmit={search}><label className="sr-only" htmlFor="blocked-query">搜索不感兴趣片单</label><div className="local-search"><input id="blocked-query" value={draft} onChange={e => setDraft(e.target.value)} placeholder="搜索不感兴趣的影片" /><button disabled={loading}>搜索</button></div></form>
    <div className="library-entries" id="library-entries" role="tabpanel" aria-labelledby="tab-blocked">
      {error ? <div className="library-empty"><p role="alert">{error}</p><button className="quiet-button" onClick={() => setRevision(n => n + 1)}>重新加载</button></div>
        : loading ? <div className="library-empty" role="status">正在读取片单…</div>
        : data?.items.length ? <><p className="list-explanation">这些影片不会出现在后续推荐中</p><ul>{data.items.map((item, index) => <li className="library-row" key={item.movie_id}><span className="row-number">{String((page - 1) * data.page_size + index + 1).padStart(2, '0')}</span><a className="row-work" href={item.movie.tmdb_url} target="_blank" rel="noreferrer"><strong>{item.movie.title}</strong><span>{[item.movie.year, countryNames(item.movie), item.movie.genres[0]?.name].filter(Boolean).join(' · ')}</span></a><span className="unrated">不感兴趣</span></li>)}</ul></>
        : <div className="library-empty"><h3>{query ? '没有找到匹配的影片' : '暂无不感兴趣的影片'}</h3><p>在推荐卡片中点击“不感兴趣”，影片会加入这里。</p></div>}
    </div>
    <div className="library-pagination"><span>{data?.total ? `${(page - 1) * data.page_size + 1}–${Math.min(page * data.page_size, data.total)} / ${data.total}` : '0 / 0'}</span><div><button aria-label="上一页" disabled={loading || page <= 1} onClick={() => setPage(n => n - 1)}>‹</button><button aria-label="下一页" disabled={loading || page >= pages} onClick={() => setPage(n => n + 1)}>›</button></div></div>
  </>
}
