# 수정 내역:
# 1. 모든 함수에 한국어 docstring 추가
# 2. _REQUIRED_KEYS에 agent.allowed_region_tags, agent.allowed_category_tags 추가 (config 검증)
import fcntl
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

from agent.collector import collect_all
from agent.reporter import generate_report
from agent.state_manager import load_state, save_state, trim_state, rollback_hashes
from agent.summarizer import summarize_all
from agent.utils import KST

load_dotenv()

_REQUIRED_KEYS = [
    ("agent", "max_articles_per_run"),
    ("agent", "max_articles_per_source"),
    ("agent", "request_delay_seconds"),
    ("agent", "region_tie_break"),
    ("agent", "allowed_region_tags"),
    ("agent", "allowed_category_tags"),
    ("http", "timeout_seconds"),
    ("http", "retry_count"),
    ("http", "retry_delay_seconds"),
    ("http", "user_agent"),
    ("http", "bs_parser"),
    ("claude", "model"),
    ("claude", "max_tokens"),
    ("claude", "temperature"),
    ("claude", "retry_count"),
    ("claude", "retry_delay_seconds"),
    ("claude", "call_delay_seconds"),
    ("claude", "raw_text_max_chars"),
    ("state", "path"),
    ("state", "max_hashes_per_source"),
    ("output", "dir"),
    ("output", "log_dir"),
    ("output", "show_untagged_section"),
    ("logging", "level"),
]

_VALID_SOURCE_TYPES = {"rss", "html"}
_REQUIRED_SOURCE_FIELDS = ("id", "name", "type", "url")
_REQUIRED_SELECTOR_KEYS = ("list", "title", "link")


def acquire_lock(lock_path: Path, logger: logging.Logger):
    """에이전트 중복 실행을 막기 위해 락 파일을 획득한다. 이미 실행 중이면 SystemExit(1)을 발생시킨다."""
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        logger.error("다른 에이전트 인스턴스가 실행 중입니다. 종료합니다.")
        raise SystemExit(1)
    return lock_fh


def init_console_logger() -> logging.Logger:
    """콘솔 출력용 기본 로거를 초기화하고 반환한다."""
    logger = logging.getLogger("agent")
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(ch)
    return logger


def setup_logging(log_dir: Path, date_str: str, logger: logging.Logger, level_str: str) -> logging.Logger:
    """로그 파일 핸들러를 로거에 추가하고 로그 레벨을 설정한다."""
    log_path = log_dir / f"{date_str}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.setLevel(getattr(logging, level_str.upper(), logging.INFO))
    return logger


def load_config(path: Path, logger: logging.Logger) -> dict:
    """config.yaml을 읽어 파싱하고 필수 키 존재 여부를 검증하여 설정 딕셔너리를 반환한다."""
    try:
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"config.yaml 없음: {path}")
        raise SystemExit(1)
    except yaml.YAMLError as e:
        logger.error(f"config.yaml 파싱 오류: {e}")
        raise SystemExit(1)

    for section, key in _REQUIRED_KEYS:
        if section not in config or key not in config[section]:
            logger.error(f"config.yaml 필수 키 누락: {section}.{key}")
            raise SystemExit(1)

    if not config.get("sources"):
        logger.error("config.yaml에 sources가 없습니다.")
        raise SystemExit(1)

    for idx, source in enumerate(config["sources"]):
        for field in _REQUIRED_SOURCE_FIELDS:
            if not source.get(field):
                logger.error(
                    f"config.yaml sources[{idx}] 필수 필드 누락 또는 빈 값: '{field}'. "
                    f"source 내용: {source}"
                )
                raise SystemExit(1)
        if source["type"] not in _VALID_SOURCE_TYPES:
            logger.error(
                f"config.yaml sources[{idx}] (id={source.get('id')!r}) "
                f"type 값 오류: {source['type']!r}. 허용값: {_VALID_SOURCE_TYPES}"
            )
            raise SystemExit(1)

        if source["type"] == "html":
            selectors = source.get("selectors")
            if not selectors or not isinstance(selectors, dict):
                logger.error(
                    f"config.yaml sources[{idx}] (id={source.get('id')!r}) "
                    f"HTML 소스에 'selectors' 섹션이 없습니다."
                )
                raise SystemExit(1)
            for sel_key in _REQUIRED_SELECTOR_KEYS:
                if not selectors.get(sel_key):
                    logger.error(
                        f"config.yaml sources[{idx}] (id={source.get('id')!r}) "
                        f"selectors.{sel_key} 누락 또는 빈 값."
                    )
                    raise SystemExit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
        raise SystemExit(1)
    config["_api_key"] = api_key

    return config


