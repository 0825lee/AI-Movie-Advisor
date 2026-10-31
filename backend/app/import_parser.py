import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.catalog_service import parse_title
from app.douban_metadata import parse_info, release_years

IMPORT_FIELDS = ("title", "originalTitle", "info", "status", "stars", "rating", "markedAt", "comment", "subjectId", "url")
SHANGHAI = timezone(timedelta(hours=8))


@dataclass
class ImportRecord:
    title: str
    original_title: str
    year: int | None
    season_number: int | None
    status: str
    rating: int | None
    marked_at: int | None
    source_id: str
    source_url: str | None
    metadata: dict


def parse_record(data: dict[str, Any]) -> ImportRecord:
    title = data["title"].strip()
    original = (data.get("originalTitle") or title).strip()
    _, title_year, title_season = parse_title(title)
    _, _, original_season = parse_title(original or "")
    year_match = re.match(r"\s*((?:18|19|20)\d{2})", data.get("info") or "")
    year = title_year or (int(year_match[1]) if year_match else None)
    status = {"collect": "watched", "wish": "wish"}[data["status"]]
    marked_at = None
    if data.get("markedAt"):
        marked_at = int(datetime.fromisoformat(data["markedAt"]).replace(tzinfo=SHANGHAI).timestamp())
    metadata = parse_info(data.get("info") or "", title)
    metadata["release_years"] = release_years(data.get("info") or "", year)
    return ImportRecord(
        title=title, original_title=original, year=year,
        season_number=title_season if title_season is not None else original_season,
        status=status, rating=data.get("stars") if status == "watched" else None,
        marked_at=marked_at, source_id=str(data["subjectId"]), source_url=data.get("url") or None,
        metadata=metadata,
    )
