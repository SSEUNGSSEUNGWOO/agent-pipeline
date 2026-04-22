# 수정 내역:
# 1. ALLOWED_REGION_TAGS, ALLOWED_CATEGORY_TAGS 모듈 상수 제거 → config.yaml에서 로드 (하드코딩 제거)
# 2. _extract_from_parsed에 config 파라미터 추가하여 config에서 허용 태그 집합 동적 생성
# 3. 모든 함수에 한국어 docstring 추가
import json
import logging
import re
import time
from dataclasses import dataclass

import anthropic

from agent.collector import Article


@dataclass
class SummarizedArticle:
    source_id: str
    source_name: str
    title: str
    url: str
    published: str
    summary: str
    tags: list[str]
    item_hash: str


def build_prompt(article: Article, config: dict) -> str:
    """Claude에 전달할 요약 요청 프롬프트를 생성한다."""
    raw_text = article.raw_text

    source_note = ""
    if article.source_type == "html":
        source_note = "\n(참고: 이 글은 목록 페이지에서 수집되어 제목만 제공됩니다.)"

    return f"""당신은 AI 정책 분석가입니다. 아래 뉴스 기사를 읽고 JSON 형식으로만 응답하세요.

기사 정보:
- 출처: {article.source_name}
- 제목: {article.title}
- 내용: {raw_text}{source_note}

다음 JSON 스키마를 정확히 따르세요. 다른 텍스트는 출력하지 마세요.

{{
  "summary": [
    "첫 번째 요약 문장 (무슨 일이 있었는지)",
    "두 번째 요약 문장 (핵심 내용 또는 배경)",
    "세 번째 요약 문장 (의미 또는 영향)"
  ],
  "tags": ["지역태그", "카테고리태그"]
}}

규칙:
- "summary"는 반드시 3개 원소를 가진 JSON 배열이어야 합니다. 문자열이 아닌 배열.
- 각 요약 문장은 한국어로 작성하고 30자 이상 80자 이하로 작성하세요.
- "tags"의 지역태그는 "국내" 또는 "글로벌" 중 하나만 선택하세요.
- "tags"의 카테고리태그는 "규제", "지원", "가이드라인", "연구", "기타" 중 하나 이상 선택하세요.
- 지역을 판단하기 어려우면 지역태그를 생략하고 카테고리태그만 넣으세요.
- 허용된 태그 값 이외의 값은 사용하지 마세요."""


