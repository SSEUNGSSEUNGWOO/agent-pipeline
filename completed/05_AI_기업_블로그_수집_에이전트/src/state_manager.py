# 수정 사항: 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def save_state(path: str, state: dict) -> None:
    """state dict를 JSON 파일에 원자적으로 저장한다.

    임시 파일(.tmp)에 먼저 쓴 뒤 os.replace로 교체하여 저장 도중 충돌로 인한
    파일 손상을 방지한다.

    Args:
        path: 저장할 state.json 파일 경로.
        state: 피드 URL을 키, 마지막 항목 ID를 값으로 갖는 dict.

    Raises:
        Exception: 쓰기 또는 교체 실패 시 임시 파일을 정리하고 예외를 재발생시킨다.
    """
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def load_state(path: str) -> dict:
    """state.json을 읽어 dict로 반환한다. 파일이 없거나 손상된 경우 빈 dict를 반환한다.

    Args:
        path: 읽을 state.json 파일 경로.

    Returns:
        저장된 state dict. 파일이 없거나 파싱 실패 시 빈 dict.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.error(f"state.json 파싱 실패. 빈 상태로 초기화: {path}")
        return {}


def get_last_id(state: dict, feed_url: str) -> str | None:
    """state에서 해당 피드 URL의 마지막 처리 항목 ID를 반환한다.

    Args:
        state: load_state()로 로드한 상태 dict.
        feed_url: 조회할 피드 URL 문자열.

    Returns:
        마지막 항목 ID 문자열, 또는 처음 수집하는 피드면 None.
    """
    return state.get(feed_url)


def update_last_id(state: dict, feed_url: str, entry_id: str) -> dict:
    """state에서 해당 피드 URL의 마지막 항목 ID를 갱신하고 state를 반환한다.

    Args:
        state: 갱신할 상태 dict.
        feed_url: 갱신할 피드 URL 문자열.
        entry_id: 새로 기록할 마지막 항목 ID.

    Returns:
        entry_id가 갱신된 state dict (동일 객체).
    """
    state[feed_url] = entry_id
    return state
