# Fixed: 모든 함수에 한국어 docstring 추가
import time
import anthropic
from loguru import logger
from tenacity import Retrying, stop_after_attempt, wait_fixed, wait_exponential, retry_if_exception_type


_CTX = ('prompt is too long', 'input length exceeds', 'too many tokens', 'context_length_exceeded',)


def build_prompt(paper: dict) -> str:
    """논문 딕셔너리에서 Claude API용 한국어 3줄 요약 프롬프트를 생성한다.

    제목과 초록을 포함한 고정 형식의 프롬프트 문자열을 반환한다.
    """
    title = paper['title']
    abstract = paper['abstract']
    return (
        '다음 arXiv 논문을 한국어로 3줄 요약하세요.\n'
        '반드시 아래 형식을 지켜주세요. 다른 문장은 출력하지 마세요.\n\n'
        '1. [첫 번째 핵심 내용]\n'
        '2. [두 번째 핵심 내용]\n'
        '3. [세 번째 핵심 내용]\n\n'
        f'제목: {title}\n\n'
        f'초록: {abstract}'
    )


def _is_context_length_error(e) -> bool:
    """예외가 컨텍스트 길이 초과 오류인지 판별한다.

    BadRequestError의 body 또는 message에서 알려진 컨텍스트 초과 패턴을 검사한다.
    """
    try:
        body = getattr(e, 'body', None) or dict()
        err = body.get('error', dict())
        if err.get('type', str()) == 'context_length_exceeded':
            return True
        msg = err.get('message', str()).lower()
        if msg:
            for pat in _CTX:
                if pat in msg:
                    return True
    except Exception:
        pass
    try:
        msg2 = (getattr(e, 'message', None) or str()).lower()
        for pat in _CTX:
            if pat in msg2:
                return True
    except Exception:
        pass
    return False


def _call_api(client, prompt, model, max_tokens, temperature,
             retry_attempts, retry_wait, rl_backoff_min, rl_backoff_max) -> str:
    """Claude API를 호출해 프롬프트에 대한 응답 텍스트를 반환한다.

    RateLimitError에는 지수 백오프, 그 외 오류에는 고정 대기 재시도를 적용한다.
    """
    def _wait_strategy(retry_state):
        """재시도 유형에 따라 대기 전략을 선택한다.

        RateLimitError면 지수 백오프, 그 외에는 고정 대기를 반환한다.
        """
        exc = retry_state.outcome.exception()
        if isinstance(exc, anthropic.RateLimitError):
            return wait_exponential(multiplier=2, min=rl_backoff_min, max=rl_backoff_max)(retry_state)
        return wait_fixed(retry_wait)(retry_state)

    retryer = Retrying(
        stop=stop_after_attempt(retry_attempts),
        wait=_wait_strategy,
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
            ValueError,
        )),
        reraise=True,
    )

    for attempt in retryer:
        with attempt:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{'role': 'user', 'content': prompt}],
            )
            if not response.content:
                raise ValueError('Claude API가 빈 content를 반환했습니다')
            return response.content[0].text


def summarize_paper(client, paper, model, max_tokens, temperature,
                    retry_attempts, retry_wait, abstract_truncate_chars,
                    rl_backoff_min, rl_backoff_max) -> str:
    """단일 논문을 Claude API로 요약하고 결과 문자열을 반환한다.

    초록이 없으면 '초록 없음'을 반환한다.
    컨텍스트 초과 오류 발생 시 초록을 abstract_truncate_chars로 잘라 재시도한다.
    최종 실패 시 '요약 실패'를 반환한다.
    """
    if not paper.get('abstract'):
        return '초록 없음'

    prompt = build_prompt(paper)

    try:
        return _call_api(client, prompt, model, max_tokens, temperature,
                         retry_attempts, retry_wait, rl_backoff_min, rl_backoff_max)

    except anthropic.BadRequestError as e:
        if not _is_context_length_error(e):
            pid = paper['id']
            logger.warning(f'BadRequestError (컨텍스트 초과 아님) [{pid}]: {e}')
            return '요약 실패'

        truncated = dict(paper)
        truncated['abstract'] = paper['abstract'][:abstract_truncate_chars]
        truncated_prompt = build_prompt(truncated)
        try:
            return _call_api(client, truncated_prompt, model, max_tokens, temperature,
                             retry_attempts, retry_wait, rl_backoff_min, rl_backoff_max)
        except Exception as e2:
            pid = paper['id']
            logger.warning(f'truncate 재시도 실패 [{pid}]: {type(e2).__name__}: {e2}')
            return '요약 실패'

    except (anthropic.APIConnectionError, anthropic.RateLimitError,
            anthropic.APITimeoutError, anthropic.InternalServerError) as e:
        pid = paper['id']
        logger.warning(f'API 오류 재시도 한도 초과 [{pid}]: {type(e).__name__}: {e}')
        return '요약 실패'

    except Exception as e:
        pid = paper['id']
        logger.warning(f'예상치 못한 오류 [{pid}]: {type(e).__name__}: {e}')
        return '요약 실패'


def summarize_all(client, papers, model, max_tokens, temperature,
                  retry_attempts, retry_wait, call_interval, abstract_truncate_chars,
                  rl_backoff_min, rl_backoff_max) -> list:
    """논문 목록 전체를 순차적으로 요약하고 summary 필드가 추가된 리스트를 반환한다.

    각 호출 사이에 call_interval 초 대기하여 API 부하를 조절한다.
    """
    results = []
    for i, paper in enumerate(papers):
        if i > 0:
            time.sleep(call_interval)
        summary = summarize_paper(
            client, paper, model, max_tokens, temperature,
            retry_attempts, retry_wait, abstract_truncate_chars,
            rl_backoff_min, rl_backoff_max,
        )
        results.append(dict(paper, summary=summary))
    return results
