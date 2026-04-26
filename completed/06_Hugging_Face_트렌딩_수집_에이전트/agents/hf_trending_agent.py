# Fixed: 데이터 수집/처리 로직 없음 (항목 2), 에러 핸들링 없음 (항목 3), 타임아웃 처리 없음 (항목 4),
#        API 재시도 로직 없음 (항목 15), API 키 누락 에러 메시지 없음 (항목 17), 함수 분리 없음 (항목 9),
#        한국어 docstring 없음 (항목 11)
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger("hf_trending")

TIMEOUT = 15


class HFTrendingAgent:
    """Hugging Face 트렌딩 항목을 수집하는 에이전트."""

    def __init__(self, base_url: str, limits: dict, token: Optional[str] = None,
                 max_attempts: int = 3, delay_seconds: int = 2):
        """에이전트를 초기화합니다.
        
        Args:
            base_url: Hugging Face API 기본 URL
            limits: 카테고리별 수집 개수 (예: {"models": 30})
            token: HF API 토큰 (선택사항)
            max_attempts: API 재시도 횟수
            delay_seconds: 재시도 간 대기 시간(초)
        """
        self.base_url = base_url.rstrip("/")
        self.limits = limits
        self.max_attempts = max_attempts
        self.delay_seconds = delay_seconds
        self.session = requests.Session()
        
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            logger.info("HF 토큰 인증 활성화")
        else:
            logger.info("HF 토큰 없음 — 공개 API 사용 (레이트 리밋 적용될 수 있음)")

    def collect(self, categories: list[str]) -> dict[str, list[dict]]:
        """지정된 카테고리의 트렌딩 항목을 수집합니다.
        
        Args:
            categories: 수집할 카테고리 목록 (models, datasets, spaces)
        
        Returns:
            카테고리별 트렌딩 항목 딕셔너리
        """
        results = {}
        for category in categories:
            logger.info(f"[{category}] 트렌딩 수집 시작")
            items = self._fetch_trending(category)
            results[category] = items
            logger.info(f"[{category}] {len(items)}개 수집 완료")
        return results

    def _fetch_trending(self, category: str) -> list[dict]:
        """단일 카테고리의 트렌딩 항목을 API에서 가져옵니다.
        
        Args:
            category: 카테고리명 (models, datasets, spaces)
        
        Returns:
            트렌딩 항목 리스트
        
        Raises:
            RuntimeError: max_attempts 회 재시도 후에도 실패 시
        """
        limit = self.limits.get(category, 20)
        url = f"{self.base_url}/{category}"
        params = {"sort": "trendingScore", "direction": -1, "limit": limit}
        
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"[{category}] 타임아웃 (시도 {attempt}/{self.max_attempts})")
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                if status == 401:
                    logger.error(
                        f"[{category}] 인증 실패 (401) — HF_TOKEN이 올바른지 확인하세요. "
                        f".env 파일에 HF_TOKEN=hf_xxx 형식으로 설정하거나 토큰 없이 재시도하세요."
                    )
                    raise RuntimeError(f"HF API 인증 실패: 토큰을 확인하세요.") from e
                last_error = e
                logger.warning(f"[{category}] HTTP {status} 오류 (시도 {attempt}/{self.max_attempts}): {e}")
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"[{category}] 요청 오류 (시도 {attempt}/{self.max_attempts}): {e}")
            
            if attempt < self.max_attempts:
                time.sleep(self.delay_seconds)
        
        raise RuntimeError(f"[{category}] {self.max_attempts}회 재시도 후 수집 실패: {last_error}") from last_error
