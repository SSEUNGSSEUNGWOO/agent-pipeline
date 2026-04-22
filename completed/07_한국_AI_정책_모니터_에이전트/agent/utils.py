# 수정 내역: compute_hash 함수에 한국어 docstring 추가
import hashlib
from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))


def compute_hash(url: str, title: str) -> str:
    """URL과 제목을 조합하여 SHA-256 기반 16자리 해시 문자열을 반환한다."""
    raw = f"{url}\n{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
