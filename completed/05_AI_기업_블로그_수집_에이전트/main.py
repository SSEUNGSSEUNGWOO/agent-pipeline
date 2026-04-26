# 수정 사항: (1) 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
#            (2) collection 섹션에 피드 retry 기본값 추가 (이슈 #3 지원)
from __future__ import annotations

import fcntl
import os
import sys
from datetime import datetime, timezone

import anthropic
import yaml
from anthropic import AuthenticationError, PermissionDeniedError
from dotenv import load_dotenv

from src.collector import collect_all_feeds
from src.logger import setup_logger
from src.renderer import render_report, save_report
from src.state_manager import load_state
from src.summarizer import summarize_all


def load_config(path: str) -> dict:
    """config.yaml을 읽어 유효성 검사 후 기본값을 채운 dict를 반환한다.

    Args:
        path: config.yaml 파일 경로.

    Returns:
        유효성이 검증된 설정 dict.

    Raises:
        SystemExit: 파일 없음·필수 항목 누락·유효한 피드 없음 등 치명적 오류 시.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: config 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(config, dict):
        print("ERROR: config.yaml이 올바른 YAML 매핑이 아닙니다.", file=sys.stderr)
        sys.exit(1)

    if "feeds" not in config or not config["feeds"]:
        print("ERROR: config.yaml에 'feeds' 항목이 없거나 비어있습니다.", file=sys.stderr)
        sys.exit(1)

    valid_feeds = []
    for feed in config["feeds"]:
        if not isinstance(feed, dict):
            print(f"WARNING: 피드 스킵 — dict가 아닌 항목: {feed!r}", file=sys.stderr)
            continue
        if not feed.get("name") or not feed.get("url"):
            print(f"WARNING: 피드 스킵 — name 또는 url 누락: {feed}", file=sys.stderr)
            continue
        if not feed["url"].startswith(("http://", "https://")):
            print(f"WARNING: 피드 스킵 — 유효하지 않은 URL: {feed["name"]}: {feed["url"]}", file=sys.stderr)
            continue
        valid_feeds.append(feed)

    if not valid_feeds:
        print("ERROR: 유효한 피드가 없습니다. config.yaml의 feeds 항목을 확인하세요.", file=sys.stderr)
        sys.exit(1)

    config["feeds"] = valid_feeds

    for section in ("agent", "collection", "claude", "report"):
        if not isinstance(config.get(section), dict):
            config[section] = {}

    if not config["claude"].get("model") or not config["claude"].get("max_tokens"):
        print("ERROR: config.yaml에 claude.model 또는 claude.max_tokens가 없습니다.", file=sys.stderr)
        sys.exit(1)

    config["agent"].setdefault("name", "AI 기업 블로그 수집 에이전트")
    config["agent"].setdefault("output_dir", "output")
    config["agent"].setdefault("state_file", "state.json")
    config["agent"].setdefault("log_dir", "logs")
    config["agent"].setdefault("lock_file", "agent.lock")

    config["collection"].setdefault("request_timeout", 15)
    config["collection"].setdefault("initial_max_entries", 5)
    config["collection"].setdefault("max_entries_per_run", 20)
    config["collection"].setdefault("delay_between_feeds", 1)
    config["collection"].setdefault("max_summary_chars", 2000)
    config["collection"].setdefault("feed_retry_attempts", 3)
    config["collection"].setdefault("feed_retry_wait_min", 2)
    config["collection"].setdefault("feed_retry_wait_max", 10)

    config["claude"].setdefault("temperature", 0.3)
    config["claude"].setdefault("delay_between_calls", 1)
    config["claude"].setdefault("retry_attempts", 3)
    config["claude"].setdefault("retry_wait_min", 2)
    config["claude"].setdefault("retry_wait_max", 10)

    config["report"].setdefault("group_by", "company")
    config["report"].setdefault("show_raw_summary", False)
    config["report"].setdefault("categories", [
        "연구·기술 동향",
        "AI 인프라·플랫폼·도구",
        "AI·데이터 활용 사례",
        "정책·거버넌스",
    ])

    return config


def main() -> None:
    """에이전트 진입점. 피드 수집 → Claude 요약 → 리포트 저장 순서로 실행한다.

    중복 실행 방지를 위해 fcntl.flock 잠금을 획득한 뒤 작업을 시작하며,
    정상·비정상 종료 모두 finally 블록에서 잠금을 해제한다.
    """
    load_dotenv()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    config = load_config("config.yaml")

    logger = setup_logger(
        "ai-blog-agent",
        log_dir=config["agent"].get("log_dir", "logs"),
    )
    agent_name = config["agent"]["name"]

    # 동시 실행 방지: fcntl.flock으로 배타적 잠금 획득.
    # LOCK_EX | LOCK_NB: 비-블로킹 배타 잠금.
    # 참고: fcntl은 Unix/macOS 전용.
    lock_path = config["agent"]["lock_file"]
    lock_file = open(lock_path, "w")
    try:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                f"ERROR: 이미 실행 중인 인스턴스가 있습니다 ({lock_path}). 종료합니다.",
                file=sys.stderr,
            )
            sys.exit(1)

        logger.info(f"{agent_name} 시작")

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        state_path = config["agent"]["state_file"]
        state = load_state(state_path)
        client = anthropic.Anthropic()

        try:
            new_entries = collect_all_feeds(
                config["feeds"], state, config, state_path
            )
            if not new_entries:
                logger.info("새로운 글 없음. 종료.")
                sys.exit(0)
            summarized = summarize_all(client, new_entries, config)
            content = render_report(summarized, date_str, config)
            path = save_report(content, config["agent"]["output_dir"], date_str)
        except (AuthenticationError, PermissionDeniedError) as e:
            logger.error(f"Claude API 인증 실패: {e}")
            sys.exit(1)
        except OSError as e:
            logger.error(f"I/O 오류: {e}")
            sys.exit(1)

        logger.info(f"리포트 저장: {path}")
        logger.info(f"완료. 총 {len(summarized)}개 신규 글 처리.")

    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


if __name__ == "__main__":
    main()
