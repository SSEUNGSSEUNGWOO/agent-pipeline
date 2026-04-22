# 수정 내역: 모든 함수에 한국어 docstring 추가
import json
import logging
import os
from pathlib import Path


def load_state(path: Path) -> tuple[dict, dict]:
    """state.json을 읽어 (상태 딕셔너리, 메타 딕셔너리) 튜플을 반환한다. 파일이 없거나 파싱 실패 시 빈 딕셔너리를 반환한다."""
    if not path.exists():
        return {}, {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.getLogger("agent").warning(f"state.json 파싱 실패, 빈 상태로 초기화: {e}")
        return {}, {}
    meta = raw.pop("_meta", {})
    state = {k: v for k, v in raw.items() if isinstance(v, list)}
    return state, meta


def save_state(path: Path, state: dict, meta: dict) -> None:
    """상태와 메타 정보를 원자적으로 state.json에 저장한다."""
    tmp_path = path.with_name(path.name + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({**state, "_meta": meta}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def build_seen_set(state: dict, source_id: str) -> set:
    """특정 소스의 이미 처리한 해시 집합을 반환한다."""
    return set(state.get(source_id, []))


def mark_seen(state: dict, source_id: str, item_hash: str, seen_set: set) -> None:
    """해시를 상태 딕셔너리와 seen_set에 추가하여 이미 처리한 항목으로 표시한다."""
    if source_id not in state:
        state[source_id] = []
    state[source_id].append(item_hash)
    seen_set.add(item_hash)


def trim_state(state: dict, max_per_source: int) -> None:
    """소스별 해시 목록이 최대 개수를 초과하면 오래된 항목을 잘라낸다."""
    for source_id in state:
        if len(state[source_id]) > max_per_source:
            state[source_id] = state[source_id][-max_per_source:]


def rollback_hashes(state: dict, hashes: list[str]) -> None:
    """지정된 해시 목록을 상태에서 제거하여 해당 기사를 다음 실행에서 재수집 가능하게 한다."""
    hash_set = set(hashes)
    for source_id in state:
        state[source_id] = [h for h in state[source_id] if h not in hash_set]
