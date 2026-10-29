"""Create local configuration once, without printing its token."""

from pathlib import Path
import secrets

backend = Path(__file__).resolve().parents[1]
target = backend / ".env"

if target.exists():
    print("保留已有 backend/.env。")
else:
    content = (backend / ".env.example").read_text(encoding="utf-8")
    content = content.replace(
        "MOVIE_INTERNAL_TOKEN=\n",
        "MOVIE_INTERNAL_TOKEN=" + secrets.token_urlsafe(32) + "\n",
    )
    target.write_text(content, encoding="utf-8", newline="\n")
    print("已创建 backend/.env 并生成内部令牌；请在本机填写 Dify 和 TMDB 凭据。")
