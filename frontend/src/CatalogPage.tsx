import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, detailPath, mediaLabel, reference } from './catalog-api'
import type { Candidate, CatalogPage as SavedPage, Detail, SearchResult, SearchType } from './catalog-api'

function Poster({ url, title, className = '' }: { url: string | null; title: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [url])
  return <div className={'poster ' + className}>
    {url && !failed
      ? <img src={url} alt={title + '海报'} loading="lazy" onError={() => setFailed(true)} />
      : <div className="poster-placeholder"><span aria-hidden="true">▤</span><span>暂无海报</span></div>}
  </div>
}

function WorkCard({ item, onSelect, confirmed = false }: { item: Candidate; onSelect: () => void; confirmed?: boolean }) {
  return <button className="work-card" onClick={onSelect}>
    <div className="work-image"><Poster url={item.poster_url} title={item.title} />
      <span className="work-badge">{mediaLabel(item.media_type)}</span>
      <span className="work-open">查看资料 ↗</span>
    </div>
    <div className="work-caption">
      <h3>{item.title}</h3>
      <p className="original-title">{item.original_title}</p>
      <div className="work-meta"><span>{item.year ?? '年份待补'}</span>{confirmed && <span className="confirmed-mark">✓ 已确认</span>}</div>
    </div>
  </button>
}

function Pagination({ page, total, busy, onPage }: { page: number; total: number; busy: boolean; onPage: (page: number) => void }) {
  if (total <= 1) return null
  return <div className="pagination">
    <button className="quiet-button" disabled={page === 1 || busy} onClick={() => onPage(page - 1)}>← 上一页</button>
    <span>{page} / {total}</span>
    <button className="quiet-button" disabled={page >= total || busy} onClick={() => onPage(page + 1)}>下一页 →</button>
  </div>
}