def call_claude_with_retry(
    client: anthropic.Anthropic,
    prompt: str,
    config: dict,
    logger: logging.Logger,
) -> str | None:
    """Claude API를 호출하고 실패 시 설정된 횟수만큼 재시도한다."""
    retry_count = config["claude"]["retry_count"]
    retry_delay = config["claude"]["retry_delay_seconds"]

    for attempt in range(retry_count + 1):
        try:
            message = client.messages.create(
                model=config["claude"]["model"],
                max_tokens=config["claude"]["max_tokens"],
                temperature=config["claude"]["temperature"],
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text

        except anthropic.AuthenticationError:
            logger.error("API 인증 실패. 종료합니다.")
            raise SystemExit(1)
        except anthropic.PermissionDeniedError:
            logger.error("API 권한 없음. 종료합니다.")
            raise SystemExit(1)
        except anthropic.BadRequestError as e:
            logger.warning(f"잘못된 요청 (400): {e}. 스킵.")
            return None
        except anthropic.RateLimitError as e:
            wait = retry_delay
            try:
                ra = e.response.headers.get("retry-after")
                if ra:
                    wait = float(ra)
            except Exception:
                pass
            if attempt < retry_count:
                logger.warning(
                    f"RateLimitError (재시도 {attempt + 1}/{retry_count}): "
                    f"{wait:.1f}초 대기"
                )
                time.sleep(wait)
            else:
                logger.error(f"API 재시도 초과 (RateLimit): {e}")
                return None
        except (
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        ) as e:
            if attempt < retry_count:
                logger.warning(f"API 오류 (재시도 {attempt + 1}/{retry_count}): {e}")
                time.sleep(retry_delay)
            else:
                logger.error(f"API 재시도 초과: {e}")
                return None

    return None


def _extract_from_parsed(data: dict, region_tie_break: str, config: dict, logger: logging.Logger) -> tuple[str, list[str]]:
    """파싱된 JSON 딕셔너리에서 요약 문장과 유효 태그 목록을 추출한다."""
    allowed_region_tags = set(config["agent"]["allowed_region_tags"])
    allowed_category_tags = set(config["agent"]["allowed_category_tags"])
    allowed_tags = allowed_region_tags | allowed_category_tags

    summary_raw = data["summary"]

    if isinstance(summary_raw, list):
        lines = [str(s).strip() for s in summary_raw if str(s).strip()]
    elif isinstance(summary_raw, str):
        lines = [s.strip() for s in summary_raw.split("\n") if s.strip()]
    else:
        lines = []

    if len(lines) != 3:
        logger.warning(f"summary 문장 수 {len(lines)}개 (기대값: 3). 조정합니다.")
        if len(lines) > 3:
            lines = lines[:3]
        else:
            while len(lines) < 3:
                lines.append("(내용 없음)")

    summary = "\n".join(lines)

    tags_raw = data.get("tags", [])
    valid_tags = [t for t in tags_raw if t in allowed_tags]

    region_tags = [t for t in valid_tags if t in allowed_region_tags]
    if len(region_tags) > 1:
        winner = region_tie_break if region_tie_break in region_tags else region_tags[0]
        region_tags = [winner]
    category_tags = [t for t in valid_tags if t in allowed_category_tags]
    final_tags = region_tags + category_tags

    if not final_tags:
        final_tags = ["기타"]

    return (summary, final_tags)


def parse_claude_response(
    response_text: str,
    config: dict,
    logger: logging.Logger,
) -> tuple[str, list[str]]:
    """Claude 응답 텍스트를 파싱하여 요약과 태그를 반환한다. JSON 추출 실패 시 폴백 값을 반환한다."""
    tie_break = config["agent"]["region_tie_break"]

    try:
        data = json.loads(response_text.strip())
        return _extract_from_parsed(data, tie_break, config, logger)
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    first_brace = response_text.find("{")
    last_brace = response_text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = response_text[first_brace:last_brace + 1]
        try:
            data = json.loads(candidate)
            return _extract_from_parsed(data, tie_break, config, logger)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    logger.warning(f"Claude 응답 파싱 최종 실패: {response_text[:100]}")
    return ("파싱 오류\n(내용 없음)\n(내용 없음)", ["기타"])


_FALLBACK_SUMMARY = "요약 생성 실패\n(내용 없음)\n(내용 없음)"


def summarize_article(
    article: Article,
    client: anthropic.Anthropic,
    config: dict,
    logger: logging.Logger,
) -> SummarizedArticle:
    """단일 기사를 Claude API로 요약하고 SummarizedArticle을 반환한다."""
    prompt = build_prompt(article, config)
    response_text = call_claude_with_retry(client, prompt, config, logger)

    if response_text is None:
        return SummarizedArticle(
            source_id=article.source_id,
            source_name=article.source_name,
            title=article.title,
            url=article.url,
            published=article.published,
            summary=_FALLBACK_SUMMARY,
            tags=["기타"],
            item_hash=article.item_hash,
        )

    summary, tags = parse_claude_response(response_text, config, logger)
    return SummarizedArticle(
        source_id=article.source_id,
        source_name=article.source_name,
        title=article.title,
        url=article.url,
        published=article.published,
        summary=summary,
        tags=tags,
        item_hash=article.item_hash,
    )


def summarize_all(
    articles: list[Article],
    config: dict,
    logger: logging.Logger,
) -> list[SummarizedArticle]:
    """기사 목록 전체를 순차적으로 요약하고 결과 리스트를 반환한다."""
    client = anthropic.Anthropic(api_key=config["_api_key"])
    results = []
    for i, article in enumerate(articles):
        result = summarize_article(article, client, config, logger)
        results.append(result)
        if i < len(articles) - 1:
            time.sleep(config["claude"]["call_delay_seconds"])
    return results
