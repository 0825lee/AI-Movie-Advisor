import asyncio
import re
import time
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.catalog_models import CatalogItem, SourceMapping
from app.catalog_schemas import (
    CatalogCandidate, CatalogDetail, CatalogPage, CatalogRef, ConfirmRequest,
    MatchRequest, MatchResult, SearchResult, SearchType,
)
from app.tmdb_client import TMDBClient, TMDBError

CACHE_SECONDS = 7 * 24 * 60 * 60


def date_year(value: str | None) -> int | None:
    return int(value[:4]) if value else None


def normalized_name(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def parse_title(title: str) -> tuple[str, int | None, int | None]:
    """仅提取明确标记的年份和季号，不把片名中的普通数字当作年份。"""
    title = unicodedata.normalize("NFKC", title).strip()
    year_match = re.search(r"\s*\(((?:18|19|20)\d{2})\)\s*$", title)
    year = int(year_match[1]) if year_match else None
    if year_match:
        title = title[:year_match.start()].strip()
    season_match = re.search(r"\s*(?:第(\d+|[一二两三四五六七八九]?十[一二三四五六七八九]?|[零〇一二两三四五六七八九])季|season\s*(\d+)|\bS(\d{1,2}))\s*$", title, re.I)
    season = None
    if season_match:
        value = next(v for v in season_match.groups() if v is not None)
        if value.isdigit():
            season = int(value)
        else:
            digits = dict(zip("零〇一二两三四五六七八九", [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))
            if "十" in value:
                left, right = value.split("十")
                season = (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
            else:
                season = digits[value]
        title = title[:season_match.start()].rstrip(" ·-—:")
    return title, year, season


def serialized(item: CatalogItem) -> CatalogDetail:
    return CatalogDetail(
        **item.details, catalog_id=item.id,
        confirmed=item.confirmed_at is not None, fetched_at=item.fetched_at,
    )


def name_year_key(original_title: str, title: str, year: int | None, season_number: int | None = None) -> str | None:
    if year is None:
        return None
    name, _, parsed_season = parse_title(original_title or title)
    season = season_number if season_number is not None else parsed_season
    key = f"{normalized_name(name)}:{year}"
    return key if season is None else f"{key}:season:{season}"


def season_presentation(series: dict, season_number: int, season_name: str) -> dict:
    single = season_number > 0 and sum(s["season_number"] > 0 for s in series["seasons"]) == 1
    return dict(
        single_season=single,
        title=series["title"] if single else series["title"] + " · " + season_name,
        original_title=series["original_title"] if single else series["original_title"] + f" · Season {season_number}",
        tmdb_url=series["tmdb_url"] if single else f"https://www.themoviedb.org/tv/{series['tmdb_id']}/season/{season_number}",
    )


class CatalogService:
    def __init__(self, engine: Engine, tmdb: TMDBClient):
        self.engine = engine
        self.tmdb = tmdb

    async def search(
        self, query: str, media_type: SearchType = "all", year: int | None = None, page: int = 1,
        *, expand_seasons: bool = True,
    ) -> SearchResult:
        series_query, _, requested_season = parse_title(query)
        types = ["movie", "tv"] if media_type == "all" else [media_type]
        if expand_seasons and requested_season is not None and media_type != "movie":
            types = ["tv"]
        responses = await asyncio.gather(*[
            self.tmdb.get(
                f"/search/{kind}",
                query=series_query if kind == "tv" and expand_seasons and requested_season is not None else query.strip(),
                page=page, include_adult="false",
                **({"year": year} if year is not None and (kind == "movie" or not expand_seasons) else {}),
            ) for kind in types
        ])
        poster_base = await self.tmdb.poster_base_url()
        items = []
        for kind, response in zip(types, responses):
            for data in response["results"]:
                items.append(CatalogCandidate(
                    media_type=kind, tmdb_id=data["id"],
                    title=data["title"] if kind == "movie" else data["name"],
                    original_title=data["original_title"] if kind == "movie" else data["original_name"],
                    year=date_year(data.get("release_date") if kind == "movie" else data.get("first_air_date")),
                    overview=data.get("overview") or "",
                    poster_url=poster_base + data["poster_path"] if data.get("poster_path") else None,
                ))
        name = normalized_name(series_query if requested_season is not None else query)
        items.sort(key=lambda item: normalized_name(item.title) != name and normalized_name(item.original_title) != name)
        if expand_seasons:
            groups = await asyncio.gather(*[self.season_candidates(item) for item in items])
            items = [item for group in groups for item in group]
            if requested_season is not None:
                items = [item for item in items if item.media_type == "movie" or item.season_number == requested_season]
            if year is not None:
                items = [item for item in items if item.year == year]
        return SearchResult(items=items, page=page, total_pages=max(r["total_pages"] for r in responses))

    async def season_candidates(self, candidate: CatalogCandidate) -> list[CatalogCandidate]:
        if candidate.media_type == "movie":
            return [candidate]
        series = await self.detail(candidate)
        return [CatalogCandidate(
            media_type="season", tmdb_id=series.tmdb_id, season_number=season.season_number,
            **season_presentation(series.model_dump(), season.season_number, season.name),
            year=season.year, poster_url=season.poster_url,
        ) for season in sorted(series.seasons, key=lambda s: (s.season_number == 0, s.season_number))]

    async def detail(self, ref: CatalogRef, refresh: bool = False) -> CatalogDetail:
        ref = CatalogRef(media_type=ref.media_type, tmdb_id=ref.tmdb_id, season_number=ref.season_number)
        with Session(self.engine) as session:
            cached = session.scalar(select(CatalogItem).where(CatalogItem.identity_key == ref.identity_key))
            if cached and not refresh and int(time.time()) - cached.fetched_at < CACHE_SECONDS:
                return serialized(cached)

        # 远程请求完成后再打开写事务。
        data = await self.fetch_detail(ref)
        values = dict(
            identity_key=ref.identity_key, media_type=ref.media_type,
            tmdb_id=ref.tmdb_id, season_number=ref.season_number,
            title=data["title"], original_title=data["original_title"], year=data["year"],
            match_key=name_year_key(data["original_title"], data["title"], data["year"], None if data.get("single_season") else ref.season_number),
            details=data, fetched_at=int(time.time()),
        )
        statement = insert(CatalogItem).values(**values).on_conflict_do_update(
            index_elements=["identity_key"],
            set_={key: value for key, value in values.items() if key != "identity_key"},
        )
        with Session(self.engine) as session:
            session.execute(statement)
            session.commit()
            return serialized(session.scalar(select(CatalogItem).where(CatalogItem.identity_key == ref.identity_key)))

    async def fetch_detail(self, ref: CatalogRef) -> dict:
        is_movie = ref.media_type == "movie"
        is_season = ref.media_type == "season"
        parent = None
        if is_season:
            parent = await self.detail(CatalogRef(media_type="tv", tmdb_id=ref.tmdb_id))
            path = f"/tv/{ref.tmdb_id}/season/{ref.season_number}"
            extra = "aggregate_credits"
        else:
            path = f"/{ref.media_type}/{ref.tmdb_id}"
            extra = "credits,alternative_titles" if is_movie else "aggregate_credits,alternative_titles"
        data = await self.tmdb.get(path, append_to_response=extra)
        overview = data.get("overview") or ""
        overview_language = "zh-CN" if overview else None
        if not overview:
            english = await self.tmdb.get(path, language="en-US")
            overview = english.get("overview") or ""
            overview_language = "en-US" if overview else None
        poster_base = await self.tmdb.poster_base_url()
        poster_path = data.get("poster_path")
        credits = data.get("credits" if is_movie else "aggregate_credits", {})
        directors = [
            {"id": person["id"], "name": person["name"]}
            for person in credits.get("crew", [])
            if person.get("job") == "Director" or any(job["job"] == "Director" for job in person.get("jobs", []))
        ]
        title = data["title"] if is_movie else data["name"]
        original_title = data["original_title"] if is_movie else data.get("original_name", "")
        presentation = {}
        if is_season:
            presentation = season_presentation(parent.model_dump(), ref.season_number, title)
            title, original_title = presentation["title"], presentation["original_title"]
        aliases = data.get("alternative_titles", {})
        return dict(
            **ref.model_dump(), title=title, original_title=original_title,
            year=date_year(data.get("release_date") if is_movie else data.get("air_date") if is_season else data.get("first_air_date")),
            overview=overview, overview_language=overview_language,
            original_language=parent.original_language if is_season else data["original_language"],
            poster_path=poster_path, poster_url=poster_base + poster_path if poster_path else None,
            runtime=data.get("runtime") if is_movie else next(iter(data.get("episode_run_time", [])), None),
            genres=[g.model_dump() for g in parent.genres] if is_season else data.get("genres", []),
            countries=[c.model_dump() for c in parent.countries] if is_season else data.get("production_countries", []),
            directors=directors,
            creators=[c.model_dump() for c in parent.creators] if is_season else [{"id": p["id"], "name": p["name"]} for p in data.get("created_by", [])],
            cast=[{"id": p["id"], "name": p["name"]} for p in credits.get("cast", [])[:2]],
            seasons=[dict(
                season_number=season["season_number"], name=season["name"],
                year=date_year(season.get("air_date")), episode_count=season["episode_count"],
                poster_url=poster_base + season["poster_path"] if season.get("poster_path") else None,
            ) for season in data.get("seasons", [])],
            episode_count=len(data["episodes"]) if is_season else data.get("number_of_episodes"),
            alternative_titles=[a["title"] for a in aliases.get("titles", aliases.get("results", []))],
            tmdb_url=presentation.get("tmdb_url", f"https://www.themoviedb.org{path}"),
            single_season=presentation.get("single_season", False),
        )

    async def confirm(self, body: ConfirmRequest) -> CatalogDetail:
        detail = await self.detail(body)
        with Session(self.engine) as session:
            item = session.get(CatalogItem, detail.catalog_id)
            if body.source:
                source = body.source
                mapping = session.scalar(select(SourceMapping).where(
                    SourceMapping.source == source.source, SourceMapping.source_id == source.source_id,
                ))
                if mapping and mapping.catalog_item_id != item.id:
                    raise TMDBError(409, "这个来源条目已对应其他作品，请先核对匹配结果。")
                if mapping is None:
                    session.add(SourceMapping(**source.model_dump(), catalog_item_id=item.id))
            if item.confirmed_at is None:
                item.confirmed_at = int(time.time())
            session.commit()
            return serialized(item)

    def confirmed_items(self, page: int = 1) -> CatalogPage:
        with Session(self.engine) as session:
            condition = CatalogItem.confirmed_at.is_not(None) & CatalogItem.tmdb_id.is_not(None)
            total = session.scalar(select(func.count()).select_from(CatalogItem).where(condition))
            items = session.scalars(select(CatalogItem).where(condition).order_by(
                CatalogItem.confirmed_at.desc(), CatalogItem.id.desc(),
            ).offset((page - 1) * 24).limit(24))
            return CatalogPage(items=[serialized(item) for item in items], total=total, page=page)

    async def match(self, body: MatchRequest) -> MatchResult:
        if body.source:
            with Session(self.engine) as session:
                item = session.scalar(select(CatalogItem).join(SourceMapping).where(
                    SourceMapping.source == body.source.source,
                    SourceMapping.source_id == body.source.source_id,
                ))
                if item:
                    return MatchResult(status="matched", reason="复用已确认的来源映射。", item=serialized(item))
        title, parsed_year, parsed_season = parse_title(body.title)
        year = body.year if body.year is not None else parsed_year
        season = body.season_number if body.season_number is not None else parsed_season
        is_season = body.media_type == "season" or season is not None
        if is_season and season is None:
            return MatchResult(status="missing_data", reason="单季作品需要明确季号。")
        search_type = "tv" if is_season else body.media_type
        query_names = list(dict.fromkeys([title, *([parse_title(body.original_title)[0]] if body.original_title else [])]))
        # 匹配服务先识别父剧集，再核对指定季；前台搜索则直接展示每季。
        results = await asyncio.gather(*[self.search(name, search_type, expand_seasons=False) for name in query_names])
        candidates = {item.identity_key: item for result in results for item in result.items}
        if not candidates:
            return MatchResult(status="not_found", reason="未找到候选作品。")
        names = {normalized_name(name) for name in query_names}
        exact = [item for item in candidates.values() if names.intersection({normalized_name(item.title), normalized_name(item.original_title)})]
        if not exact:
            # 搜索可能通过别名命中；只核对同年份候选的已知别名。
            for item in candidates.values():
                if year is not None and (is_season or item.year == year):
                    detail = await self.detail(item)
                    if names.intersection(normalized_name(alias) for alias in detail.alternative_titles):
                        exact.append(item)
        if is_season:
            seasons = []
            for item in exact:
                series = await self.detail(item)
                season_info = next((s for s in series.seasons if s.season_number == season), None)
                if season_info:
                    seasons.append(CatalogCandidate(
                        media_type="season", tmdb_id=item.tmdb_id, season_number=season,
                        title=item.title + " · " + season_info.name,
                        original_title=item.original_title + f" · Season {season}",
                        year=season_info.year, poster_url=season_info.poster_url,
                    ))
            exact = seasons
            if not exact:
                return MatchResult(status="not_found", reason="候选剧集中未找到指定季号。", candidates=list(candidates.values()))
        reliable = [item for item in exact if year is not None and item.year == year]
        if len(reliable) == 1:
            return MatchResult(status="matched", reason="名称、年份和作品身份唯一吻合。", item=await self.detail(reliable[0]))
        if year is None and exact:
            return MatchResult(status="missing_data", reason="缺少年份，需补充年份或手动确认候选。", candidates=exact)
        return MatchResult(status="ambiguous", reason="候选无法唯一确认，请人工核对名称、年份和季号。", candidates=exact or list(candidates.values()))
