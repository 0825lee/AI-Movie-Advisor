import { useEffect, useRef, useState } from 'react'
import { api } from '../catalog-api'
import { outcomeLabels, statusLabels } from '../import-api'
import type { DoubanFile, ImportOutcome, ImportRowsPage, ImportSummary } from '../import-api'

type Props = {
  open: boolean; libraryCount: number; onClose: () => void
  onChanged: () => void; onRunningChange: (running: boolean) => void
}

export default function ImportDialog({ open, libraryCount, onClose, onChanged, onRunningChange }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [filename, setFilename] = useState('')
  const [payload, setPayload] = useState<DoubanFile | null>(null)
  const [job, setJob] = useState<ImportSummary | null>(null)
  const [history, setHistory] = useState<ImportSummary[]>([])
  const [rows, setRows] = useState<ImportRowsPage | null>(null)
  const [outcome, setOutcome] = useState<'all' | ImportOutcome>('all')
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [rowsError, setRowsError] = useState('')
  const running = job?.status === 'running'

  useEffect(() => {
    api<ImportSummary[]>('/imports').then(jobs => { setHistory(jobs); setJob(jobs[0] ?? null) }).catch(reason => setError(reason.message))
  }, [])
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal()
    if (!open && dialog.current?.open) dialog.current.close()
  }, [open])
  useEffect(() => {
    if (open && job) api<ImportSummary>('/imports/' + job.id).then(setJob).catch(reason => setError(reason.message))
  }, [open, job?.id])
  useEffect(() => { onRunningChange(running) }, [running, onRunningChange])
  useEffect(() => { if (job) onChanged() }, [job?.id, job?.processed, job?.status, onChanged])
  useEffect(() => {
    if (!job || job.status !== 'running') return
    const timer = window.setInterval(() => {
      api<ImportSummary>('/imports/' + job.id).then(result => { setJob(result); setError('') }).catch(reason => setError(reason.message))
    }, 2000)
    return () => window.clearInterval(timer)
  }, [job?.id, job?.status])
  useEffect(() => {
    if (!open || !job) return
    let active = true
    api<ImportRowsPage>(`/imports/${job.id}/rows?outcome=${outcome}&page=${page}`)
      .then(result => { if (active) { setRows(result); setRowsError('') } })
      .catch(reason => { if (active) setRowsError(reason.message) })
    return () => { active = false }
  }, [open, job?.id, job?.processed, outcome, page])

  async function readFile(file: File) {
    setError(''); setBusy(true)
    try {
      const data = JSON.parse(await file.text()) as DoubanFile
      if (!Array.isArray(data.records)) throw new Error('JSON 中需要包含 records 数组。')
      setPayload(data); setFilename(file.name); setJob(null); setRows(null); setOutcome('all'); setPage(1)
    } catch { setPayload(null); setError('文件无法读取，请选择包含 records 数组的豆瓣 JSON 文件。') }
    finally { setBusy(false) }
  }
  async function start() {
    if (!payload) return
    setBusy(true); setError('')
    try {
      const result = await api<ImportSummary>('/imports', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ filename, data: payload }),
      })
      setJob(result); setHistory(jobs => [result, ...jobs].slice(0, 10)); setPayload(null); setOutcome('all'); setPage(1)
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  async function action(kind: 'pause' | 'resume') {
    if (!job) return
    setBusy(true); setError('')
    try { setJob(await api<ImportSummary>(`/imports/${job.id}/${kind}`, { method: 'POST' })) }
    catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  async function clearLibrary() {
    if (!window.confirm('清空片库会移除全部想看、看过、评分、评论和画像输入记录。确认清空？')) return
    setBusy(true); setError('')
    try {
      await api('/library', { method: 'DELETE' }); onChanged()
      if (job) setJob(await api<ImportSummary>('/imports/' + job.id))
    } catch (reason) { setError((reason as Error).message) }
    finally { setBusy(false) }
  }
  const preview = payload ? {
    total: payload.records.length,
    watched: payload.records.filter(r => r?.status === 'collect').length,
    wish: payload.records.filter(r => r?.status === 'wish').length,
    rated: payload.records.filter(r => r?.status === 'collect' && r?.stars != null).length,
  } : null
  const totalPages = rows ? Math.ceil(rows.total / rows.page_size) : 0

  return <dialog ref={dialog} className="detail-dialog import-dialog" aria-labelledby="import-title" onCancel={event => { event.preventDefault(); onClose() }} onClick={event => { if (event.target === dialog.current) onClose() }}>
    <div className="detail-shell">
      <div className="work-dialog-heading"><div><h2 id="import-title">导入豆瓣记录</h2><p>将想看、看过和个人星级带入你的片库</p></div><button className="close-button" aria-label="关闭导入窗口" onClick={onClose}>×</button></div>
      {error && <div className="notice error-message" role="alert">{error}</div>}
      {!running && <label className={'import-file-zone ' + (busy ? 'busy' : '')} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!busy && event.dataTransfer.files[0]) void readFile(event.dataTransfer.files[0]) }}>
        <input type="file" accept=".json,application/json" disabled={busy} onChange={event => { if (event.target.files?.[0]) void readFile(event.target.files[0]); event.target.value = '' }} />
        <span className="file-zone-icon" aria-hidden="true">↥</span><strong>{payload ? filename : '选择豆瓣 JSON 文件'}</strong><span>{payload ? '点击可重新选择文件' : '点击选择，或将文件拖放到这里'}</span>
      </label>}
      {preview && <section className="import-preview" aria-label="文件概况"><div><strong>{preview.total}</strong><span>条记录</span></div><div><strong>{preview.watched}</strong><span>看过</span></div><div><strong>{preview.wish}</strong><span>想看</span></div><div><strong>{preview.rated}</strong><span>已评分</span></div></section>}
      {payload && <div className="import-start-row"><div>{libraryCount > 0 ? <><p>当前片库有 {libraryCount} 条记录，清空后可开始导入。</p><button className="text-button" disabled={busy} onClick={() => void clearLibrary()}>清空片库</button></> : <p>片库为空，可以开始导入。</p>}</div><button className="primary-button" disabled={busy || libraryCount > 0 || !preview?.total} onClick={() => void start()}>{busy ? '处理中…' : '开始导入'}</button></div>}
      {history.length > 0 && !payload && <div className="import-history"><label htmlFor="import-history">最近导入</label><select id="import-history" value={job?.id ?? ''} disabled={running || busy} onChange={event => { const selected = history.find(item => item.id === Number(event.target.value)); if (selected) { setJob(selected); setRows(null); setPage(1); setOutcome('all'); void api<ImportSummary>('/imports/' + selected.id).then(setJob).catch(reason => setError(reason.message)) } }}>{history.map(item => <option key={item.id} value={item.id}>{item.filename} · #{item.id}</option>)}</select></div>}
      {job && <section className="import-progress-panel" aria-label="导入进度">
        <div className="import-progress-heading"><div><h3>{job.filename}</h3><span className={'import-status ' + job.status}>{statusLabels[job.status]}</span></div><strong>{job.processed} <span>/ {job.total}</span></strong></div>
        <progress max={job.total || 1} value={job.processed} aria-label="已处理导入记录" />
        {running && <p className="import-current" role="status">正在处理：{job.current_title || '整理导入结果…'}</p>}
        {job.message && <p className="import-job-message" role="status">{job.message}</p>}
        <div className="import-counts">{(['added', 'upgraded', 'duplicate', 'skipped', 'failed'] as const).map(key => <div key={key}><strong>{job.counts[key]}</strong><span>{outcomeLabels[key]}</span></div>)}</div>
        <div className="import-task-actions"><span>{running ? '关闭窗口后仍会继续导入' : job.status === 'completed' ? '导入结束，片库已更新' : job.status === 'paused' ? '已完成的记录会保留，继续时接着处理' : '可选择文件创建新任务'}</span>{running ? <button className="quiet-button" disabled={busy} onClick={() => void action('pause')}>暂停导入</button> : job.status === 'paused' && <button className="primary-button" disabled={busy} onClick={() => void action('resume')}>继续导入</button>}</div>
        <div className="import-results-heading"><h3>处理明细</h3><select aria-label="筛选导入结果" value={outcome} onChange={event => { setOutcome(event.target.value as typeof outcome); setPage(1) }}><option value="all">全部结果</option>{Object.entries(outcomeLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></div>
        {rowsError && <p className="import-job-message" role="alert">{rowsError}</p>}
        <div className="import-table-wrap"><table className="import-results"><thead><tr><th>序号</th><th>作品名称</th><th>结果</th><th>说明</th></tr></thead><tbody>{rows?.items.map(row => <tr key={row.row_number}><td>{row.row_number}</td><td><strong>{row.title}</strong>{row.matched_title && row.matched_title !== row.title && <span>{row.matched_title}</span>}</td><td><span className={'row-outcome ' + row.outcome}>{outcomeLabels[row.outcome]}</span></td><td>{row.message || '等待处理'}</td></tr>)}</tbody></table></div>
        {rows && <div className="pagination import-results-pages"><button className="quiet-button" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button><span>{rows.total ? `${page} / ${totalPages}` : '暂无记录'}</span><button className="quiet-button" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button></div>}
      </section>}
    </div>
  </dialog>
}
