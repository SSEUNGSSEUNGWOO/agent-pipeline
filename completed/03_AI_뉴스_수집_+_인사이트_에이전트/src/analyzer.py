# Fixed: anthropic.AuthenticationError를 except 절에 추가해 잘못된 API 키 시 graceful 처리 (#1, #6)
# Fixed: 모든 함수에 Korean docstring 추가 (0/8 → 8/8) (#5)
from __future__ import annotations

import json
import anthropic
from typing import Callable
from loguru import logger
from tenacity import (
    Retrying, RetryError,
    stop_after_attempt, wait_exponential,
    retry_if_exception_type,
)

RETRYABLE = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    anthropic.RateLimitError,
)


def classify_category(title: str, summary: str, categories: list[dict], default_name: str) -> str:
    """기사 제목과 요약을 키워드 매칭으로 카테고리에 분류한다. 매칭 없으면 default_name 반환."""
    text = (title + " " + summary).lower()
    for category in categories:
        if any(kw in text for kw in category["keywords"]):
            return category["name"]
    return default_name


def build_prompt(articles: list[dict], insight_count: int, prompt_template: str, prompt_summary_max_chars: int) -> str:
    """기사 목록으로 Claude API에 전달할 프롬프트 문자열을 생성한다."""
    example_items = ", ".join(f'"인사이트{i+1}"' for i in range(insight_count))
    example_json = '{"insights": [' + example_items + ']}' 

    article_blocks = []
    for i, article in enumerate(articles, 1):
        block = (
            f"[기사 {i}]\n"
            f"제목: {article['title']}\n"
            f"요약: {article['summary'][:prompt_summary_max_chars]}\n"
            f"출처: {article['source']}"
        )
        article_blocks.append(block)
    articles_text = "\n\n".join(article_blocks)

    prompt = prompt_template.replace("{insight_count}", str(insight_count))
    prompt = prompt.replace("{example_json}", example_json)
    prompt = prompt.replace("{articles_text}", articles_text)
    return prompt


def _extract_first_json_object(text: str) -> str | None:
    """텍스트에서 첫 번째 JSON 객체 문자열을 추출한다. 없으면 None 반환."""
    start = text.find("{")
    if start == -1:
        return None
    try:
        _, end = json.JSONDecoder().raw_decode(text, start)
        return text[start:end]
    except json.JSONDecodeError:
        return None


def parse_insights_response(raw: str, insight_count: int) -> list[str]:
    """Claude 응답 문자열을 파싱해 인사이트 리스트를 반환한다. 파싱 실패 시 오류 메시지 리스트 반환."""
    data = None
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(raw)
        if candidate:
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                data = None

    if data and isinstance(data, dict) and "insights" in data:
        insights = data["insights"]
        if isinstance(insights, list):
            return [str(item) for item in insights]

    logger.error(f"Claude 응답 파싱 실패. raw={raw[:200]!r}")
    return ["인사이트 추출 실패 (파싱 오류)"] * insight_count


def _make_wait(rate_limit_wait: int, wait_min: int, wait_max: int) -> Callable:
    """RateLimitError는 고정 대기, 그 외는 지수 백오프를 적용하는 wait 함수를 반환한다."""
    exp = wait_exponential(min=wait_min, max=wait_max)

    def _wait(retry_state):
        """재시도 상태에 따라 대기 시간을 결정한다."""
        if isinstance(retry_state.outcome.exception(), anthropic.RateLimitError):
            logger.warning(f"Rate limit 응답. {rate_limit_wait}초 대기 후 재시도.")
            return rate_limit_wait
        return exp(retry_state)

    return _wait


def extract_insights(
    articles: list[dict],
    model: str,
    max_tokens: int,
    temperature: float,
    insight_count: int,
    prompt_template: str,
    prompt_summary_max_chars: int,
    retry_cfg: dict,
) -> dict:
    """기사 목록을 Claude API에 전달해 인사이트를 추출한다. API 오류 시 오류 메시지 딕셔너리 반환."""
    client = anthropic.Anthropic()
    prompt = build_prompt(articles, insight_count, prompt_template, prompt_summary_max_chars)
    rate_limit_wait = retry_cfg.get("rate_limit_wait", 60)

    raw = None
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(retry_cfg["attempts"]),
            wait=_make_wait(rate_limit_wait, retry_cfg["wait_min"], retry_cfg["wait_max"]),
            retry=retry_if_exception_type(RETRYABLE),
        ):
            with attempt:
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                if not response.content or not hasattr(response.content[0], "text"):
                    raise ValueError("Claude 응답이 비어 있거나 TextBlock이 아닙니다.")
                raw = response.content[0].text
        return {"insights": parse_insights_response(raw, insight_count)}
    except (RetryError, ValueError, anthropic.BadRequestError, anthropic.AuthenticationError) as e:
        logger.error(f"Claude API 실패: {e}")
        return {"insights": ["인사이트 추출 실패 (API 오류)"] * insight_count}
