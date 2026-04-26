# 수정 사항: 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
from __future__ import annotations

import json
import logging
import re
import time

import anthropic
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ClaudeResponseError(Exception):
    """빈 content, 비-TextBlock 등 Claude 응답 구조 이상 시 raise. tenacity가 재시도한다."""


RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
    ClaudeResponseError,
)

NON_RETRYABLE_EXCEPTIONS = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)


def build_prompt(entry: dict, categories: list[str]) -> str:
    """블로그 항목을 분석하는 Claude 프롬프트 문자열을 생성한다.

    Args:
        entry: 제목·링크·summary_raw를 포함한 피드 항목 dict.
        categories: Claude가 분류에 사용할 카테고리 목록.

    Returns:
        JSON 응답 형식을 지시하는 프롬프트 문자열.
    """
    fence = "```"
    categories_str = ", ".join(f'"{c}"' for c in categories)
    return (
        f"다음 AI 기업 블로그 글을 분석하고, 아래 JSON 형식으로만 응답하세요. "
        f"JSON 외 다른 텍스트는 출력하지 마세요.\n\n"
        f"제목: {entry.get('title', '(제목 없음)')}\n"
        f"링크: {entry.get('link', '')}\n"
        f"원문 요약: {entry.get('summary_raw', '없음')}\n\n"
        f"{fence}json\n"
        f"{{\n"
        f'  "summary_ko": "1. 첫 번째 줄 요약.\\n2. 두 번째 줄 요약.\\n3. 세 번째 줄 요약.",\n'
        f'  "keywords": ["키워드1", "키워드2", "키워드3"],\n'
        f'  "category": "<카테고리명>"\n'
        f"}}\n"
        f"{fence}\n\n"
        f"category는 다음 중 하나만 사용: {categories_str}"
    )


def call_claude(client: anthropic.Anthropic, prompt: str, config: dict) -> str:
    """Claude API를 호출하고 응답 텍스트를 반환한다. 일시 오류 시 tenacity로 재시도한다.

    Args:
        client: 초기화된 anthropic.Anthropic 클라이언트.
        prompt: 전송할 프롬프트 문자열.
        config: claude 설정 섹션을 포함한 전체 설정 dict.

    Returns:
        Claude 응답의 첫 번째 TextBlock 텍스트.

    Raises:
        ClaudeResponseError: 응답 content가 비어있거나 TextBlock이 아닌 경우.
        anthropic.AuthenticationError: 인증 실패 (재시도 안 함).
        anthropic.PermissionDeniedError: 권한 오류 (재시도 안 함).
    """
    attempts = config["claude"]["retry_attempts"]
    wait_min = config["claude"]["retry_wait_min"]
    wait_max = config["claude"]["retry_wait_max"]

    for attempt in Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    ):
        with attempt:
            response = client.messages.create(
                model=config["claude"]["model"],
                max_tokens=config["claude"]["max_tokens"],
                temperature=config["claude"].get("temperature", 0.3),
                messages=[{"role": "user", "content": prompt}],
            )
            if not response.content:
                raise ClaudeResponseError(
                    f"Claude 응답 content가 비어있음. stop_reason={response.stop_reason}"
                )
            block = response.content[0]
            if not hasattr(block, "text"):
                raise ClaudeResponseError(
                    f"첫 번째 content 블록이 TextBlock이 아님: {type(block)}"
                )
            return block.text


def parse_claude_response(response_text: str) -> dict:
    """Claude 응답 문자열에서 JSON을 추출해 요약·키워드·카테고리 dict로 반환한다.

    코드 블록(```json ... ```) 우선 파싱 후, 실패 시 중괄호 패턴으로 폴백한다.
    JSON 파싱 자체가 불가능하면 원문 500자를 summary_ko로 사용하는 폴백 dict를 반환한다.

    Args:
        response_text: Claude 응답 원문 문자열.

    Returns:
        {'summary_ko': str, 'keywords': list[str], 'category': str} 형태의 dict.
    """
    # greedy {.*}를 사용한다. non-greedy {.*?}는 summary_ko 등에 포함된 }에서
    # 조기 종료되어 JSON을 잘라내므로 json.loads가 실패한다.
    code_block = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response_text, re.DOTALL)
    json_str = code_block.group(1) if code_block else None

    if json_str is None:
        brace_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        json_str = brace_match.group(0) if brace_match else None

    if json_str is not None:
        try:
            parsed = json.loads(json_str)

            summary_ko = parsed.get("summary_ko", "")
            if not isinstance(summary_ko, str):
                summary_ko = str(summary_ko)

            keywords = parsed.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []

            category = parsed.get("category", "미분류")
            if not isinstance(category, str):
                category = "미분류"

            return {"summary_ko": summary_ko, "keywords": keywords, "category": category}
        except json.JSONDecodeError:
            pass

    logger.warning("Claude 응답 JSON 파싱 실패. 폴백값 사용.")
    return {"summary_ko": response_text[:500], "keywords": [], "category": "미분류"}


def summarize_entry(client: anthropic.Anthropic, entry: dict, config: dict) -> dict:
    """단일 피드 항목을 Claude로 요약하고 원본 항목 dict에 결과를 병합해 반환한다.

    비인증 오류는 즉시 재발생시키고, 그 외 오류는 기본값 폴백으로 처리한다.

    Args:
        client: 초기화된 anthropic.Anthropic 클라이언트.
        entry: 요약할 피드 항목 dict.
        config: 전체 애플리케이션 설정 dict.

    Returns:
        entry에 summary_ko·keywords·category가 추가된 dict.
    """
    categories = config["report"]["categories"]
    try:
        prompt = build_prompt(entry, categories)
        response_text = call_claude(client, prompt, config)
        parsed = parse_claude_response(response_text)
    except NON_RETRYABLE_EXCEPTIONS:
        raise
    except Exception as e:
        logger.warning(f"[{entry.get('company', '?')}] 요약 실패: {e}. 기본값으로 폴백.")
        parsed = {"summary_ko": "요약 실패", "keywords": [], "category": "미분류"}

    return {**entry, **parsed}


def summarize_all(client: anthropic.Anthropic, entries: list[dict], config: dict) -> list[dict]:
    """모든 피드 항목을 순서대로 요약한다. 항목 간 API 호출 지연을 적용한다.

    Args:
        client: 초기화된 anthropic.Anthropic 클라이언트.
        entries: 요약할 피드 항목 dict 리스트.
        config: 전체 애플리케이션 설정 dict.

    Returns:
        요약 결과가 병합된 항목 dict 리스트 (입력 순서 유지).
    """
    results = []
    total = len(entries)
    for i, entry in enumerate(entries):
        result = summarize_entry(client, entry, config)
        results.append(result)
        logger.info(f"Claude 요약 완료 - {i + 1}/{total}개")
        if i < total - 1:
            time.sleep(config["claude"].get("delay_between_calls", 1))
    return results