def ensure_dirs(config: dict, logger: logging.Logger) -> tuple[Path, Path]:
    """출력 디렉토리와 로그 디렉토리를 생성하고, 잔류 임시 파일 및 만료된 백업을 정리한다."""
    BASE_DIR = Path(__file__).parent
    output_dir = BASE_DIR / config["output"]["dir"]
    log_dir = BASE_DIR / config["output"]["log_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob("*.md.tmp"):
        try:
            stale.unlink()
            logger.debug(f"잔류 임시 파일 삭제: {stale}")
        except OSError as e:
            logger.warning(f"잔류 임시 파일 삭제 실패: {stale} — {e}")

    retention_days = config["output"].get("backup_retention_days", 7)
    cutoff = datetime.now(tz=KST).date() - timedelta(days=retention_days)
    for bak in output_dir.glob("*.bak.md"):
        date_part = bak.name.split(".")[0]
        try:
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
            if file_date < cutoff:
                bak.unlink()
                logger.debug(f"오래된 백업 삭제: {bak}")
        except (ValueError, OSError) as e:
            logger.warning(f"백업 파일 정리 중 오류: {bak} — {e}")

    logger.debug(f"디렉토리 확인: {output_dir}, {log_dir}")
    return output_dir, log_dir


def build_meta(articles_count: int, status: str = "done") -> dict:
    """실행 메타 정보 딕셔너리를 생성하여 반환한다."""
    return {
        "last_run": datetime.now(tz=KST).isoformat(),
        "version": "1",
        "articles_processed": articles_count,
        "status": status,
    }


def main():
    """에이전트 메인 진입점. 수집→요약→보고서 생성 파이프라인을 실행하고 상태를 저장한다."""
    lock_fh = None
    try:
        logger = init_console_logger()
        BASE_DIR = Path(__file__).parent

        lock_fh = acquire_lock(BASE_DIR / ".agent.lock", logger)

        config = load_config(BASE_DIR / "config.yaml", logger)

        sources = config["sources"]

        date_str = datetime.now(tz=KST).strftime("%Y-%m-%d")

        output_dir, log_dir = ensure_dirs(config, logger)
        logger = setup_logging(log_dir, date_str, logger, config["logging"]["level"])

        state_path = BASE_DIR / config["state"]["path"]
        state, meta = load_state(state_path)

        if meta.get("status") == "collected":
            pending = meta.get("pending_hashes", [])
            if pending:
                rollback_hashes(state, pending)
                save_state(state_path, state, build_meta(0, "rollback_done"))
                logger.warning(
                    f"이전 실행 크래시 감지: {len(pending)}개 해시 롤백 완료. "
                    f"해당 기사는 이번 실행에서 재수집됩니다."
                )

        active_sources = [s for s in sources if s.get("enabled", True)]
        if not active_sources:
            logger.warning("활성화된 소스가 없습니다. config.yaml의 sources를 확인하세요.")
            return

        articles = collect_all(active_sources, state, config, logger)

        if not articles:
            logger.info("새로운 글이 없습니다.")
            save_state(state_path, state, build_meta(0))
            return

        pending_hashes = [a.item_hash for a in articles]
        interim_meta = {
            **build_meta(len(articles), "collected"),
            "pending_hashes": pending_hashes,
        }
        save_state(state_path, state, interim_meta)

        summarized = summarize_all(articles, config, logger)

        generate_report(summarized, output_dir, date_str, config, logger)

        trim_state(state, config["state"]["max_hashes_per_source"])
        save_state(state_path, state, build_meta(len(articles)))

        logger.info(f"처리 완료: {len(articles)}개 글, output/{date_str}.md 저장")

    finally:
        if lock_fh is not None:
            lock_fh.close()


if __name__ == "__main__":
    main()
