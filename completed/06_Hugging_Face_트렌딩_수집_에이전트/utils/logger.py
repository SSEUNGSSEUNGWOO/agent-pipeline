# Fixed: 에러 로깅 없음 (항목 16), 함수 분리 없음 (항목 9)
import logging
import os
from datetime import datetime


def setup_logger(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """로거를 설정하고 반환합니다.
    
    Args:
        log_dir: 로그 파일 저장 디렉토리
        level: 로깅 레벨 (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        설정된 Logger 인스턴스
    """
    os.makedirs(log_dir, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"hf_trending_{date_str}.log")
    
    logger = logging.getLogger("hf_trending")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if logger.handlers:
        return logger
    
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    
    return logger
