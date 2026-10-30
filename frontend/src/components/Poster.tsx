import { useEffect, useState } from 'react'

export default function Poster({ url, title, className = '' }: { url: string | null; title: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [url])
  return <div className={'poster ' + className}>
    {url && !failed
      ? <img src={url} alt={title + '海报'} loading="lazy" onError={() => setFailed(true)} />
      : <div className="poster-placeholder"><span aria-hidden="true">▤</span><span>暂无海报</span></div>}
  </div>
}
