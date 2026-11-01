import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { api, ApiError } from './catalog-api'
import RecommendationCard from './components/RecommendationCard'
import type { RecommendationMode, RecommendationTask } from './recommendation-api'
import type { ProfileState } from './profile-api'

const examples = [
  ['2010 年后的日本悬疑', '想看一部2010年以后的日本悬疑电影。'],
  ['节奏慢、余味长', '想看一部节奏慢一点、余味长的电影。'],
  ['周五晚上的华语片', '想看一部适合周五晚上的华语片。'],
]

export default function AIPicksPage({ active, onGoLibrary }: { active: boolean; onGoLibrary: () => void }) {
  const [mode, setMode] = useState<RecommendationMode>('request')
  return <main className="picks-main">
    <section className="picks-hero"><div className="eyebrow"><span />AI 选片</div><h1>想看什么</h1><p>从你的观影画像出发，或直接说出此刻的观影需求。</p><div className="picks-mode-row"><div className="picks-modes" aria-label="推荐模式"><button className={mode === 'personalized' ? 'active' : ''} aria-pressed={mode === 'personalized'} onClick={() => setMode('personalized')}>按画像推荐</button><button className={mode === 'request' ? 'active' : ''} aria-pressed={mode === 'request'} onClick={() => setMode('request')}>按需求推荐</button></div><span className="picks-exclusion-note"><span aria-hidden="true">✓</span> 推荐结果自动排除已看影片</span></div></section>
    {(['request', 'personalized'] as const).map(value => <div key={value} hidden={mode !== value}><RecommendationPanel active={active && mode === value} mode={value} onGoLibrary={onGoLibrary} /></div>)}
  </main>
}

