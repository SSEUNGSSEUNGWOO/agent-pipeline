# Fixed: 모든 함수에 한국어 docstring 추가
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import zip_longest
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup
from requests.exceptions import ChunkedEncodingError

from agent.state_manager import is_new_item, mark_seen
from agent.utils import compute_hash


@dataclass
class Article:
    source_id: str
    source_name: str
    source_type: str
    title: str
    url: str
    published: str
    raw_text: str
    item_hash: str


def resolve_url(raw_url: str, link_base: str) -> str:
    """상대 URL을 link_base를 기준으로 절대 URL로 변환한다."""
    if not link_base:
        return raw_url
    return urljoin(link_base, raw_url)


def fetch_with_retry(
    url: str,
    config: dict,
    logger: logging.Logger,
) -> requests.Response | None:
    """HTTP GET 요청을 재시도 로직과 함께 실행하고 응답을 반환한다."""
    timeout = config["http"]["timeout_seconds"]
    retry_count = config["http"]["retry_count"]
    retry_delay = config["http"]["retry_delay_seconds"]
    headers = {"User-Agent": config["http"]["user_agent"]}

    for attempt in range(retry_count + 1):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)

            if response.status_code == 403:
                logger.error(f"HTTP 403 Forbidden: {url}. 스킵.")
                return None
            if response.status_code == 404:
                logger.warning(f"HTTP 404 Not Found: {url}. 스킵.")
                return None
            if 400 <= response.status_code < 500:
                logger.warning(f"HTTP {response.status_code}: {url}. 스킵.")
                return None

            if response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)

            response.raise_for_status()
            return response

        except (
            requests.Timeout,
            requests.ConnectionError,
            ChunkedEncodingError,
            requests.HTTPError,
        ) as e:
            if attempt < retry_count:
                logger.warning(
                    f"요청 실패 (재시도 {attempt + 1}/{retry_count}): {url} — {e}"
                )
                time.sleep(retry_delay)
            else:
                logger.error(f"재시도 초과: {url} — {e}")
                return None

    return None


def parse_date_rss(entry) -> str:
    """RSS 피드 항목에서 발행일을 파싱해 ISO 형식 문자열로 반환한다."""
    parsed = getattr(entry, "published_parsed", None)
    if parsed is None:
        parsed = getattr(entry, "updated_parsed", None)
    if parsed is None:
        return datetime.now(tz=timezone.utc).isoformat()
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).isoformat()


def parse_date_html(date_str: str, logger: logging.Logger) -> str:
    """HTML에서 추출한 날짜 문자열을 ISO 형식으로 변환한다."""
    if not date_str or not date_str.strip():
        return datetime.now(tz=timezone.utc).isoformat()

    date_str = date_str.strip()

    m = re.match(r'(\d{4})[.\-](\d{2})[.\-](\d{2})', date_str)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return datetime(y, mo, d, tzinfo=timezone.utc).isoformat()

    m = re.match(r'(\d{2})[.\-](\d{2})[.\-](\d{2})$', date_str)
    if m:
        try:
            dt = datetime.strptime(date_str.replace("-", "."), "%y.%m.%d")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

    logger.warning(f"날짜 파싱 실패: {date_str!r}, 현재 UTC로 대체")
    return datetime.now(tz=timezone.utc).isoformat()


def parse_rss_article_meta(entry, source: dict, config: dict, item_hash: str) -> Article:
    """RSS 피드 항목으로부터 Article 객체를 생성한다."""
    url = getattr(entry, "link", "") or ""
    url = resolve_url(url, source.get("link_base", ""))

    title = getattr(entry, "title", "") or ""

    raw_text = (
        getattr(entry, "summary", None)
        or getattr(entry, "description", None)
        or title
    )
    max_chars = config["claude"]["raw_text_max_chars"]
    raw_text = raw_text[:max_chars]

    return Article(
        source_id=source["id"],
        source_name=source["name"],
        source_type="rss",
        title=title,
        url=url,
        published=parse_date_rss(entry),
        raw_text=raw_text,
        item_hash=item_hash,
    )


def extract_html_items(html: str, source: dict, config: dict, logger: logging.Logger) -> list[dict]:
    """HTML 페이지를 파싱해 제목·링크·날짜 목록을 추출한다."""
    parser = config["http"]["bs_parser"]
    soup = BeautifulSoup(html, parser)
    selectors = source.get("selectors", {})

    list_sel  = selectors.get("list")
    title_sel = selectors.get("title")
    link_sel  = selectors.get("link")

    if not list_sel or not title_sel or not link_sel:
        logger.error(
            f"[{source['id']}] selectors에 필수 키(list/title/link)가 누락되었습니다. 스킵."
        )
        return []

    items = []
    for row in soup.select(list_sel):
        title_el = row.select_one(title_sel)
        link_el  = row.select_one(link_sel)
        if not title_el or not link_el:
            continue

        date_sel = selectors.get("date")
        date_el  = row.select_one(date_sel) if date_sel else None
        date_str = date_el.get_text(strip=True) if date_el else ""

        items.append({
            "title": title_el.get_text(strip=True),
            "url":   link_el.get("href", ""),
            "date":  date_str,
        })

    return items


