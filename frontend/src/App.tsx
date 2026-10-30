import { useState } from 'react'
import CatalogPage from './CatalogPage'
import HealthStatus from './HealthStatus'

export default function App() {
  const [page, setPage] = useState<'catalog' | 'health'>('catalog')
  return <div className="app">
    <header className="site-header">
      <button className="brand" onClick={() => setPage('catalog')} aria-label="9万天首页"><span className="brand-mark" aria-hidden="true">▤</span><strong>9万天</strong><span className="brand-caption">AI 电影推荐助手</span></button>
      <nav className="main-nav" aria-label="主导航"><button className={page === 'catalog' ? 'active' : ''} aria-current={page === 'catalog' ? 'page' : undefined} onClick={() => setPage('catalog')}>发现作品</button><button className={page === 'health' ? 'active' : ''} aria-current={page === 'health' ? 'page' : undefined} onClick={() => setPage('health')}>服务状态</button></nav>
      <span className="local-label"><i />本地开发</span>
    </header>
    {page === 'catalog' ? <CatalogPage /> : <HealthStatus />}
  </div>
}
