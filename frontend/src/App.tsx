import { useState } from 'react'
import LibraryPage from './LibraryPage'
import HealthStatus from './HealthStatus'

export default function App() {
  const [page, setPage] = useState<'library' | 'health'>('library')
  return <div className="app library-app">
    <header className="site-header library-header">
      <button className="brand" onClick={() => setPage('library')} aria-label="9万天首页"><span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="21" height="21" fill="currentColor"><path d="M4 3a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1H4Zm1 2h2v3H5V5Zm0 5h2v4H5v-4Zm0 6h2v3H5v-3Zm12-11h2v3h-2V5Zm0 5h2v4h-2v-4Zm0 6h2v3h-2v-3ZM9 5h6v14H9V5Z" /></svg></span><strong>9万天</strong></button>
      <nav className="main-nav prototype-nav" aria-label="主导航"><button className={page === 'library' ? 'active' : ''} aria-current={page === 'library' ? 'page' : undefined} onClick={() => setPage('library')}>我的片库</button><button disabled title="AI选片即将开放">AI选片</button></nav>
      <button className={'service-link ' + (page === 'health' ? 'active' : '')} onClick={() => setPage('health')}>服务状态</button>
    </header>
    {page === 'library' ? <LibraryPage /> : <HealthStatus />}
  </div>
}
