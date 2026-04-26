# Fixed: 모든 함수에 Korean docstring 추가 (0/4 → 4/4) (#5)
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from datetime import timedelta
from loguru import logger


def make_article_id(article: dict) -> str:
    """기사의 link 또는 (title+source)를 MD5 해시해 16자리 고유 ID를 반환한다."""
    key = article.get("link") or (article.get("title", "") + article.get("source", ""))
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:16]


def load_seen_ids(state_path: Path) -> dict:
    """state.json에서 기수집 ID 딕셔너리를 로드한다. 파일 없거나 손상되면 빈 딕셔너리 반환."""
    if not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        logger.warning("state.json 손상, 빈 상태로 초기화")
        return {}

    if not isinstance(data, dict):
        logger.warning("state.json 구버전 형식 감지, 빈 상태로 초기화")
        return {}

    if any(not isinstance(v, str) for v in data.values()):
        logger.warning("state.json 구버전 형식 감지, 빈 상태로 초기화")
        return {}

    return data


def save_seen_ids(state_path: Path, new_ids: set[str], date: datetime.date, retention_days: int) -> None:
    """신규 ID를 state.json에 추가하고 retention_days 이전 항목을 정리한다."""
    existing = load_seen_ids(state_path)
    for id_ in new_ids:
        existing[id_] = date.isoformat()

    cutoff = date - timedelta(days=retention_days)
    pruned = {k: v for k, v in existing.items() if v >= cutoff.isoformat()}

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2)


def filter_new_articles(articles: list[dict], seen_ids: dict) -> list[dict]:
    """기수집 ID에 없는 신규 기사만 필터링해 반환한다. 각 기사에 id 필드를 추가한다."""
    result = []
    for article in articles:
        article["id"] = make_article_id(article)
        if article["id"] not in seen_ids:
            result.append(article)
    return result
