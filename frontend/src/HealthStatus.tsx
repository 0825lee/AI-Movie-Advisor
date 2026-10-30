import { useEffect, useState } from 'react'
import { api } from './catalog-api'

type Health = { database_revision: string; dify_configured: boolean; tmdb_configured: boolean }

export default function HealthStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
  async function refresh() {
    setLoading(true); setError('')
    try { setHealth(await api<Health>('/health')) }
    catch (reason) { setHealth(null); setError((reason as Error).message) }
    finally { setLoading(false) }
  }
  useEffect(() => { void refresh() }, [])
  const connected = !loading && health !== null
  const services = [
    { name: 'FastAPI', description: '业务接口', state: connected ? '运行正常' : '未连接', note: backendUrl.replace('http://', ''), good: connected },
    { name: 'SQLite', description: '本地持久化', state: connected ? '读取成功' : '待检查', note: connected ? '迁移版本 ' + health.database_revision : '数据库随后端检查', good: connected },
    { name: 'Dify', description: 'AI 工作流', state: !connected ? '待检查' : health.dify_configured ? '凭据已填写' : '待填写应用 Key', note: 'localhost:18080', good: false },
    { name: 'TMDB', description: '电影资料', state: !connected ? '待检查' : health.tmdb_configured ? '凭据已填写' : '待填写访问令牌', note: '电影、海报与简介', good: false },
  ]
  return <main>
    <div className="eyebrow"><span />基础服务</div>
    <div className="page-heading"><div><h1>服务连接状态</h1><p>后端与数据库状态来自实际查询。</p></div><button className="refresh-button" disabled={loading} onClick={() => void refresh()}>{loading ? '检查中…' : '↻ 重新检查'}</button></div>
    <section className="connection-panel" aria-busy={loading}>
      <div className="panel-heading"><h2>基础服务</h2><span className={'status-pill ' + (connected ? 'success' : 'pending')} role="status">{loading ? '正在连接' : connected ? '后端与数据库已连接' : '等待服务就绪'}</span></div>
      {error && <div className="error-message" role="alert">{error}</div>}
      <div className="service-grid">{services.map((service, i) => <article className="service-card" key={service.name}>
        <div className="service-number">0{i + 1}</div><h3>{service.name}</h3><p>{service.description}</p><div className={'service-state ' + (service.good ? 'good' : '')}><i />{loading ? '检查中' : service.state}</div><code>{service.note}</code>
      </article>)}</div>
      <p className="panel-note">Dify 和 TMDB 此处仅显示凭据配置状态，调用结果需单独验证。</p>
    </section>
    <footer><span>9万天 · 私人观影记录与选片</span><div><a href={backendUrl + '/docs'} target="_blank" rel="noreferrer">后端接口 ↗</a><a href="http://localhost:18080" target="_blank" rel="noreferrer">Dify 控制台 ↗</a></div></footer>
  </main>
}
