import { countryNames } from '../library-api'
import type { RecommendationCardData } from '../recommendation-api'
import Poster from './Poster'

export default function RecommendationCard({ card, index, total, disabled, onWish, onBlock }: {
  card: RecommendationCardData; index: number; total: number; disabled?: boolean
  onWish: () => void; onBlock: () => void
}) {
  const movie = card.movie
  const metadata = [movie.year, countryNames(movie), movie.runtime ? `${movie.runtime} 分钟` : ''].filter(Boolean).join(' · ')
  return <article className="pick-card">
    <div className="pick-card-top"><span>{String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span><span>为此刻挑选</span></div>
    <div className="pick-film-heading">
      <a className="pick-poster-link" href={movie.tmdb_url} target="_blank" rel="noreferrer" aria-label={`在 TMDB 查看《${movie.title}》`}><Poster url={movie.poster_url} title={movie.title} /></a>
      <div className="pick-film-title"><div className="pick-genres">{movie.genres.map(genre => <span key={genre.id ?? genre.name}>{genre.name}</span>)}</div><h3><a href={movie.tmdb_url} target="_blank" rel="noreferrer">{movie.title}</a></h3>{movie.original_title !== movie.title && <p className="pick-original-title">{movie.original_title}</p>}<p className="pick-metadata">{metadata}</p></div>
    </div>
    <dl className="pick-credits"><div><dt>导演</dt><dd>{movie.directors.map(person => person.name).join(' / ') || '暂无资料'}</dd></div><div><dt>主演</dt><dd>{movie.cast.map(person => person.name).join(' / ') || '暂无资料'}</dd></div></dl>
    <div className="pick-overview"><h4>剧情简介</h4><p>{movie.overview || '暂无简介'}</p></div>
    <section className="pick-reason"><h4><span aria-hidden="true">✦</span> 推荐理由</h4><p>{card.reason}</p></section>
    <div className="pick-actions"><button className="quiet-button" disabled={disabled || card.library_status !== null} onClick={onWish}>{card.library_status === 'watched' ? '已看过' : card.library_status === 'wish' ? '已加入想看' : '＋ 加入想看'}</button><button className="text-button" disabled={disabled} onClick={onBlock}>不感兴趣</button></div>
    <a className="pick-source-link" href={movie.tmdb_url} target="_blank" rel="noreferrer">在 TMDB 查看 <span aria-hidden="true">↗</span></a>
  </article>
}
