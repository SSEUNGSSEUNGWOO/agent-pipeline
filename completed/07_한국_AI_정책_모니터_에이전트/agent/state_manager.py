# Fixed: 모든 함수에 한국어 docstring 추가
import json
import logging
import os
from pathlib import Path


def load_state(path: Path) -> dict:
    """state.json을 읽어 소스별 해시 목록 딕셔너리를 반환한다."""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.getLogger("agent").warning(f"state.json 파싱 실패, 빈 상태로 초기화: {e}")
        return {}
    return {k: v for k, v in raw.items() if k != "_meta" and isinstance(v, list)}


def save_state(path: Path, state: dict, meta: dict) -> None:
    """state 딕셔너리와 메타 정보를 임시 파일을 거쳐 안전하게 저장한다."""
    tmp_path = path.with_suffix(".json.tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({**state, "_meta": meta}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def is_new_item(state: dict, source_id: str, item_hash: str) -> bool:
    """해당 소스에서 item_hash가 처음 등장하는 신규 항목인지 확인한다."""
    return item_hash not in set(state.get(source_id, []))


def mark_seen(state: dict, source_id: str, item_hash: str) -> None:
    """item_hash를 해당 소스의 처리 완료 목록에 추가한다."""
    if source_id not in state:
        state[source_id] = []
    state[source_id].append(item_hash)


def trim_state(state: dict, max_per_source: int) -> None:
    """소스별 해시 목록을 최대 개수 이하로 오래된 항목부터 제거한다."""
    for source_id in state:
        while len(state[source_id]) > max_per_source:
            state[source_id].pop(0)
