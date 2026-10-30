from typing import Any

import httpx

from app.config import Settings


class TMDBError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message


class TMDBClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http = http
        self.settings = settings
        self._poster_base_url: str | None = None

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        token = self.settings.tmdb_read_access_token
        if token is None:
            raise TMDBError(503, "请先在 backend/.env 配置 TMDB_READ_ACCESS_TOKEN。")
        try:
            response = await self.http.get(
                "https://api.themoviedb.org/3" + path,
                headers={"Authorization": "Bearer " + token.get_secret_value()},
                params={"language": "zh-CN", **params},
                timeout=20,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TMDBError(504, "TMDB 请求超时，请稍后重试。") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                raise TMDBError(404, "TMDB 未找到这部作品或这一季。") from exc
            if status == 429:
                raise TMDBError(503, "TMDB 请求过于频繁，请稍后再试。") from exc
            raise TMDBError(502, f"TMDB 返回 HTTP {status}，请检查凭据或稍后重试。") from exc
        except httpx.RequestError as exc:
            raise TMDBError(502, "无法连接 TMDB，请检查网络后重试。") from exc
        return response.json()

    async def poster_base_url(self) -> str:
        if self._poster_base_url is None:
            config = await self.get("/configuration")
            self._poster_base_url = config["images"]["secure_base_url"] + "w500"
        return self._poster_base_url
