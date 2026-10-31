import { useEffect, useState } from 'react'
import { api } from '../catalog-api'
import type { ProfileConclusion, ProfileState } from '../profile-api'

function Conclusions({ title, items }: { title: string; items: ProfileConclusion[] }) {
  if (!items.length) return null
  return <section className="profile-conclusions"><h3>{title}</h3>{items.map((item, index) =>
    <details key={index}><summary><span>{item.dimension}</span>{item.label}</summary><p>{item.reason}</p>
      <ul>{item.evidence.map((evidence, i) => <li key={i}><strong>{evidence.title}</strong>{evidence.rating !== null && <span> · {evidence.rating} 分</span>}{evidence.commentExcerpt && <blockquote>{evidence.commentExcerpt}</blockquote>}</li>)}</ul>
    </details>)}</section>
}

export default function ProfilePanel({ revision }: { revision: number }) {
  const [state, setState] = useState<ProfileState | null>(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let active = true
    api<ProfileState>('/profile').then(result => { if (active) { setState(result); setError('') } })
      .catch(reason => { if (active) setError(reason.message) })
    return () => { active = false }
  }, [revision, refresh])
  useEffect(() => {
    if (!state?.generating) return
    const timer = window.setInterval(() => setRefresh(n => n + 1), 2000)
    return () => window.clearInterval(timer)
  }, [state?.generating])

  async function generate(rebuild = false) {
    if (rebuild && !window.confirm('重建会删除旧画像和 Dify 画像会话，使用全部看过记录从第 1 版重新生成。片库保留；若生成失败，需要重试。确认重建？')) return
    setStarting(true); setError('')
    try { setState(await api<ProfileState>(rebuild ? '/profile/rebuild' : '/profile/generate', { method: 'POST' })) }
    catch (reason) { setError((reason as Error).message) }
    finally { setStarting(false) }
  }

  const profile = state?.profile
  const busy = starting || state?.generating
  const failed = state?.job && ['failed', 'cancelled'].includes(state.job.status)
  return <aside className="profile-panel" aria-labelledby="profile-title" aria-busy={Boolean(busy)}>
    <div className="eyebrow"><span />画像构建</div><h2 id="profile-title">我的观影画像</h2><p className="profile-subtitle">基于看过的影片生成</p>
    {profile ? <>
      <div className="profile-version"><span>第 {profile.version} 版 · 覆盖 {profile.covered_count} 部</span><time>{state?.created_at ? new Date(state.created_at * 1000).toLocaleString('zh-CN') : ''}</time></div>
      <section className="profile-live-summary"><h3>口味总结</h3><p>{profile.summary}</p></section>
    </> : <div className="profile-pending"><svg aria-hidden="true" width="44" height="44" viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="8" y="8" width="32" height="32" rx="9" /><circle cx="18" cy="20" r="1" fill="currentColor" /><circle cx="30" cy="20" r="1" fill="currentColor" /><path d="M17 29c4 4 10 4 14 0" /></svg><h3>{busy ? '正在构建观影画像' : '暂无观影画像'}</h3></div>}
    <div className="profile-records"><div><span>已记录看过</span><strong>{state?.watched_count ?? '—'}<small> 部</small></strong></div><span className="profile-record-icon" aria-hidden="true">▤</span></div>
    <div className="profile-progress"><div><span>{profile ? '新观影记录积累' : '观影记录积累'}</span><span>{state ? `${state.pending_count} / 50` : '—'}</span></div><progress max="50" value={Math.min(state?.pending_count ?? 0, 50)} aria-label="距下一版画像所需的观影记录" /><p>{state ? state.remaining > 0 ? `再记录 ${state.remaining} 部看过的影片后${profile ? '更新' : '生成'}画像。` : busy ? state.job?.stage === 'uploading' ? '正在上传本批观影记录…' : 'AI 正在分析，请稍候。' : '已满足画像生成条件。' : '正在读取画像状态…'}</p></div>
    {error && <p className="profile-error" role="alert">{error}<button className="text-button" onClick={() => setRefresh(n => n + 1)}>重新加载</button></p>}
    {failed && <p className="profile-error" role="alert">{state.job?.error}{profile ? ' 当前仍显示上一版画像。' : ''}</p>}
    {state && !state.configured && <p className="profile-error">画像服务尚未配置。</p>}
    <button className="primary-button profile-generate" disabled={!state || !state.configured || Boolean(busy) || state.remaining > 0} onClick={() => void generate()}>{busy ? '画像生成中…' : failed ? '重试生成' : profile ? '更新画像' : '生成观影画像'}</button>
    {state && (profile || state.job) && <button className="text-button profile-rebuild" disabled={!state.configured || Boolean(busy) || state.watched_count < 50} onClick={() => void generate(true)}>重建画像</button>}
    {profile && <><Conclusions title="主要偏好" items={profile.preferences} /><Conclusions title="较少偏好" items={profile.less_preferred} /><Conclusions title="近期变化" items={profile.recent_changes} />{profile.limitations.length > 0 && <details className="profile-limitations"><summary>画像依据说明</summary><ul>{profile.limitations.map((text, i) => <li key={i}>{text}</li>)}</ul></details>}</>}
    <p className="profile-quote">In this terrifying world, all we have are the connections that we make.</p>
  </aside>
}
