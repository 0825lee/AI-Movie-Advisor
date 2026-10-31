import { useState } from 'react'

export default function RatingPicker({ title, busy, comment, onCommentChange, onSubmit, onBack }: {
  title: string; busy: boolean; comment: string; onCommentChange: (value: string) => void
  onSubmit: (rating: number | null) => void; onBack: () => void
}) {
  const [rating, setRating] = useState<number | null>(null)
  return <div className="rating-picker">
    <span className="rating-film-label">看过这部作品</span>
    <h3>{title}</h3>
    <p>记录你的感受，也可以只标记看过。</p>
    <fieldset className="rating-stars" disabled={busy}>
      <legend className="sr-only">选择 1 至 5 星评分</legend>
      {[1, 2, 3, 4, 5].map(stars => <label className={rating !== null && stars <= rating ? 'lit' : ''} key={stars}>
        <input type="radio" name="personal-rating" value={stars} checked={rating === stars} onChange={() => setRating(stars)} />
        <span aria-hidden="true">★</span><span className="sr-only">{stars} 星，{stars * 2} 分</span>
      </label>)}
    </fieldset>
    <div className="rating-value" aria-live="polite">{rating === null ? '尚未选择评分' : `${rating} 星 · ${rating * 2} 分`}</div>
    <label className="comment-input-label" htmlFor="watch-comment">我的评论 <span>选填</span></label>
    <textarea id="watch-comment" className="comment-input" value={comment} disabled={busy} onChange={event => onCommentChange(event.target.value)} placeholder="记录这次观影的感受" rows={4} />
    <button className="skip-rating" disabled={busy} onClick={() => onSubmit(null)}>跳过评分，只标记看过 →</button>
    <div className="rating-actions"><button className="quiet-button" disabled={busy} onClick={onBack}>返回</button><button className="primary-button" disabled={busy || rating === null} onClick={() => onSubmit(rating)}>{busy ? '保存中…' : '保存评分并标记看过'}</button></div>
  </div>
}
