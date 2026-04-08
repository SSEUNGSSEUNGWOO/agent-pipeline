# Fixed: docstring 추가, 하드코딩된 retention='30 days'를 파라미터로 대체
import os
import sys
from loguru import logger


def setup_logger(log_dir: str, log_retention: str):
    """로거를 초기화한다.

    log_dir에 날짜별 로그 파일을 생성하고, stderr에는 INFO 이상 출력한다.
    파일 로그는 매일 자정 rotation되며 log_retention 기간 후 삭제된다.
    """
    os.makedirs(log_dir, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level='INFO')
    logger.add(
        os.path.join(log_dir, '{time:YYYY-MM-DD}.log'),
        rotation='00:00',
        retention=log_retention,
        compression='zip',
        level='DEBUG',
    )
    return logger
