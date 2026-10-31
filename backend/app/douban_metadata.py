"""豆瓣导出的 info 区段解析；无需网络或模型调用。"""

import re

from app.catalog_service import parse_title

COUNTRIES = set("中国大陆 中国香港 中国台湾 中国澳门 中国 日本 美国 英国 法国 德国 韩国 意大利 西班牙 芬兰 瑞典 挪威 丹麦 加拿大 澳大利亚 新西兰 冰岛 摩洛哥 哥伦比亚 印度 泰国 伊朗 巴西 阿根廷 波兰 俄罗斯 苏联 奥地利 比利时 瑞士 荷兰 爱尔兰 捷克 墨西哥 智利 匈牙利 土耳其 新加坡 马来西亚 以色列 不丹 卢森堡 前西德 西德 南非 葡萄牙 希腊".split())
GENRES = set("剧情 喜剧 动作 爱情 科幻 动画 悬疑 惊悚 恐怖 纪录片 短片 情色 同性 音乐 歌舞 家庭 儿童 传记 历史 战争 犯罪 西部 奇幻 冒险 灾难 武侠 古装 运动 黑色电影 真人秀 脱口秀 舞台艺术 戏曲".split())
DATE = re.compile(r"^(?:18|19|20)\d{2}(?:-\d{1,2})?(?:-\d{1,2})?(?:\([^)]*\))?(?:\s+\d{2}:\d{2})?$")
RUNTIME = re.compile(r"^(\d+)\s*分钟")
WEBSITE = re.compile(r"(?:https?://|www\.|[a-z0-9-]+\.[a-z]{2,}(?:/|$))", re.I)


def release_years(info: str, primary_year: int | None = None) -> list[int]:
    years = []
    for part in info.split(" / "):
        if not DATE.fullmatch(part.strip()):
            break
        years.append(int(part.strip()[:4]))
    if primary_year is not None:
        years.append(primary_year)
    return list(dict.fromkeys(years))


def parse_info(info: str, title: str) -> dict:
    parts = [part.strip() for part in info.split(" / ") if part.strip()]
    base_title, _, _ = parse_title(title)
    titles = {title, base_title}
    runtime_index = next((i for i, part in enumerate(parts) if RUNTIME.match(part)), len(parts))
    country_start = next((i for i, part in enumerate(parts[:runtime_index]) if part in COUNTRIES), None)
    countries, cast, directors = [], [], []
    if country_start is not None:
        country_end = country_start
        while country_end < len(parts) and parts[country_end] in COUNTRIES:
            countries.append(parts[country_end])
            country_end += 1
        cast = [part for part in parts[:country_start] if not DATE.match(part)]
        director_end = runtime_index
        if runtime_index == len(parts):
            director_end = next((i for i in range(country_end, len(parts)) if parts[i] in titles or parts[i] in GENRES), len(parts))
        directors = [part for part in parts[country_end:director_end]
                     if part not in titles and not DATE.match(part) and not WEBSITE.search(part)]
    runtime = int(RUNTIME.match(parts[runtime_index])[1]) if runtime_index < len(parts) else None
    return dict(
        info=info, runtime=runtime, release_years=release_years(info),
        genres=[{"name": part} for part in dict.fromkeys(parts) if part in GENRES],
        countries=[{"name": name} for name in countries],
        directors=[{"name": name} for name in directors],
        cast=[{"name": name} for name in cast],
        languages=list(dict.fromkeys(part for part in parts if part.endswith(("语", "话")) and part not in titles)),
    )