def collect_rss(source: dict, state: dict, config: dict, logger: logging.Logger) -> list[Article]:
    """RSS 피드에서 신규 기사를 수집하고 Article 목록으로 반환한다."""
    response = fetch_with_retry(source["url"], config, logger)
    if response is None:
        return []

    feed = feedparser.parse(response.content)

    if feed.bozo:
        logger.warning(
            f"[{source['id']}] 피드 파싱 경고 (bozo=True): {feed.bozo_exception}. "
            f"entries={len(feed.entries)}개로 계속 진행."
        )
        if not feed.entries:
            logger.error(f"[{source['id']}] 피드에 항목이 없습니다. 스킵.")
            return []

    keywords = source.get("filter_keywords", [])
    candidates = []

    for entry in feed.entries:
        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or ""
        if not url or not title:
            continue

        url = resolve_url(url, source.get("link_base", ""))
        item_hash = compute_hash(url, title)

        if not is_new_item(state, source["id"], item_hash):
            continue
        mark_seen(state, source["id"], item_hash)

        if keywords and not any(kw.lower() in title.lower() for kw in keywords):
            continue

        candidates.append(parse_rss_article_meta(entry, source, config, item_hash))

        if len(candidates) >= config["agent"]["max_articles_per_source"]:
            break

    return candidates


def collect_html(source: dict, state: dict, config: dict, logger: logging.Logger) -> list[Article]:
    """HTML 목록 페이지에서 신규 기사를 수집하고 Article 목록으로 반환한다."""
    if not source.get("link_base"):
        logger.error(f"[{source['id']}] link_base 누락. 스킵.")
        return []

    if not source.get("selectors"):
        logger.error(f"[{source['id']}] selectors 설정 누락. 스킵.")
        return []

    response = fetch_with_retry(source["url"], config, logger)
    if response is None:
        return []

    raw_items = extract_html_items(response.text, source, config, logger)
    keywords = source.get("filter_keywords", [])
    candidates = []

    for item in raw_items:
        raw_url = item.get("url", "")
        title = item.get("title", "").strip()
        if not raw_url or not title:
            continue

        url = resolve_url(raw_url, source["link_base"])
        item_hash = compute_hash(url, title)

        if not is_new_item(state, source["id"], item_hash):
            continue
        mark_seen(state, source["id"], item_hash)

        if keywords and not any(kw.lower() in title.lower() for kw in keywords):
            continue

        published = parse_date_html(item.get("date", ""), logger)
        candidates.append(Article(
            source_id=source["id"],
            source_name=source["name"],
            source_type="html",
            title=title,
            url=url,
            published=published,
            raw_text=title,
            item_hash=item_hash,
        ))

        if len(candidates) >= config["agent"]["max_articles_per_source"]:
            break

    return candidates


def collect_all(
    sources: list[dict],
    state: dict,
    config: dict,
    logger: logging.Logger,
) -> list[Article]:
    """모든 소스에서 기사를 수집하고 최대 개수 제한을 적용해 반환한다."""
    per_source_results = []

    for i, source in enumerate(sources):
        if not source.get("enabled", True):
            logger.info(f"[{source['id']}] 소스 비활성화됨, 건너뜁니다.")
            continue

        if source["type"] == "rss":
            articles = collect_rss(source, state, config, logger)
        elif source["type"] == "html":
            articles = collect_html(source, state, config, logger)
        else:
            logger.warning(f"[{source['id']}] 알 수 없는 소스 타입: {source['type']}")
            articles = []

        per_source_results.append(articles)

        remaining = [s for s in sources[i + 1:] if s.get("enabled", True)]
        if remaining:
            time.sleep(config["agent"]["request_delay_seconds"])

    max_run = config["agent"]["max_articles_per_run"]
    merged = []
    for round_items in zip_longest(*per_source_results, fillvalue=None):
        for item in round_items:
            if item is None:
                continue
            merged.append(item)
            if len(merged) >= max_run:
                break
        if len(merged) >= max_run:
            total_available = sum(len(r) for r in per_source_results)
            if total_available > len(merged):
                logger.warning(
                    f"총 수집 가능 {total_available}개 중 "
                    f"{max_run}개만 처리"
                )
            break

    return merged
