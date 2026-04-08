import os
import time
import logging
import anthropic


logger = logging.getLogger("github_trending")


class ClaudeAnalyzer:
    """Claude API를 사용해 GitHub 트렌딩 레포지토리를 분석하는 클래스."""

    def __init__(self, config: dict):
        """분석기 초기화: API 키를 환경변수에서 읽고 설정을 적용한다."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.\n"
                ".env 파일에 ANTHROPIC_API_KEY=your_key_here 를 추가하거나\n"
                "환경변수로 직접 설정해 주세요.\n"
                "API 키 발급: https://console.anthropic.com/"
            )

        analyzer_cfg = config.get("analyzer", {})
        self.model = analyzer_cfg.get("model", "claude-opus-4-5")
        self.max_tokens = analyzer_cfg.get("max_tokens", 2000)
        self.top_n = analyzer_cfg.get("top_repos_for_analysis", 10)
        self.max_retries = analyzer_cfg.get("max_retries", 3)
        self.retry_delay = analyzer_cfg.get("retry_delay", 10)
        self.client = anthropic.Anthropic(api_key=api_key)

    def _build_prompt(self, repos: list[dict]) -> str:
        """분석할 레포지토리 목록을 기반으로 Claude 프롬프트를 생성한다."""
        repo_lines = []
        for i, repo in enumerate(repos[:self.top_n], 1):
            repo_lines.append(
                f"{i}. [{repo['full_name']}]({repo['url']})\n"
                f"   - 언어: {repo.get('language', '미지정')}\n"
                f"   - 설명: {repo.get('description', '설명 없음')}\n"
                f"   - 스타: {repo.get('stars', 0):,}개 (오늘 +{repo.get('stars_today', 0):,})\n"
                f"   - 포크: {repo.get('forks', 0):,}개"
            )
        
        repos_text = "\n".join(repo_lines)

        return f"""다음은 오늘 GitHub Trending에서 수집한 상위 {len(repos[:self.top_n])}개 레포지토리입니다.

{repos_text}

위 데이터를 분석하여 다음 항목을 한국어로 답변해 주세요:

1. **오늘의 주요 트렌드 요약** (3~5문장): 어떤 기술/주제가 부상하고 있는지
2. **주목할 레포지토리 TOP 3**: 각각 왜 주목해야 하는지 이유 포함
3. **언어별 동향**: 어떤 프로그래밍 언어가 두드러지는지
4. **개발자에게 주는 인사이트**: 이 트렌드가 시사하는 바

각 섹션은 명확한 제목과 함께 마크다운 형식으로 작성해 주세요."""

    def _call_api(self, prompt: str) -> str:
        """Claude API를 호출하고 응답 텍스트를 반환한다. 실패 시 재시도한다."""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Claude API 호출 중 (시도 {attempt}/{self.max_retries})...")
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                logger.info("Claude API 호출 성공")
                return message.content[0].text
            except anthropic.AuthenticationError:
                logger.error("API 키가 유효하지 않습니다. ANTHROPIC_API_KEY를 확인하세요.")
                raise
            except anthropic.RateLimitError as e:
                logger.warning(f"Rate limit 초과 (시도 {attempt}/{self.max_retries}): {e}")
            except anthropic.APIConnectionError as e:
                logger.warning(f"API 연결 오류 (시도 {attempt}/{self.max_retries}): {e}")
            except anthropic.APIStatusError as e:
                logger.warning(f"API 상태 오류 {e.status_code} (시도 {attempt}/{self.max_retries}): {e.message}")

            if attempt < self.max_retries:
                logger.info(f"{self.retry_delay}초 후 재시도...")
                time.sleep(self.retry_delay)

        logger.error("Claude API 모든 재시도 실패")
        return "분석 실패: API 호출에 반복적으로 실패했습니다."

    def analyze(self, repos: list[dict]) -> str:
        """레포지토리 목록을 받아 Claude 분석 결과를 반환한다."""
        if not repos:
            logger.warning("분석할 레포지토리가 없습니다.")
            return "분석할 데이터가 없습니다."

        logger.info(f"{len(repos[:self.top_n])}개 레포지토리 분석 시작...")
        prompt = self._build_prompt(repos)
        result = self._call_api(prompt)
        logger.info("분석 완료")
        return result
