import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api } from './catalog-api'
import RecommendationCard from './components/RecommendationCard'
import type { RecommendationTask } from './recommendation-api'

const LAST_TASK = 'movie-advisor-request-task'
const examples = [
  ['2010 年后的日本悬疑', '想看一部2010年以后的日本悬疑电影。'],
  ['节奏慢、余味长', '想看一部节奏慢一点、余味长的电影。'],
  ['周五晚上的华语片', '想看一部适合周五晚上的华语片。'],
]

export default function AIPicksPage({ active }: { active: boolean }) {
  const [taskId, setTaskId] = useState(() => sessionStorage.getItem(LAST_TASK))
  const [task, setTask] = useState<RecommendationTask | null>(null)
  const [draft, setDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(Boolean(taskId))
  const [error, setError] = useState('')
  const [queryFailed, setQueryFailed] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    if (!taskId || !active) return
    let current = true
    let timer: ReturnType<typeof setTimeout>
    async function query() {
      try {
        const result = await api<RecommendationTask>(`/recommendations/tasks/${taskId}`)
        if (!current) return
        setTask(result); setError(''); setQueryFailed(false); setLoading(false)
        setDraft(value => value || result.request_text)
        if (result.status === 'running') timer = setTimeout(() => void query(), 2000)
      } catch (reason) {
        if (current) { setError((reason as Error).message); setQueryFailed(true); setLoading(false) }
      }
    }
    void query()
    return () => { current = false; clearTimeout(timer) }
  }, [taskId, active, refresh])

  async function generate(retry = false) {
    const text = draft.trim()
    if (!retry && !text) { setError('先描述一下你想看的电影。'); setQueryFailed(false); return }
    setSubmitting(true); setError(''); setQueryFailed(false)
    try {
      const result = await api<RecommendationTask>(retry ? `/recommendations/tasks/${taskId}/run` : '/recommendations/request',
        retry ? { method: 'POST' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_text: text }) })
      setTask(result); setTaskId(result.task_id); sessionStorage.setItem(LAST_TASK, result.task_id)
      setRefresh(value => value + 1)
    } catch (reason) { setError((reason as Error).message) }
    finally { setSubmitting(false) }
  }

  function submit(event: FormEvent) { event.preventDefault(); void generate() }
  const busy = submitting || loading || task?.status === 'running'

  return <main className="picks-main">
    <section className="picks-hero"><div className="eyebrow"><span />AI 选片</div><h1>想看什么</h1><p>从此刻的观影需求出发，找到下一部想看的电影。</p><div className="picks-mode-row"><div className="picks-modes" aria-label="推荐模式"><button disabled title="暂未开放">按画像推荐</button><button className="active" aria-pressed="true">按需求推荐</button></div><span className="picks-exclusion-note"><span aria-hidden="true">✓</span> 推荐结果自动排除已看影片</span></div></section>
    <section className="picks-workspace">
      <section className="picks-demand-panel" aria-labelledby="demand-heading"><div className="eyebrow"><span />描述观影需求</div><h2 id="demand-heading">描述你此刻想看的电影</h2><p className="picks-description">可以包含年代、国家或地区、类型与观影氛围，本轮只依据这段描述推荐。</p>
        <form onSubmit={submit}><label className="sr-only" htmlFor="demand-input">描述观影需求</label><textarea id="demand-input" value={draft} onChange={event => setDraft(event.target.value)} disabled={busy} rows={4} placeholder="例如：想看一部2010年以后的日本悬疑电影。" /><div className="picks-form-footer"><div><p>试试这些描述</p><div className="picks-examples">{examples.map(([label, text]) => <button key={label} type="button" disabled={busy} onClick={() => setDraft(text)}>{label}</button>)}</div></div><button type="submit" className="primary-button picks-submit" disabled={busy || !draft.trim()}><span aria-hidden="true">✦</span>{busy ? '正在推荐…' : '推荐电影'}</button></div></form>
      </section>
      {error && <div className="picks-error" role="alert"><p>{error}</p>{queryFailed ? <button className="quiet-button" onClick={() => { setLoading(true); setRefresh(value => value + 1) }}>重新查询</button> : <span>请检查后重新提交。</span>}</div>}
      <section className="picks-results" aria-label="推荐结果" aria-busy={busy}>
        {busy ? <div className="picks-status" role="status"><span className="picks-spinner" aria-hidden="true" /><h2>{loading ? '正在读取推荐结果' : '正在为你寻找电影'}</h2><p>{loading ? '稍候片刻，查看本次推荐的最新状态。' : '正在理解需求、检索并挑选合适的影片，请稍候。'}</p></div>
          : task?.status === 'failed' ? <div className="picks-status picks-failed" role="alert"><span className="picks-status-icon" aria-hidden="true">!</span><h2>这次推荐未能完成</h2><p>{task.error}</p><button className="primary-button" onClick={() => void generate(true)}>重试本次推荐</button></div>
          : task?.status === 'succeeded' ? <><div className="picks-result-heading"><div><div className="eyebrow"><span />根据本次需求推荐</div><h2>为你挑选的 {task.target_count} 部</h2></div></div><p className="picks-request-summary">本次需求：{task.request_text}</p>{task.needs_refresh && <p className="picks-stale" role="status">部分影片已看过或已不再推荐，已从结果中移除。可以提交需求重新推荐。</p>}<div className="picks-grid">{task.cards.map((card, index) => <RecommendationCard key={card.movie_id} card={card} index={index} total={task.target_count} />)}</div></>
          : !error && <div className="picks-status picks-empty"><span className="picks-status-icon" aria-hidden="true">▤</span><h2>推荐结果会出现在这里</h2><p>说说此刻想看的电影，每次为你挑选 3 部。</p></div>}
      </section>
    </section>
  </main>
}
