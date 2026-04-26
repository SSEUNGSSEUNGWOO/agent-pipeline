# Fixed: NON_RETRIABLE_STATUS(404 등) 응답 시 None 반환해 success_count 오기록 방지 (#3)
# Fixed: 모든 함수에 Korean docstring 추가 (0/2 → 2/2) (#5)
from __future__ import annotations

import calendar
import requests
import requests.exceptions
import feedparser
from datetime import datetime
from loguru import logger
from tenacity import (
    Retrying, RetryError,
    stop_after_attempt, wait_exponential,
    retry_if_exception_type,
)
from src.processor import strip_html

NON_RETRIABLE_STATUS = {400, 404, 410}


def fetch_feed(url: str, source: str, timeout: int, max_articles: int, user_agent: str) -> list[dict] | None:
    """RSS 피드 URL에서 기사를 수집한다.

    NON_RETRIABLE_STATUS(400/404/410) 응답이면 None을 반환해 실패로 표시한다.
    네트워크 오류는 예외를 그대로 raise해 상위에서 재시도하도록 한다.
    """
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": user_agent},
    )
    if response.status_code in NON_RETRIABLE_STATUS:
        logger.warning(f"비재시도성 HTTP {response.status_code} 응답, 스킵: {url}")
        return None
    response.raise_for_status()

    feed = feedparser.parse(response.content)
    entries = feed.entries[:max_articles]

    articles = []
    for entry in entries:
        if entry.get("published_parsed"):
            published_at = datetime.utcfromtimestamp(calendar.timegm(entry.published_parsed))
        else:
            published_at = None

        article = {
            "title": strip_html(entry.get("title", "")),
            "summary": strip_html(entry.get("summary", "")),
            "link": entry.get("link") or None,
            "published_at": published_at,
            "source": source,
        }
        articles.append(article)

    return articles


def collect_all_feeds(
    feed_configs: list[dict],
    timeout: int,
    max_articles_per_feed: int,
    user_agent: str,
    retry_cfg: dict,
) -> tuple[list[dict], int, int]:
    """활성화된 모든 피드를 수집한다.

    fetch_feed가 None을 반환하면(NON_RETRIABLE_STATUS) 실패로 처리해 success_count에 포함하지 않는다.
    반환: (기사 목록, 활성 피드 수, 성공 피드 수)
    """
    enabled_feeds = [f for f in feed_configs if f.get("enabled", True)]
    enabled_feed_count = len(enabled_feeds)
    result = []
    success_count = 0

    for feed in enabled_feeds:
        try:
            articles = None
            for attempt in Retrying(
                stop=stop_after_attempt(retry_cfg["attempts"]),
                wait=wait_exponential(min=retry_cfg["wait_min"], max=retry_cfg["wait_max"]),
                retry=retry_if_exception_type(requests.exceptions.RequestException),
            ):
                with attempt:
                    articles = fetch_feed(
                        feed["url"], feed["name"], timeout,
                        max_articles_per_feed, user_agent,
                    )
            if articles is not None:
                success_count += 1
                if articles:
                    result.extend(articles)
        except RetryError:
            logger.warning(f"피드 수집 실패 (재시도 소진): {feed['name']}")
        except Exception as e:
            logger.warning(f"피드 처리 중 예상치 못한 오류, 스킵: {feed['name']} — {e}")

    return result, enabled_feed_count, success_count
