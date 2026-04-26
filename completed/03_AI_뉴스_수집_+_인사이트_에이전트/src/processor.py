# Fixed: 모든 함수에 Korean docstring 추가 (0/4 → 4/4) (#5)
from __future__ import annotations

import re
import html
from datetime import datetime, date, timedelta, time as dt_time
from src.state import make_article_id


def strip_html(text: str) -> str:
    """HTML 태그와 엔티티를 제거하고 앞뒤 공백을 정리한 문자열을 반환한다."""
    result = re.sub(r'<[^>]+>', '', text)
    return html.unescape(result).strip()


def filter_by_date(articles: list[dict], date: date, lookback_days: int) -> list[dict]:
    """published_at이 [today - lookback_days, today] 범위에 있거나 None인 기사만 반환한다."""
    start = datetime.combine(date - timedelta(days=lookback_days), dt_time.min)
    end = datetime.combine(date, dt_time.max)
    result = []
    for article in articles:
        pub = article.get("published_at")
        if pub is None or (start <= pub <= end):
            result.append(article)
    return result


def deduplicate(articles: list[dict]) -> list[dict]:
    """article ID 기준으로 중복 기사를 제거한 목록을 반환한다."""
    seen: set[str] = set()
    result = []
    for article in articles:
        aid = make_article_id(article)
        if aid not in seen:
            seen.add(aid)
            result.append(article)
    return result


def sort_and_truncate(articles: list[dict], max_count: int) -> list[dict]:
    """기사를 published_at 내림차순으로 정렬하고 max_count개로 잘라 반환한다."""
    sorted_articles = sorted(
        articles,
        key=lambda a: a["published_at"] or datetime.min,
        reverse=True,
    )
    return sorted_articles[:max_count]
