import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import Optional


logger = logging.getLogger("github_trending")


class GitHubTrendingScraper:
    """GitHub Trending 페이지에서 레포지토리 정보를 수집하는 스크래퍼."""

    def __init__(self, config: dict):
        """스크래퍼 초기화: config에서 설정값을 읽어온다."""
        scraper_cfg = config.get("scraper", {})
        self.base_url = scraper_cfg.get("base_url", "https://github.com/trending")
        self.period = scraper_cfg.get("period", "daily")
        self.languages = scraper_cfg.get("languages", [""])
        self.timeout = scraper_cfg.get("timeout", 30)
        self.delay = scraper_cfg.get("delay_between_requests", 2)
        self.max_retries = scraper_cfg.get("max_retries", 3)
        self.retry_delay = scraper_cfg.get("retry_delay", 5)
        self.top_n = scraper_cfg.get("top_n", 25)
        self.user_agent = scraper_cfg.get("user_agent", "Mozilla/5.0")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def _build_url(self, language: str) -> str:
        """언어와 기간을 기반으로 트렌딩 URL을 생성한다."""
        if language:
            url = f"{self.base_url}/{language}"
        else:
            url = self.base_url
        
        period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
        since = period_map.get(self.period, "daily")
        return f"{url}?since={since}"

    def _fetch_page(self, url: str) -> Optional[str]:
        """지정된 URL에서 HTML을 가져온다. 실패 시 최대 max_retries 번 재시도한다."""
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"페이지 요청 중 (시도 {attempt}/{self.max_retries}): {url}")
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                logger.info(f"페이지 요청 성공: {url}")
                return response.text
            except requests.exceptions.Timeout:
                logger.warning(f"타임아웃 발생 (시도 {attempt}/{self.max_retries}): {url}")
            except requests.exceptions.HTTPError as e:
                logger.warning(f"HTTP 오류 {e.response.status_code} (시도 {attempt}/{self.max_retries}): {url}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"연결 오류 (시도 {attempt}/{self.max_retries}): {url} - {e}")
            except requests.exceptions.RequestException as e:
                logger.error(f"요청 오류 (시도 {attempt}/{self.max_retries}): {url} - {e}")
            
            if attempt < self.max_retries:
                logger.info(f"{self.retry_delay}초 후 재시도...")
                time.sleep(self.retry_delay)
        
        logger.error(f"모든 재시도 실패: {url}")
        return None

    def _parse_repos(self, html: str, language: str) -> list[dict]:
        """HTML에서 레포지토리 정보를 파싱하여 딕셔너리 목록으로 반환한다."""
        repos = []
        soup = BeautifulSoup(html, "lxml")
        
        repo_articles = soup.select("article.Box-row")
        
        if not repo_articles:
            logger.warning(f"레포지토리 파싱 결과 없음 (언어: {language or '전체'})")
            return repos

        for article in repo_articles[:self.top_n]:
            try:
                repo = self._extract_repo_data(article, language)
                if repo:
                    repos.append(repo)
            except Exception as e:
                logger.warning(f"레포 파싱 중 오류 발생, 건너뜀: {e}")
                continue

        logger.info(f"파싱 완료: {len(repos)}개 레포지토리 (언어: {language or '전체'})")
        return repos

    def _extract_repo_data(self, article, language: str) -> Optional[dict]:
        """단일 article 태그에서 레포지토리 데이터를 추출한다."""
        h2 = article.select_one("h2.h3 a")
        if not h2:
            return None

        full_name = h2.get("href", "").strip("/")
        parts = full_name.split("/")
        if len(parts) != 2:
            return None

        owner, name = parts[0], parts[1]

        desc_tag = article.select_one("p.col-9")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        lang_tag = article.select_one("span[itemprop='programmingLanguage']")
        repo_language = lang_tag.get_text(strip=True) if lang_tag else (language or "")

        stars_tag = article.select_one("a[href$='/stargazers']")
        stars_text = stars_tag.get_text(strip=True).replace(",", "") if stars_tag else "0"
        try:
            stars = int(stars_text)
        except ValueError:
            stars = 0

        forks_tag = article.select_one("a[href$='/forks']")
        forks_text = forks_tag.get_text(strip=True).replace(",", "") if forks_tag else "0"
        try:
            forks = int(forks_text)
        except ValueError:
            forks = 0

        stars_today_tag = article.select_one("span.d-inline-block.float-sm-right")
        stars_today_text = stars_today_tag.get_text(strip=True) if stars_today_tag else "0 stars today"
        stars_today = self._parse_stars_today(stars_today_text)

        return {
            "owner": owner,
            "name": name,
            "full_name": full_name,
            "url": f"https://github.com/{full_name}",
            "description": description,
            "language": repo_language,
            "stars": stars,
            "forks": forks,
            "stars_today": stars_today,
            "trending_language": language or "all",
            "period": self.period,
        }

    def _parse_stars_today(self, text: str) -> int:
        """'123 stars today' 형식의 문자열에서 숫자를 추출한다."""
        import re
        match = re.search(r"([\d,]+)", text)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                return 0
        return 0

    def scrape_all(self) -> list[dict]:
        """설정된 모든 언어에 대한 트렌딩 레포지토리를 수집하여 반환한다."""
        all_repos = []

        for language in self.languages:
            url = self._build_url(language)
            html = self._fetch_page(url)

            if html is None:
                logger.error(f"언어 '{language or '전체'}' 스크래핑 실패, 건너뜀")
                continue

            repos = self._parse_repos(html, language)
            all_repos.extend(repos)

            if language != self.languages[-1]:
                logger.info(f"{self.delay}초 대기 중...")
                time.sleep(self.delay)

        logger.info(f"전체 수집 완료: {len(all_repos)}개 레포지토리")
        return all_repos