export function RecommendationPanel({ active, mode, onGoLibrary }: { active: boolean; mode: RecommendationMode; onGoLibrary: () => void }) {
  const LAST_TASK = mode === 'request' ? 'movie-advisor-request-task' : 'movie-advisor-personalized-task'
  const [taskId, setTaskId] = useState(() => sessionStorage.getItem(LAST_TASK))
  const [task, setTask] = useState<RecommendationTask | null>(null)
  const [draft, setDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(Boolean(taskId))
  const [error, setError] = useState('')
  const [queryFailed, setQueryFailed] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [profile, setProfile] = useState<ProfileState | null>(null)
  const [profileLoading, setProfileLoading] = useState(mode === 'personalized')
  const [profileError, setProfileError] = useState('')

  useEffect(() => {
    if (!active || mode !== 'personalized') return
    let current = true
    setProfileLoading(true)
    api<ProfileState>('/profile').then(result => { if (current) { setProfile(result); setProfileError('') } })
      .catch(reason => { if (current) setProfileError(reason.message) })
      .finally(() => { if (current) setProfileLoading(false) })
    return () => { current = false }
  }, [active, mode, refresh])

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
        if (current) {
          if (reason instanceof ApiError && reason.status === 404) {
            setTask(null); setTaskId(null); sessionStorage.removeItem(LAST_TASK)
            setError('这条推荐记录已被清除，可以重新开始。'); setQueryFailed(false)
          } else { setError((reason as Error).message); setQueryFailed(true) }
          setLoading(false)
        }
      }
    }
    setLoading(true); void query()
    return () => { current = false; clearTimeout(timer) }
  }, [taskId, active, refresh, LAST_TASK])

  async function generate(retry = false) {
    const text = draft.trim()
    if (!retry && mode === 'request' && !text) { setError('先描述一下你想看的电影。'); setQueryFailed(false); return }
    setSubmitting(true); setError(''); setQueryFailed(false)
    try {
      const result = await api<RecommendationTask>(retry ? `/recommendations/tasks/${taskId}/run` : `/recommendations/${mode === 'request' ? 'request' : 'personalized'}`,
        retry || mode === 'personalized' ? { method: 'POST' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_text: text }) })
      setTask(result); setTaskId(result.task_id); sessionStorage.setItem(LAST_TASK, result.task_id)
      setRefresh(value => value + 1)
    } catch (reason) { setError((reason as Error).message) }
    finally { setSubmitting(false) }
  }

  function submit(event: FormEvent) { event.preventDefault(); void generate() }
  const busy = submitting || loading || task?.status === 'running'

  return <section className="picks-workspace">
      {mode === 'personalized' ? <section className="picks-demand-panel picks-profile-panel" aria-label="画像推荐">
        <div className="eyebrow"><span />画像摘要</div><h2>从你的观影口味出发</h2>
        {profileLoading ? <p className="picks-description" role="status">正在读取观影画像…</p>
          : profileError ? <p className="profile-error" role="alert">{profileError}<button className="text-button" onClick={() => setRefresh(n => n + 1)}>重新读取</button></p>
          : profile?.profile ? <><p className="picks-description">当前第 {profile.profile.version} 版画像 · 覆盖 {profile.profile.covered_count} 部看过影片</p><details className="picks-profile-details"><summary>{task?.profile_version ? `查看本次使用的第 ${task.profile_version} 版画像摘要` : '查看画像摘要'}</summary><p>{task?.profile_summary || profile.profile.summary}</p></details>{task?.profile_version && task.profile_version !== profile.profile.version && <p className="picks-description">下一次推荐将使用最新第 {profile.profile.version} 版画像，当前任务仍使用原版本。</p>}<button className="primary-button" disabled={busy} onClick={() => void generate()}><span aria-hidden="true">✦</span>{busy ? '正在推荐…' : '开始推荐'}</button></>
          : <><p className="picks-description">{profile?.remaining ? `再记录 ${profile.remaining} 部看过的影片，即可构建首份画像。` : '请先在“我的片库”中构建观影画像。'}</p><button className="quiet-button" onClick={onGoLibrary}>前往我的片库</button></>}
      </section> : <section className="picks-demand-panel" aria-labelledby="demand-heading"><div className="eyebrow"><span />描述观影需求</div><h2 id="demand-heading">描述你此刻想看的电影</h2><p className="picks-description">可以包含年代、国家或地区、类型与观影氛围，本轮只依据这段描述推荐。</p>
        <form onSubmit={submit}><label className="sr-only" htmlFor="demand-input">描述观影需求</label><textarea id="demand-input" value={draft} onChange={event => setDraft(event.target.value)} disabled={busy} rows={4} placeholder="例如：想看一部2010年以后的日本悬疑电影。" /><div className="picks-form-footer"><div><p>试试这些描述</p><div className="picks-examples">{examples.map(([label, text]) => <button key={label} type="button" disabled={busy} onClick={() => setDraft(text)}>{label}</button>)}</div></div><button type="submit" className="primary-button picks-submit" disabled={busy || !draft.trim()}><span aria-hidden="true">✦</span>{busy ? '正在推荐…' : '推荐电影'}</button></div></form>
      </section>}
      {error && <div className="picks-error" role="alert"><p>{error}</p>{queryFailed ? <button className="quiet-button" onClick={() => { setLoading(true); setRefresh(value => value + 1) }}>重新查询</button> : <span>请检查后重新提交。</span>}</div>}
      <section className="picks-results" aria-label="推荐结果" aria-busy={busy}>
        {busy ? <div className="picks-status" role="status"><span className="picks-spinner" aria-hidden="true" /><h2>{loading ? '正在读取推荐结果' : '正在为你寻找电影'}</h2><p>{loading ? '稍候片刻，查看本次推荐的最新状态。' : '正在理解需求、检索并挑选合适的影片，请稍候。'}</p></div>
          : task?.status === 'failed' ? <div className="picks-status picks-failed" role="alert"><span className="picks-status-icon" aria-hidden="true">!</span><h2>这次推荐未能完成</h2><p>{task.error}</p><button className="primary-button" onClick={() => void generate(true)}>重试本次推荐</button></div>
          : task?.status === 'succeeded' ? <><div className="picks-result-heading"><div><div className="eyebrow"><span />{mode === 'personalized' ? '根据观影画像推荐' : '根据本次需求推荐'}</div><h2>为你挑选的 {task.target_count} 部</h2></div></div><p className="picks-request-summary">{mode === 'personalized' ? `本次依据第 ${task.profile_version} 版观影画像` : `本次需求：${task.request_text}`}</p>{task.needs_refresh && <p className="picks-stale" role="status">部分影片已看过或已不再推荐，已从结果中移除。可以重新推荐。</p>}<div className="picks-grid">{task.cards.map((card, index) => <RecommendationCard key={card.movie_id} card={card} index={index} total={task.target_count} />)}</div></>
          : !error && <div className="picks-status picks-empty"><span className="picks-status-icon" aria-hidden="true">▤</span><h2>推荐结果会出现在这里</h2><p>{mode === 'personalized' ? '根据你的观影画像，每次为你挑选 3 部。' : '说说此刻想看的电影，每次为你挑选 3 部。'}</p></div>}
      </section>
  </section>
}
