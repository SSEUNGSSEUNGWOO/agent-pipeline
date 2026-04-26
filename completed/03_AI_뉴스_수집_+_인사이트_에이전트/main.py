# Fixed: Path("config.yaml") 상대 경로를 Path(__file__).parent 기준 절대 경로로 변경 (#2)
# Fixed: 모든 함수에 Korean docstring 추가 (0/5 → 5/5) (#5)
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import datetime
import os
import sys
from pathlib import Path
import yaml

from src.collector import collect_all_feeds
from src.processor import filter_by_date, deduplicate, sort_and_truncate
from src.state import load_seen_ids, save_seen_ids, filter_new_articles
from src.analyzer import classify_category, extract_insights
from src.reporter import render_markdown, save_report
from loguru import logger


REQUIRED_TOP = ["agent", "feeds", "claude", "retry", "categories", "output", "logging", "state"]

REQUIRED_NESTED = [
    ("agent", "name"), ("agent", "lookback_days"), ("agent", "max_articles_per_feed"),
    ("agent", "max_total_articles"), ("feeds", "timeout"), ("feeds", "user_agent"),
    ("feeds", "sources"), ("claude", "model"), ("claude", "max_tokens"),
    ("claude", "temperature"), ("claude", "insight_count"), ("claude", "prompt_template"),
    ("claude", "prompt_summary_max_chars"), ("retry", "attempts"), ("retry", "wait_min"),
    ("retry", "wait_max"), ("retry", "rate_limit_wait"), ("categories", "default_name"),
    ("categories", "items"), ("output", "dir"), ("output", "encoding"),
    ("logging", "dir"), ("logging", "level"), ("logging", "retention_days"),
    ("state", "path"), ("state", "retention_days"),
]


def load_config(path: Path) -> dict:
    """config.yaml을 로드하고 필수 키 존재 여부를 검증한다. 오류 시 sys.exit(1)."""
    if not path.exists():
        print(f"오류: config.yaml 파일을 찾을 수 없습니다: {path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"오류: config.yaml 파싱 실패: {e}")
        sys.exit(1)

    if not isinstance(config, dict):
        print("오류: config.yaml이 올바른 형식이 아닙니다.")
        sys.exit(1)

    for key in REQUIRED_TOP:
        if key not in config:
            print(f"오류: config.yaml에 필수 섹션 '{key}'가 없습니다.")
            sys.exit(1)

    for section, key in REQUIRED_NESTED:
        if key not in config.get(section, {}):
            print(f"오류: config.yaml에 필수 키 '{section}.{key}'가 없습니다.")
            sys.exit(1)

    return config


def cleanup_old_logs(log_dir: Path, retention_days: int) -> None:
    """retention_days보다 오래된 날짜 형식 로그 파일을 삭제한다."""
    cutoff = datetime.date.today() - datetime.timedelta(days=retention_days)
    for log_file in log_dir.glob("*.log"):
        try:
            file_date = datetime.date.fromisoformat(log_file.stem)
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                log_file.unlink(missing_ok=True)
                print(f"오래된 로그 파일 삭제: {log_file.name}")
            except OSError as e:
                print(f"로그 파일 삭제 실패, 스킵: {log_file.name} — {e}")


def setup_logger(log_dir: Path, date: datetime.date, level: str) -> None:
    """loguru 로거를 날짜별 파일과 stderr에 설정한다."""
    logger.remove()
    logger.add(log_dir / f"{date}.log", level=level)
    logger.add(sys.stderr, level=level)


def run(config: dict) -> None:
    """피드 수집 → 필터링 → Claude 분석 → 리포트 저장의 전체 파이프라인을 실행한다."""
    categories_order = [cat["name"] for cat in config["categories"]["items"]]

    state_path = Path(config["state"]["path"])
    state_path.parent.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.datetime.utcnow()
    today = generated_at.date()

    output_dir = Path(config["output"]["dir"])
    log_dir = Path(config["logging"]["dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    cleanup_old_logs(log_dir, retention_days=config["logging"]["retention_days"])
    setup_logger(log_dir, today, level=config["logging"]["level"])

    logger.info(f"에이전트 실행 시작: {today}")

    retry_cfg = config["retry"]
    articles, enabled_feed_count, success_feed_count = collect_all_feeds(
        feed_configs=config["feeds"]["sources"],
        timeout=config["feeds"]["timeout"],
        max_articles_per_feed=config["agent"]["max_articles_per_feed"],
        user_agent=config["feeds"]["user_agent"],
        retry_cfg=retry_cfg,
    )
    logger.info(f"피드 수집 완료: {success_feed_count}/{enabled_feed_count}개 성공, 기사 {len(articles)}개")

    lookback_days = config["agent"]["lookback_days"]
    articles = filter_by_date(articles, today, lookback_days=lookback_days)
    logger.info(f"날짜 필터 후 기사 수: {len(articles)}개 (lookback_days={lookback_days})")

    articles = deduplicate(articles)
    total_article_count = len(articles)

    seen_ids = load_seen_ids(state_path)
    all_new_articles = filter_new_articles(articles, seen_ids)
    logger.info(f"신규 기사: {len(all_new_articles)}개 (중복/기수집 제외)")

    if len(all_new_articles) == 0:
        logger.info("신규 기사 없음. 리포트 생성 생략.")
        return

    new_article_count = len(all_new_articles)

    default_category_name = config["categories"]["default_name"]
    for article in all_new_articles:
        article["category"] = classify_category(
            article["title"],
            article["summary"],
            config["categories"]["items"],
            default_name=default_category_name,
        )

    new_articles = sort_and_truncate(all_new_articles, max_count=config["agent"]["max_total_articles"])
    displayed_article_count = len(new_articles)

    logger.info(f"Claude API 인사이트 추출 시작 (기사 {len(new_articles)}개)")
    analysis = extract_insights(
        articles=new_articles,
        model=config["claude"]["model"],
        max_tokens=config["claude"]["max_tokens"],
        temperature=config["claude"]["temperature"],
        insight_count=config["claude"]["insight_count"],
        prompt_template=config["claude"]["prompt_template"],
        prompt_summary_max_chars=config["claude"]["prompt_summary_max_chars"],
        retry_cfg=retry_cfg,
    )

    content = render_markdown(
        date=today,
        articles=new_articles,
        analysis=analysis,
        model=config["claude"]["model"],
        agent_name=config["agent"]["name"],
        categories_order=categories_order,
        default_category_name=default_category_name,
        enabled_feed_count=enabled_feed_count,
        success_feed_count=success_feed_count,
        total_article_count=total_article_count,
        new_article_count=new_article_count,
        displayed_article_count=displayed_article_count,
        generated_at=generated_at,
    )

    try:
        saved_path = save_report(content, output_dir=output_dir, date=today,
                                 encoding=config["output"]["encoding"])
        logger.info(f"리포트 저장 완료: {saved_path}")
    except OSError as e:
        logger.error(f"리포트 저장 실패: {e}")
        return

    try:
        save_seen_ids(
            state_path,
            new_ids={a["id"] for a in all_new_articles},
            date=today,
            retention_days=config["state"]["retention_days"],
        )
    except OSError as e:
        logger.warning(f"state.json 저장 실패. 다음 실행에서 중복 처리될 수 있습니다: {e}")

    logger.info("에이전트 실행 완료.")


def main():
    """진입점. config.yaml을 __file__ 기준 경로로 로드하고 ANTHROPIC_API_KEY를 검증한 후 run()을 호출한다."""
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(config_path)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("오류: ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)
    run(config)


if __name__ == "__main__":
    main()
