import { useEffect, useState } from 'react'

type Health = {
  status: 'ok'
  database: 'ok'
  database_revision: string
  dify_configured: boolean
  tmdb_configured: boolean
}

export default function App() {
  const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
  const [health, setHealth] = useState<Health | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function refresh() {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/health')
      if (!response.ok) {
        const detail = response.status === 503
          ? '数据库尚未就绪，请先执行迁移。'
          : '请确认 FastAPI 已启动，且前端配置的地址正确。'
        throw new Error('健康检查返回 HTTP ' + response.status + '。' + detail)
      }
      setHealth(await response.json() as Health)
    } catch (reason) {
      setHealth(null)
      setError(reason instanceof Error ? reason.message : '连接失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  const connected = !loading && health !== null
  return (
    <div className="app">
      <header className="site-header">
        <a className="brand" href="/" aria-label="9万天首页">
          <span className="brand-mark" aria-hidden="true">▤</span>
          <strong>9万天</strong>
          <span className="brand-caption">AI 电影推荐助手</span>
        </a>
        <span className="local-label"><i />本地开发</span>
      </header>

      <main>
        <div className="eyebrow"><span />工程准备 · 01</div>
        <div className="page-heading">
          <div>
            <h1>连接真实数据，<br />开始下一场电影。</h1>
            <p>先打通网站与服务，再逐步接入片库、画像和推荐。</p>
          </div>
          <button className="refresh-button" disabled={loading} onClick={() => void refresh()}>
            <span aria-hidden="true">↻</span>{loading ? '检查中…' : '重新检查'}
          </button>
        </div>

        <section className="connection-panel" aria-labelledby="connection-title" aria-busy={loading}>
          <div className="panel-heading">
            <div>
              <div className="small-label">CONNECTION STATUS</div>
              <h2 id="connection-title">基础服务</h2>
            </div>
            <span className={'status-pill ' + (connected ? 'success' : loading ? 'pending' : 'failure')} role="status">
              <i />{loading ? '正在连接' : connected ? '后端与数据库已连接' : '等待服务就绪'}
            </span>
          </div>

          {error && <div className="error-message" role="alert">{error}</div>}

          <div className="service-grid">
            <article className="service-card">
              <div className="service-number">01</div>
              <h3>FastAPI</h3>
              <p>业务接口</p>
              <div className={'service-state ' + (connected ? 'good' : '')}>
                <i />{loading ? '检查中' : connected ? '运行正常' : '未连接'}
              </div>
              <code>{backendUrl.replace('http://', '')}</code>
            </article>
            <article className="service-card">
              <div className="service-number">02</div>
              <h3>SQLite</h3>
              <p>本地持久化</p>
              <div className={'service-state ' + (connected ? 'good' : '')}>
                <i />{loading ? '检查中' : connected ? '读取成功' : '待检查'}
              </div>
              <code>{connected ? '迁移版本 ' + health.database_revision : '数据库随后端检查'}</code>
            </article>
            <article className="service-card">
              <div className="service-number">03</div>
              <h3>Dify</h3>
              <p>AI 工作流</p>
              <div className="service-state">
                <i />{!connected ? '待检查' : health.dify_configured ? '凭据已填写' : '待填写应用 Key'}
              </div>
              <code>localhost:18080</code>
            </article>
            <article className="service-card">
              <div className="service-number">04</div>
              <h3>TMDB</h3>
              <p>电影资料</p>
              <div className="service-state">
                <i />{!connected ? '待检查' : health.tmdb_configured ? '凭据已填写' : '待填写访问令牌'}
              </div>
              <code>电影、海报与简介</code>
            </article>
          </div>
          <p className="panel-note">后端与数据库状态来自实际查询；Dify 和 TMDB 此处仅显示凭据配置状态，调用结果需单独验证。</p>
        </section>

        <section className="next-step">
          <span className="step-index">NEXT</span>
          <div>
            <h2>接下来，建立你的真实片库。</h2>
            <p>保留现有原型的布局，逐步替换模拟数据。先完成作品匹配，再接入导入与 AI 选片。</p>
          </div>
          <span className="step-arrow" aria-hidden="true">↗</span>
        </section>

        <footer>
          <span>9万天 · 私人观影记录与选片</span>
          <div>
            <a href={backendUrl + '/docs'} target="_blank" rel="noreferrer">后端接口 ↗</a>
            <a href="http://localhost:18080" target="_blank" rel="noreferrer">Dify 控制台 ↗</a>
          </div>
        </footer>
      </main>
    </div>
  )
}
