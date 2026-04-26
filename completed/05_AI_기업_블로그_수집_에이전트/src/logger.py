# 수정 사항: 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone


def setup_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """루트 로거에 파일·콘솔 핸들러를 설정하고 명명된 로거를 반환한다.

    같은 경로의 FileHandler가 이미 추가되어 있으면 중복 추가하지 않는다.
    log_dir 생성에 실패하면 콘솔 핸들러만 사용하고 경고를 기록한다.

    Args:
        name: 반환할 로거 이름 (보통 모듈명 또는 에이전트 이름).
        log_dir: 로그 파일을 저장할 디렉토리 경로.

    Returns:
        설정이 완료된 logging.Logger 인스턴스.
    """
    root = logging.getLogger("")
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S")

    def _ensure_stream_handler() -> None:
        """루트 로거에 StreamHandler가 없으면 추가한다. FileHandler는 제외한다."""
        has_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in root.handlers
        )
        if not has_stream:
            ch = logging.StreamHandler()
            ch.setFormatter(fmt)
            root.addHandler(ch)

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError as e:
        _ensure_stream_handler()
        named = logging.getLogger(name)
        named.warning(
            f"로그 디렉토리 생성 실패 ({log_dir}): {e}. 콘솔 로그만 사용합니다."
        )
        return named

    log_path = os.path.join(log_dir, f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log")
    abs_log_path = os.path.abspath(log_path)

    existing_files = {
        h.baseFilename
        for h in root.handlers
        if isinstance(h, logging.FileHandler)
    }
    if abs_log_path not in existing_files:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    _ensure_stream_handler()

    return logging.getLogger(name)
