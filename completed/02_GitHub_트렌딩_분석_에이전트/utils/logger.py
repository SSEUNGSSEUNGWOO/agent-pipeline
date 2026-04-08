import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(config: dict) -> logging.Logger:
    """로그 설정을 초기화하고 Logger 인스턴스를 반환한다."""
    log_config = config.get("logging", {})
    log_dir = log_config.get("log_dir", "logs")
    level_str = log_config.get("level", "INFO")
    filename_format = log_config.get("filename_format", "trending_%Y-%m-%d.log")
    console_output = log_config.get("console_output", True)

    Path(log_dir).mkdir(parents=True, exist_ok=True)

    log_filename = datetime.now().strftime(filename_format)
    log_path = os.path.join(log_dir, log_filename)

    level = getattr(logging, level_str.upper(), logging.INFO)

    logger = logging.getLogger("github_trending")
    logger.setLevel(level)

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
