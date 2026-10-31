import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './catalog-api'
import { countryNames } from './library-api'
import type { LibraryEntry, LibraryPageData, LibraryStatus, WorkRequest } from './library-api'
import WorkDialog from './components/WorkDialog'
import ImportDialog from './components/ImportDialog'

export default function LibraryPage() {
  const [status, setStatus] = useState<LibraryStatus>('watched')
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [data, setData] = useState<LibraryPageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState(false)
  const [error, setError] = useState('')
  const [workRequest, setWorkRequest] = useState<WorkRequest | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importRunning, setImportRunning] = useState(false)
  const importChanged = useCallback(() => setRevision(n => n + 1), [])

  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    const params = new URLSearchParams({ status, query, page: String(page) })
    api<LibraryPageData>('/library?' + params)
      .then(result => { if (active) setData(result) })
      .catch(reason => { if (active) setError((reason as Error).message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [status, query, page, revision])

  function search(event: FormEvent) { event.preventDefault(); setQuery(draft.trim()); setPage(1) }
  function saved(item: LibraryEntry) {
    setStatus(item.status); setQuery(''); setDraft(''); setPage(1); setRevision(n => n + 1)
  }
  async function clearLibrary() {
    if (!window.confirm('清空片库会移除全部想看、看过和评分记录。确认清空？')) return
    setClearing(true); setError('')
    try {
      await api<{ deleted: number }>('/library', { method: 'DELETE' })
      setQuery(''); setDraft(''); setPage(1); setRevision(n => n + 1)
    } catch (reason) { setError((reason as Error).message) }
    finally { setClearing(false) }
  }
  const count = data ? data.counts.wish + data.counts.watched : null
  const pages = data ? Math.ceil(data.total / data.page_size) : 0
  const watched = data?.counts.watched ?? 0

  return <main className="library-main">
    <section className="library-hero"><div><div className="eyebrow"><span />私人片库</div><h1>我的片库</h1><p>电影使人的寿命延长了三倍。</p></div><div className="library-hero-actions"><button className="import-button" onClick={() => setImportOpen(true)}><span aria-hidden="true">↥</span>{importRunning ? '导入中…' : '导入豆瓣记录'}</button><button className="primary-button" disabled={importRunning} onClick={() => setWorkRequest({})}><span aria-hidden="true">＋</span>手动添加</button></div></section>
    <section className="library-workspace">
      <section className="library-list-panel" aria-labelledby="library-list-title" aria-busy={loading || clearing}>
        <div className="library-list-heading"><div className="library-title-row"><h2 id="library-list-title">片单</h2><span className="total-badge">共 {count ?? '—'} 部</span><button className="clear-library-button" disabled={loading || clearing || importRunning} onClick={() => void clearLibrary()}>{clearing ? '清空中…' : '清空片库'}</button></div><p>按标记时间排序</p>
          <div className="library-tabs" role="tablist" aria-label="片库状态">{(['wish', 'watched'] as const).map(tab => <button key={tab} id={'tab-' + tab} role="tab" aria-selected={status === tab} aria-controls="library-entries" disabled={loading} className={status === tab ? 'active' : ''} onClick={() => { setStatus(tab); setPage(1) }}>{tab === 'wish' ? '想看' : '看过'}（{data ? data.counts[tab] : '—'}）</button>)}</div>
          <form className="library-filters" onSubmit={search}><label className="sr-only" htmlFor="library-query">搜索个人片库</label><div className="local-search"><input id="library-query" value={draft} disabled={loading} onChange={e => setDraft(e.target.value)} placeholder="搜索片库中的作品" /><button aria-label="搜索片库" disabled={loading}><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg></button></div></form>
        </div>
        <div className="library-entries" id="library-entries" role="tabpanel" aria-labelledby={'tab-' + status}>
          {error ? <div className="library-empty"><p role="alert">{error}</p><button className="quiet-button" onClick={() => setRevision(n => n + 1)}>重新加载</button></div>
            : loading ? <div className="library-empty" role="status">正在读取片单…</div>
            : data && data.items.length > 0 ? <>{status === 'wish' && <div className="list-explanation">想看的下一部，也许就在这里</div>}<ul>{data.items.map((item, index) => {
              const work = item.catalog
              const metadata = [work.year, countryNames(work), work.genres[0]?.name].filter(Boolean).join(' · ')
              return <li className="library-row" key={item.id}><span className="row-number">{String((page - 1) * data.page_size + index + 1).padStart(2, '0')}</span><a className="row-work" href={work.source_url} target="_blank" rel="noreferrer"><strong>{work.title}</strong><span>{metadata}</span></a>
                {status === 'wish' ? <button className="mark-watched-button" disabled={importRunning} onClick={() => setWorkRequest({ entry: item, startRating: true })}><span aria-hidden="true">✓</span>标记看过</button>
                  : item.rating === null ? <span className="unrated">未评分</span> : <div className="row-rating" aria-label={`${item.rating} 星，${item.score} 分`}><span className="row-stars" aria-hidden="true">{'★'.repeat(item.rating)}<i>{'★'.repeat(5 - item.rating)}</i></span><span>{item.score} <small>分</small></span></div>}
              </li>
            })}</ul></>
            : <div className="library-empty"><span className="empty-film" aria-hidden="true">▤</span><h3>{query ? '没有找到匹配的记录' : status === 'wish' ? '收藏下一部想看的作品' : '记录你的第一部看过'}</h3><p>{query ? '试试其他片名，或切换作品类型。' : '从手动添加或导入开始，建立属于你的片库。'}</p>{!query && <button className="quiet-button" disabled={importRunning} onClick={() => setWorkRequest({})}>＋ 手动添加</button>}</div>}
        </div>
        <div className="library-pagination"><span>{data && data.total > 0 ? `${(page - 1) * data.page_size + 1}–${Math.min(page * data.page_size, data.total)} / ${data.total}` : '0 / 0'}</span><div><button aria-label="上一页" disabled={loading || page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>{Array.from({ length: Math.min(pages, 5) }, (_, i) => {
          const n = Math.max(1, Math.min(page - 2, pages - 4)) + i
          return <button key={n} className={n === page ? 'active' : ''} aria-label={`第 ${n} 页`} aria-current={n === page ? 'page' : undefined} disabled={loading} onClick={() => setPage(n)}>{n}</button>
        })}<button aria-label="下一页" disabled={loading || page >= pages} onClick={() => setPage(p => p + 1)}>›</button></div></div>
      </section>
      <aside className="profile-panel" aria-labelledby="profile-title">
        <div className="eyebrow"><span />画像构建</div><h2 id="profile-title">我的观影画像</h2><p className="profile-subtitle">基于看过的影片生成</p>
        <div className="profile-pending"><svg aria-hidden="true" width="44" height="44" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="8" y="8" width="32" height="32" rx="9" /><circle cx="18" cy="20" r="1" fill="currentColor" /><circle cx="30" cy="20" r="1" fill="currentColor" /><path d="M17 29c4 4 10 4 14 0" /></svg><h3>暂无观影画像</h3></div>
        <div className="profile-records"><div><span>已记录看过</span><strong>{data ? watched : '—'}<small> 部</small></strong></div><span className="profile-record-icon" aria-hidden="true">▤</span></div>
        <div className="profile-progress"><div><span>观影记录积累</span><span>{data ? `${watched} / 50` : '—'}</span></div><progress max="50" value={Math.min(watched, 50)} aria-label="距首份画像所需的观影记录" /><p>{!data ? '读取观影记录后显示进度' : watched < 50 ? `再记录 ${50 - watched} 部看过的作品，积累首份画像所需的记录。` : '已积累首份画像所需的观影记录，画像尚未生成。'}</p></div>
        <div className="profile-summary-empty"><span>口味总结</span><p>你的观影故事，留待这里慢慢展开。</p></div>
        <p className="profile-quote">In this terrifying world, all we have are the connections that we make.</p>
      </aside>
    </section>
    {workRequest && <WorkDialog request={workRequest} onClose={() => setWorkRequest(null)} onSaved={saved} />}
    <ImportDialog open={importOpen} libraryCount={count ?? 0} onClose={() => setImportOpen(false)} onChanged={importChanged} onRunningChange={setImportRunning} />
  </main>
}
