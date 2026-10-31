import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, detailPath, reference } from '../catalog-api'
import type { Candidate, CatalogRef, Detail, SearchResult } from '../catalog-api'
import { countryNames, entryState } from '../library-api'
import type { LibraryEntry, LibraryState, LibraryStatus, LibraryWork, WorkRequest } from '../library-api'
import Poster from './Poster'
import RatingPicker from './RatingPicker'

export default function WorkDialog({ request, onClose, onSaved }: {
  request: WorkRequest; onClose: () => void; onSaved: (entry: LibraryEntry) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [step, setStep] = useState<'search' | 'detail' | 'rating'>(request.startRating ? 'rating' : request.entry ? 'detail' : 'search')
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState<SearchResult | null>(null)
  const [lastSearch, setLastSearch] = useState({ query: '' })
  const [detail, setDetail] = useState<Detail | LibraryWork | null>(request.entry?.catalog ?? null)
  const [state, setState] = useState<LibraryState>(request.entry ? entryState(request.entry) : { item_id: null, status: null, rating: null, score: null })
  const [selected, setSelected] = useState<CatalogRef | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => { if (!dialog.current?.open) dialog.current?.showModal() }, [])
  function close() { if (!busy) onClose() }

  async function runSearch(values = { query }, page = 1) {
    setBusy(true); setError(''); setNotice(''); setLastSearch(values)
    const params = new URLSearchParams({ query: values.query.trim(), page: String(page) })
    try { setSearch(await api<SearchResult>('/catalog/search?' + params)) }
    catch (reason) { setSearch(null); setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) void runSearch()
  }
  async function selectWork(work: CatalogRef, refresh = false) {
    setSelected(reference(work)); setStep('detail'); setDetail(null); setBusy(true); setError(''); setNotice('')
    const statePath = detailPath(work).replace('/catalog/details', '/library/state')
    try {
      const workDetail = await api<Detail>(detailPath(work, refresh))
      const personalState = await api<LibraryState>(statePath)
      setDetail(workDetail); setState(personalState)
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  async function save(status: LibraryStatus, rating: number | null = null) {
    if (!detail) return
    setBusy(true); setError(''); setNotice('')
    try {
      const existingWish = status === 'watched' && state.item_id !== null
      const updated = await api<LibraryEntry>(existingWish ? `/library/${state.item_id}/watched` : '/library/manual', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(existingWish ? { rating } : { media_type: detail.media_type, tmdb_id: detail.tmdb_id, season_number: detail.season_number, status, rating }),
      })
      setState(entryState(updated)); setDetail(updated.catalog); setStep('detail')
      setNotice(updated.status === 'wish' ? '已加入想看' : '已标记看过')
      onSaved(updated)
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }

  function refreshDetail() {
    if (detail && detail.tmdb_id !== null && detail.media_type !== 'work') {
      void selectWork({ media_type: detail.media_type, tmdb_id: detail.tmdb_id, season_number: detail.season_number }, true)
    }
  }

  return <dialog ref={dialog} className="detail-dialog work-dialog" aria-labelledby="work-dialog-title" onCancel={e => { e.preventDefault(); close() }} onClick={e => { if (e.target === dialog.current) close() }}>
    <div className="detail-shell">
      <div className="work-dialog-heading"><div><h2 id="work-dialog-title">{step === 'search' ? '手动添加作品' : step === 'rating' ? '标记看过' : '作品资料'}</h2><p>{step === 'search' ? '搜索影片' : step === 'rating' ? '你的个人观影记录' : '核对作品信息，记录想看或看过'}</p></div><button className="close-button" aria-label="关闭窗口" disabled={busy} onClick={close}>×</button></div>
      {error && <div className="notice error-message" role="alert">{error}{step === 'detail' && selected && !detail && <button onClick={() => void selectWork(selected)}>重试</button>}</div>}
      {notice && <div className="library-notice" role="status">✓ {notice}</div>}
      {step === 'search' && <>
        <form className="work-search" onSubmit={submit}>
          <label className="sr-only" htmlFor="remote-query">作品名称</label><input id="remote-query" autoFocus required value={query} disabled={busy} onChange={e => setQuery(e.target.value)} placeholder="输入影片名称" />

          <button className="primary-button" disabled={busy || !query.trim()}>{busy ? '搜索中…' : '搜索'}</button>
        </form>
        {busy ? <div className="dialog-empty" role="status">正在查找作品…</div> : search ? <>
          <p className="search-result-note">{search.items.length ? '选择正确的作品，同名作品请核对年份。' : '没有找到作品，试试原名或缩短关键词。'}</p>
          <div className="work-grid">{search.items.map((item: Candidate) => <button className="work-card" key={`${item.media_type}:${item.tmdb_id}:${item.season_number}`} onClick={() => void selectWork(item)}>
            <div className="work-image"><Poster url={item.poster_url} title={item.title} /></div>
            <div className="work-caption"><h3>{item.title}</h3><p className="original-title">{item.original_title}</p><div className="work-meta">{item.year ?? '年份待补'}</div></div>
          </button>)}</div>
          {search.total_pages > 1 && <div className="pagination"><button className="quiet-button" disabled={search.page === 1} onClick={() => void runSearch(lastSearch, search.page - 1)}>上一页</button><span>{search.page} / {search.total_pages}</span><button className="quiet-button" disabled={search.page >= search.total_pages} onClick={() => void runSearch(lastSearch, search.page + 1)}>下一页</button></div>}
        </> : <div className="dialog-empty"><span aria-hidden="true">▤</span><p>从一部熟悉的作品开始。</p></div>}
      </>}
      {step === 'detail' && <>
        {!request.entry && <button className="text-button dialog-back" disabled={busy} onClick={() => { setStep('search'); setError(''); setNotice('') }}>← 返回搜索结果</button>}
        {busy && !detail ? <div className="dialog-empty" role="status">正在读取作品资料…</div> : detail && <>
          <div className="detail-content"><Poster className="detail-poster" url={detail.poster_url} title={detail.title} /><div className="detail-summary">
            <div className="detail-kicker">影片<span>·</span>{detail.year ?? '年份待补'}</div><h3 className="work-detail-title">{detail.title}</h3><p className="detail-original">{detail.original_title}</p>
            <div className="genre-list">{detail.genres.map(g => <span key={g.name}>{g.name}</span>)}</div>
            <dl className="detail-facts">
              {detail.directors.length > 0 && <><dt>导演</dt><dd>{detail.directors.map(p => p.name).join(' / ')}</dd></>}
              {detail.creators.length > 0 && <><dt>主创</dt><dd>{detail.creators.map(p => p.name).join(' / ')}</dd></>}
              <dt>主演</dt><dd>{detail.cast.map(p => p.name).join(' / ') || '暂无资料'}</dd><dt>国家 / 地区</dt><dd>{countryNames(detail) || '暂无资料'}</dd>
              {detail.runtime !== null && detail.runtime > 0 && <><dt>时长</dt><dd>{detail.runtime} 分钟</dd></>}
              {detail.episode_count !== null && <><dt>集数</dt><dd>{detail.episode_count} 集</dd></>}
            </dl>
          </div></div>
          <section className="overview-section"><div className="overview-heading"><h3>剧情简介</h3>{detail.overview_language === 'en-US' && <span>英文简介</span>}</div><p>{detail.overview || '暂无简介'}</p></section>
          <div className="detail-source"><a href={'source_url' in detail ? detail.source_url : detail.tmdb_url ?? undefined} target="_blank" rel="noreferrer">在 {'source_name' in detail ? detail.source_name : 'TMDB'} 查看 ↗</a>{detail.tmdb_id !== null && <button className="text-button" disabled={busy} onClick={refreshDetail}>刷新资料</button>}</div>
          <div className="library-detail-actions"><span>{state.status === 'watched' ? state.rating === null ? '已看过 · 未评分' : `${state.rating} 星 · ${state.score} 分` : state.status === 'wish' ? '已在你的想看片单中' : '记录这部作品'}</span><div>
            <button className="quiet-button" disabled={busy || state.status !== null} onClick={() => void save('wish')}>{state.status === 'wish' ? '已加入想看' : '加入想看'}</button>
            <button className="primary-button" disabled={busy || state.status === 'watched'} onClick={() => { setStep('rating'); setError(''); setNotice('') }}>{state.status === 'watched' ? '已看过' : '标记看过'}</button>
          </div></div>
        </>}
      </>}
      {step === 'rating' && detail && <RatingPicker title={detail.title} busy={busy} onSubmit={rating => void save('watched', rating)} onBack={() => { setStep('detail'); setError('') }} />}
    </div>
  </dialog>
}
