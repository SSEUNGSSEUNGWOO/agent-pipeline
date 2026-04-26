# 수정 사항: (1) 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
#            (2) fetch_feed()에 tenacity retry 로직 추가 — 네트워크 오류 시 재시도 (이슈 #3)
#            (3) collect_all_feeds()에서 retry 파라미터를 config에서 읽어 fetch_feed에 전달
from __future__ import annotations

import calendar
import feedparser
import hashlib
import html
import logging
import re
import requests
import time
from datetime import datetime, timezone

from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.state_manager import get_last_id, save_state, update_last_id

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ai-blog-agent/1.0; "
        "+https://github.com/your-repo/ai-blog-agent)"
        # TODO: 배포 전 실제 저장소 URL로 교체하거나 config.yaml의
        # agent.user_agent 항목으로 추출할 것
    )
}

_RETRYABLE_HTTP_EXCEPTIONS = (requests.ConnectionError, requests.Timeout)


def fetch_feed(
    feed_config: dict,
    timeout: int,
    headers: dict,
    retry_attempts: int = 3,
    retry_wait_min: int = 2,
    retry_wait_max: int = 10,
) -> feedparser.FeedParserDict | None:
    """단일 RSS 피드를 가져온다. 네트워크 오류 시 tenacity로 재시도한다.

    Args:
        feed_config: 피드 설정 dict. 'url'·'name' 키 필수.
        timeout: HTTP 요청 타임아웃(초).
        headers: 요청 헤더 dict.
        retry_attempts: 최대 재시도 횟수 (기본 3).
        retry_wait_min: 재시도 최소 대기 시간(초) (기본 2).
        retry_wait_max: 재시도 최대 대기 시간(초) (기본 10).

    Returns:
        파싱된 feedparser.FeedParserDict, 또는 복구 불가 오류 시 None.
    """
    url = feed_config["url"]
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(retry_attempts),
            wait=wait_exponential(multiplier=1, min=retry_wait_min, max=retry_wait_max),
            retry=retry_if_exception_type(_RETRYABLE_HTTP_EXCEPTIONS),
            reraise=True,
        ):
            with attempt:
                response = requests.get(url, timeout=timeout, headers=headers)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                if feed.get("bozo"):
                    logger.warning(
                        f"[{feed_config['name']}] bozo 피드(잘못된 XML): {feed.get('bozo_exception')}"
                    )
                return feed
    except requests.HTTPError as e:
        logger.warning(f"[{feed_config['name']}] HTTP 오류: {e}. 건너뜀.")
        return None
    except requests.RequestException as e:
        logger.warning(f"[{feed_config['name']}] 피드 접근 실패: {e}. 건너뜀.")
        return None


def extract_entry_id(entry: feedparser.FeedParserDict, feed_url: str) -> str:
    """피드 항목의 고유 ID를 결정한다.

    entry.id → entry.link → (feed_url + title + published) MD5 순으로 폴백한다.

    Args:
        entry: feedparser 항목 dict.
        feed_url: 부모 피드 URL. MD5 해시 생성 시 salt로 사용.

    Returns:
        고유 식별자 문자열.
    """
    if entry.get("id"):
        return entry["id"]
    if entry.get("link"):
        return entry["link"]
    title = entry.get("title", "")
    published = str(entry.get("published", ""))
    raw = feed_url + title + published
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()


def get_new_entries(
    feed: feedparser.FeedParserDict,
    last_id: str | None,
    max_entries: int,
    feed_url: str,
) -> list[dict]:
    """피드에서 마지막으로 처리한 항목 이후의 신규 항목만 반환한다.

    항목을 published 내림차순으로 정렬한 뒤, last_id를 기준으로
    그 이전 항목만 추려 max_entries 개수로 제한한다.

    Args:
        feed: feedparser로 파싱한 피드 객체.
        last_id: 직전 실행에서 기록한 최신 항목 ID. None이면 초기 수집.
        max_entries: 반환할 최대 항목 수.
        feed_url: 피드 URL. extract_entry_id에 전달.

    Returns:
        신규 항목 dict 리스트 (published 내림차순).
    """
    entries = feed.get("entries", [])

    def sort_key(e):
        """published_parsed를 Unix 타임스탬프로 변환한다. 없으면 0 반환."""
        pp = e.get("published_parsed")
        return calendar.timegm(pp) if pp else 0

    sorted_entries = sorted(entries, key=sort_key, reverse=True)

    for e in sorted_entries:
        e["entry_id"] = extract_entry_id(e, feed_url)

    if last_id is None:
        return sorted_entries[:max_entries]

    idx = next((i for i, e in enumerate(sorted_entries) if e["entry_id"] == last_id), None)

    if idx is None:
        logger.debug(f"last_id 미발견 (피드가 최근 N개만 반환한 것으로 추정). max_entries={max_entries}개 반환")
        return sorted_entries[:max_entries]

    return sorted_entries[:idx][:max_entries]


