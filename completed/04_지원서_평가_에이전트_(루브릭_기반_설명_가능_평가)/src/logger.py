# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from src.config import get_config, get_base_dir


def setup_logger(name: str = "evaluator") -> logging.Logger:
    """로거를 설정하고 파일 핸들러와 콘솔 핸들러를 등록하여 반환한다."""
    config = get_config()
    log_config = config.get("logging", {})

    log_dir = get_base_dir() / log_config.get("dir", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    fmt = log_config.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    retention_days = log_config.get("retention_days", 30)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    log_file = log_dir / "evaluator.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(console_handler)

    return logger