export default function CatalogPage() {
  const [query, setQuery] = useState('')
  const [year, setYear] = useState('')
  const [mediaType, setMediaType] = useState<SearchType>('all')
  const [search, setSearch] = useState<SearchResult | null>(null)
  const [searchedFor, setSearchedFor] = useState('')
  const [criteria, setCriteria] = useState({ query: '', year: '', mediaType: 'all' as SearchType })
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [saved, setSaved] = useState<SavedPage>({ items: [], total: 0, page: 1 })
  const [savedError, setSavedError] = useState('')
  const [loadingSaved, setLoadingSaved] = useState(true)
  const [selection, setSelection] = useState<Candidate | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [saving, setSaving] = useState(false)
  const [detailError, setDetailError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const busy = loadingDetail || saving

  async function loadSaved(page = 1) {
    setLoadingSaved(true); setSavedError('')
    try { setSaved(await api<SavedPage>('/catalog/items?page=' + page)) }
    catch (error) { setSavedError((error as Error).message) }
    finally { setLoadingSaved(false) }
  }
  useEffect(() => { void loadSaved() }, [])
  useEffect(() => {
    if (selection && !dialog.current?.open) dialog.current?.showModal()
    if (!selection && dialog.current?.open) dialog.current.close()
  }, [selection])

  async function runSearch(values = { query, year, mediaType }, page = 1) {
    setSearching(true); setSearchError(''); setCriteria(values); setSearchedFor(values.query.trim())
    const params = new URLSearchParams({ query: values.query.trim(), media_type: values.mediaType, page: String(page) })
    if (values.year) params.set('year', values.year)
    try { setSearch(await api<SearchResult>('/catalog/search?' + params)) }
    catch (error) { setSearch(null); setSearchError((error as Error).message) }
    finally { setSearching(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (query.trim()) void runSearch()
  }
  async function openDetails(item: Candidate, refresh = false) {
    setSelection(item); setDetail(null); setDetailError(''); setLoadingDetail(true)
    try { setDetail(await api<Detail>(detailPath(item, refresh))) }
    catch (error) { setDetailError((error as Error).message) }
    finally { setLoadingDetail(false) }
  }
  async function confirm() {
    if (!detail) return
    setSaving(true); setDetailError('')
    try {
      setDetail(await api<Detail>('/catalog/confirm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(reference(detail)),
      }))
      await loadSaved()
    } catch (error) { setDetailError((error as Error).message) }
    finally { setSaving(false) }
  }
  function closeDetails() { if (!busy) setSelection(null) }

  return <main className="catalog-main">
    <div className="eyebrow"><span />发现作品 · CATALOG</div>
    <div className="page-heading catalog-heading"><div>
      <h1>每一部好电影，<br />从认识它开始。</h1>
      <p>搜索电影或剧集，核对版本与年份，保存你确认的作品。</p>
    </div><span className="catalog-edition">YOUR NEXT FRAME<span>电影 · 剧集 · 每一季</span></span></div>
    <form className="search-form" onSubmit={submit}>
      <div className="search-title-field"><label htmlFor="work-query">作品名称</label><input id="work-query" required value={query} disabled={searching} onChange={e => setQuery(e.target.value)} placeholder="中文名或原名，例如：盗梦空间" /></div>
      <div><label htmlFor="work-year">年份 <span>选填</span></label><input id="work-year" type="number" min="1000" max="9999" value={year} disabled={searching} onChange={e => setYear(e.target.value)} placeholder="如 2010" /></div>
      <div><label htmlFor="work-type">作品类型</label><select id="work-type" value={mediaType} disabled={searching} onChange={e => setMediaType(e.target.value as SearchType)}><option value="all">全部作品</option><option value="movie">电影</option><option value="tv">剧集</option></select></div>
      <button className="primary-button search-submit" disabled={searching || !query.trim()}>{searching ? '搜索中…' : '搜索作品'}<span aria-hidden="true">↗</span></button>
    </form>
    <div className="search-hints"><span>试试搜索</span>{['盗梦空间', '沙丘', '权力的游戏'].map(name => <button key={name} disabled={searching} onClick={() => {
      setQuery(name); setYear(''); setMediaType('all'); void runSearch({ query: name, year: '', mediaType: 'all' })
    }}>{name} ↗</button>)}</div>
    {(search || searching || searchError) && <section className="catalog-section" aria-label="搜索结果" aria-busy={searching}>
      <div className="section-heading"><div><span className="small-label">SEARCH RESULTS</span><h2>“{searchedFor}”的搜索结果</h2></div><span className="section-note">选择作品，查看完整资料</span></div>
      {searchError && <div className="notice error-message" role="alert">{searchError}<button onClick={() => void runSearch(criteria)}>重试</button></div>}
      {searching ? <div className="empty-state compact" role="status">正在查找相关作品…</div> : search && <>
        {search.items.length ? <div className="work-grid">{search.items.map(item => <WorkCard key={`${item.media_type}:${item.tmdb_id}`} item={item} onSelect={() => void openDetails(item)} />)}</div>
          : <div className="empty-state compact"><h3>没有找到相关作品</h3><p>试试原名、缩短关键词，或去掉年份再搜索。</p></div>}
        <Pagination page={search.page} total={search.total_pages} busy={searching} onPage={page => void runSearch(criteria, page)} />
      </>}
    </section>}
    <section className="catalog-section saved-section" aria-labelledby="saved-title" aria-busy={loadingSaved}>
      <div className="section-heading"><div><span className="small-label">CONFIRMED COLLECTION</span><h2 id="saved-title">已确认作品 <span className="count-label">{saved.total}</span></h2></div><button className="text-button" disabled={loadingSaved} onClick={() => void loadSaved(saved.page)}>↻ 刷新</button></div>
      {savedError ? <div className="notice error-message" role="alert">{savedError}<button onClick={() => void loadSaved(saved.page)}>重试</button></div>
        : loadingSaved ? <div className="empty-state compact" role="status">正在读取作品…</div>
        : saved.items.length ? <><div className="work-grid">{saved.items.map(item => <WorkCard key={item.catalog_id} item={item} confirmed onSelect={() => void openDetails(item)} />)}</div><Pagination page={saved.page} total={Math.ceil(saved.total / 24)} busy={loadingSaved} onPage={page => void loadSaved(page)} /></>
        : <div className="empty-state"><div className="empty-symbol" aria-hidden="true">▤</div><h3>从一部熟悉的作品开始</h3><p>搜索并确认作品后，资料会保存在这里。<br />下次回来，也能继续查阅。</p><span className="empty-line" /></div>}
    </section>
    <footer><span>9万天 · 私人观影记录与选片</span><div><a href="https://www.themoviedb.org" target="_blank" rel="noreferrer">资料来源 TMDB ↗</a></div></footer>
    <dialog className="detail-dialog" aria-label="作品资料" ref={dialog} onCancel={e => { e.preventDefault(); closeDetails() }} onClick={e => { if (e.target === dialog.current) closeDetails() }}>
      <div className="detail-shell">
        <div className="detail-top"><span className="eyebrow">作品资料</span><button className="close-button" aria-label="关闭作品资料" disabled={busy} onClick={closeDetails}>×</button></div>
        {loadingDetail ? <div className="empty-state" role="status">正在读取真实作品资料…</div> : <>
          {detailError && <div className="notice error-message" role="alert">{detailError}{!detail && selection && <button onClick={() => void openDetails(selection)}>重试</button>}</div>}
          {detail && <>
            <div className="detail-content"><Poster className="detail-poster" url={detail.poster_url} title={detail.title} /><div className="detail-summary">
              <div className="detail-kicker">{mediaLabel(detail.media_type)}<span>·</span>{detail.year ?? '年份待补'}</div>
              <h2>{detail.title}</h2><p className="detail-original">{detail.original_title}</p>
              <div className="genre-list">{detail.genres.map(g => <span key={g.id}>{g.name}</span>)}</div>
              <dl className="detail-facts">
                {detail.directors.length > 0 && <><dt>导演</dt><dd>{detail.directors.map(p => p.name).join(' / ')}</dd></>}
                {detail.creators.length > 0 && <><dt>主创</dt><dd>{detail.creators.map(p => p.name).join(' / ')}</dd></>}
                <dt>主演</dt><dd>{detail.cast.map(p => p.name).join(' / ') || '暂无资料'}</dd>
                <dt>国家 / 地区</dt><dd>{detail.countries.map(c => c.name).join(' / ') || '暂无资料'}</dd>
                {detail.runtime != null && detail.runtime > 0 && <><dt>{detail.media_type === 'movie' ? '片长' : '单集时长'}</dt><dd>{detail.runtime} 分钟</dd></>}
                {detail.episode_count !== null && <><dt>集数</dt><dd>{detail.episode_count} 集</dd></>}
              </dl>
              {detail.media_type === 'tv' && <div className="season-picker"><label htmlFor="season-choice">选择整剧或具体季</label><select id="season-choice" value="series" disabled={busy} onChange={e => {
                if (e.target.value !== 'series') void openDetails({ ...detail, media_type: 'season', season_number: Number(e.target.value) })
              }}><option value="series">整剧</option>{detail.seasons.map(s => <option key={s.season_number} value={s.season_number}>{s.name}{s.year ? ` · ${s.year}` : ''} · {s.episode_count} 集</option>)}</select></div>}
              {detail.media_type === 'season' && <button className="text-button back-series" onClick={() => void openDetails({ ...detail, media_type: 'tv', season_number: null })}>← 查看整剧及其他季</button>}
            </div></div>
            <section className="overview-section"><div className="overview-heading"><h3>剧情简介</h3>{detail.overview_language === 'en-US' && <span>英文简介</span>}</div><p>{detail.overview || '暂无简介'}</p></section>
            <div className="detail-source"><a href={detail.tmdb_url} target="_blank" rel="noreferrer">在 TMDB 查看 ↗</a><button className="text-button" disabled={busy} onClick={() => void openDetails(detail, true)}>刷新资料</button></div>
            <div className="detail-actions"><span>{detail.confirmed ? '✓ 作品资料已保存' : '核对作品、年份与季号后确认'}</span><button className="primary-button" disabled={busy || detail.confirmed} onClick={() => void confirm()}>{saving ? '保存中…' : detail.confirmed ? '已确认' : '确认作品资料'}</button></div>
          </>}
        </>}
      </div>
    </dialog>
  </main>
}