def collect_all_feeds(
    feeds_config: list[dict],
    state: dict,
    config: dict,
    state_path: str,
) -> list[dict]:
    """활성화된 모든 피드를 순회하며 신규 항목을 수집하고 state를 갱신한다.

    각 피드에서 신규 항목을 가져온 직후 state를 저장(원자적 쓰기)하여
    중간 실패 시에도 이미 처리한 피드의 상태는 보존된다.

    Args:
        feeds_config: 피드 설정 dict 리스트.
        state: 피드별 마지막 항목 ID를 담은 상태 dict.
        config: 전체 애플리케이션 설정 dict.
        state_path: state.json 파일 경로.

    Returns:
        수집된 모든 신규 항목 dict 리스트.
    """
    all_entries = []
    initial_max = config["collection"]["initial_max_entries"]
    run_max = config["collection"]["max_entries_per_run"]
    delay = config["collection"].get("delay_between_feeds", 1)
    timeout = config["collection"].get("request_timeout", 15)
    max_summary_chars = config["collection"].get("max_summary_chars", 2000)
    retry_attempts = config["collection"].get("feed_retry_attempts", 3)
    retry_wait_min = config["collection"].get("feed_retry_wait_min", 2)
    retry_wait_max = config["collection"].get("feed_retry_wait_max", 10)

    # _HEADERS 원본은 수정하지 않는다. config.yaml의 user_agent가 있으면
    # 로컬 복사본에만 적용하여 모듈 전역 부작용을 방지한다.
    headers = dict(_HEADERS)
    custom_ua = config["agent"].get("user_agent")
    if custom_ua:
        headers["User-Agent"] = custom_ua

    enabled_feeds = [f for f in feeds_config if f.get("enabled", True)]

    for i, feed_config in enumerate(enabled_feeds):
        feed_url = feed_config["url"]
        feed = fetch_feed(
            feed_config, timeout, headers,
            retry_attempts=retry_attempts,
            retry_wait_min=retry_wait_min,
            retry_wait_max=retry_wait_max,
        )

        if feed is None:
            if i < len(enabled_feeds) - 1:
                time.sleep(delay)
            continue

        last_id = get_last_id(state, feed_url)
        max_entries = initial_max if last_id is None else run_max

        new_entries = get_new_entries(feed, last_id, max_entries, feed_url)

        if new_entries:
            state = update_last_id(state, feed_url, new_entries[0]["entry_id"])
            save_state(state_path, state)
            logger.info(f"[{feed_config['name']}] 신규 {len(new_entries)}개, state 저장")

        for entry in new_entries:
            entry["company"] = feed_config["name"]
            entry["feed_url"] = feed_url
            if entry.get("published_parsed"):
                dt = datetime.fromtimestamp(calendar.timegm(entry["published_parsed"]), tz=timezone.utc)
                entry["published"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                entry["published"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                logger.debug(f"[{feed_config['name']}] published_parsed 없음. 현재 UTC로 대체")

            # summary → entry.content[0].value 순 폴백.
            # entry.get("content") or []: 키가 없거나 값이 None인 경우 모두 []로 처리.
            raw = entry.get("summary", "")
            if not raw:
                raw = next(
                    (c.get("value", "") for c in (entry.get("content") or []) if c.get("value")),
                    "",
                )
            # 1) HTML 태그 제거
            # 2) HTML 엔티티 디코딩
            # 3) 길이 상한
            raw = html.unescape(re.sub(r"<[^>]+>", " ", raw).strip())
            entry["summary_raw"] = raw[:max_summary_chars]

        all_entries.extend(new_entries)

        if i < len(enabled_feeds) - 1:
            time.sleep(delay)

    return all_entries
