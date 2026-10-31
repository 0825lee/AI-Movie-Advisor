import { useEffect, useRef } from 'react'
import type { LibraryEntry } from '../library-api'

export default function CommentDialog({ entry, onClose }: { entry: LibraryEntry; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { if (!dialog.current?.open) dialog.current?.showModal() }, [])

  return <dialog ref={dialog} className="comment-dialog" aria-labelledby="comment-title"
    onCancel={event => { event.preventDefault(); onClose() }}
    onClick={event => { if (event.target === dialog.current) onClose() }}>
    <div className="comment-card-heading"><div><p>我的评论</p><h2 id="comment-title">{entry.catalog.title}</h2></div><button className="close-button" aria-label="关闭评论" onClick={onClose}>×</button></div>
    <div className="comment-card-rating">{entry.rating === null ? '未评分' : `${'★'.repeat(entry.rating)} · ${entry.score} 分`}</div>
    <p className={'comment-card-text' + (entry.comment ? '' : ' empty')}>{entry.comment || '暂无评论'}</p>
  </dialog>
}
