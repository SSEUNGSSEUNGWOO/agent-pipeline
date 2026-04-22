# Fixed: 모든 함수에 한국어 docstring 추가
import fcntl
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from agent.collector import collect_all
from agent.reporter import generate_report
from agent.state_manager import load_state, save_state, trim_state
from agent.summarizer import summarize_all

load_dotenv()

_KST = timezone(timedelta(hours=9))

_REQUIRED_KEYS = [
    ("agent", "max_articles_per_run"),
    ("agent", "max_articles_per_source"),
    ("agent", "request_delay_seconds"),
    ("agent", "region_tie_break"),
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
    ("logging", "level"),
]


def init_console_logger() -> logging.Logger:
    """콘솔 핸들러를 붙인 에이전트 로거를 초기화하고 반환한다."""
    logger = logging.getLogger("agent")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


def setup_logging(log_dir: Path, date_str: str, logger: logging.Logger, level_str: str) -> logging.Logger:
    """날짜별 로그 파일 핸들러를 추가하고 로그 레벨을 설정한다."""
    log_path = log_dir / f"{date_str}.log"
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.setLevel(getattr(logging, level_str.upper(), logging.INFO))
    return logger


def acquire_lock(lock_path: Path, logger: logging.Logger):
    """파일 잠금을 획득해 에이전트 중복 실행을 방지한다."""
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.close()
        logger.error("다른 에이전트 인스턴스가 실행 중입니다. 종료합니다.")
        raise SystemExit(1)
    return lock_fh


def load_config(path: Path, logger: logging.Logger) -> dict:
    """config.yaml을 읽고 필수 키와 API 키 존재 여부를 검증한 뒤 반환한다."""
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
        if (
            section not in config
            or not isinstance(config[section], dict)
            or key not in config[section]
        ):
            logger.error(f"config.yaml 필수 키 누락: {section}.{key}")
            raise SystemExit(1)

    if not config.get("sources"):
        logger.error("config.yaml에 sources가 없습니다.")
        raise SystemExit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
        raise SystemExit(1)

    return config


def ensure_dirs(config: dict, logger: logging.Logger) -> tuple[Path, Path]:
    """출력 디렉토리와 로그 디렉토리를 생성하고 경로를 반환한다."""
    BASE_DIR = Path(__file__).parent
    output_dir = BASE_DIR / config["output"]["dir"]
    log_dir    = BASE_DIR / config["output"]["log_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"디렉토리 확인: {output_dir}, {log_dir}")
    return output_dir, log_dir


def build_meta(articles_count: int) -> dict:
    """실행 시각, 버전, 처리된 기사 수를 담은 메타 딕셔너리를 생성한다."""
    return {
        "last_run": datetime.now(tz=_KST).isoformat(),
        "version": "1",
        "articles_processed": articles_count,
    }


def main():
    """에이전트 메인 진입점으로 수집·요약·보고서 생성 전 과정을 실행한다."""
    lock_fh = None
    try:
        logger = init_console_logger()
        BASE_DIR = Path(__file__).parent

        lock_fh = acquire_lock(BASE_DIR / ".agent.lock", logger)

        config = load_config(BASE_DIR / "config.yaml", logger)

        sources = config["sources"]

        KST = timezone(timedelta(hours=9))
        date_str = datetime.now(tz=KST).strftime("%Y-%m-%d")

        output_dir, log_dir = ensure_dirs(config, logger)
        logger = setup_logging(log_dir, date_str, logger, config["logging"]["level"])

        state_path = BASE_DIR / config["state"]["path"]
        state = load_state(state_path)

        active_sources = [s for s in sources if s.get("enabled", True)]
        if not active_sources:
            logger.warning("활성화된 소스가 없습니다. config.yaml의 sources를 확인하세요.")
            return

        articles = collect_all(active_sources, state, config, logger)

        if not articles:
            logger.info("새로운 글이 없습니다.")
            save_state(state_path, state, build_meta(0))
            return

        interim_meta = {**build_meta(len(articles)), "status": "collected"}
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
