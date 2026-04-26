# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
# [Fix] API 호출 시 timeout 파라미터 추가 — 네트워크 장애 시 무한 대기 방지 (안정성)
import anthropic
from dotenv import load_dotenv
import json
import logging
import os
import time
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from src.config import get_config

logger = logging.getLogger("evaluator")


def create_client() -> anthropic.Anthropic:
    """Anthropic API 클라이언트를 생성하고 반환한다."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    return anthropic.Anthropic(api_key=api_key)


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """싱글턴 패턴으로 API 클라이언트를 반환한다."""
    global _client
    if _client is None:
        _client = create_client()
    return _client


def call_claude(
    system: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> str:
    """Claude API를 호출하여 텍스트 응답을 반환한다. 재시도 및 rate limit 처리를 포함한다."""
    config = get_config()
    api_config = config["api"]
    model = model or api_config["model"]
    max_tokens = max_tokens or api_config["max_tokens"]
    temperature = temperature if temperature is not None else api_config["temperature"]
    timeout = api_config.get("timeout", 120)

    client = _get_client()
    attempts = api_config.get("retry_attempts", 3)
    delay = api_config.get("retry_delay_seconds", 2)
    backoff = api_config.get("retry_backoff_multiplier", 2)
    rate_limit_retries = api_config.get("rate_limit_max_retries", 5)

    last_error = None
    for attempt in range(attempts + rate_limit_retries):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages,
                timeout=timeout,
            )
            return response.content[0].text
        except anthropic.RateLimitError as e:
            if attempt >= rate_limit_retries:
                raise
            wait_time = delay * (backoff ** attempt)
            logger.warning(f"Rate limit 도달. {wait_time}초 대기 후 재시도...")
            time.sleep(wait_time)
            last_error = e
        except anthropic.APIError as e:
            if attempt >= attempts - 1:
                raise
            wait_time = delay * (backoff ** attempt)
            logger.warning(f"API 에러: {e}. {wait_time}초 대기 후 재시도...")
            time.sleep(wait_time)
            last_error = e

    raise last_error


def call_claude_json(
    system: str,
    messages: list[dict],
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    """Claude API를 호출하고 응답을 JSON으로 파싱하여 반환한다. 파싱 실패 시 재요청한다."""
    response_text = call_claude(system, messages, model, max_tokens, temperature)

    try:
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패. JSON 포맷 강조하여 재요청합니다.")
        retry_messages = messages + [
            {"role": "assistant", "content": response_text},
            {"role": "user", "content": "위 응답을 유효한 JSON 형식으로만 다시 작성해주세요. 코드 블록이나 부가 설명 없이 순수 JSON만 반환하세요."},
        ]
        response_text2 = call_claude(system, retry_messages, model, max_tokens, temperature)
        try:
            text2 = response_text2.strip()
            if text2.startswith("```json"):
                text2 = text2[7:]
            if text2.startswith("```"):
                text2 = text2[3:]
            if text2.endswith("```"):
                text2 = text2[:-3]
            return json.loads(text2.strip())
        except json.JSONDecodeError:
            logger.error(f"JSON 재파싱 실패. Raw response 저장됨.")
            raise ValueError(f"Claude 응답 JSON 파싱 실패: {response_text2[:200]}")
