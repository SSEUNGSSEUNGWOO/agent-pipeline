# Fixed: 모든 함수에 한국어 docstring 추가
import hashlib


def compute_hash(url: str, title: str) -> str:
    """URL과 제목을 조합해 16자리 SHA-256 해시를 생성한다."""
    raw = f"{url}\n{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
