# Fixed: docstring 추가, 하드코딩된 arXiv API URL과 논문 링크 URL 패턴을 파라미터로 대체
import io
import urllib.parse
import urllib.request
import feedparser
from loguru import logger
from tenacity import Retrying, stop_after_attempt, wait_fixed, retry_if_exception_type


def build_query(keywords: list, search_fields: list) -> str:
    """키워드 목록과 검색 필드로 arXiv Lucene 쿼리 문자열을 생성한다.

    각 키워드를 지정된 필드에 인용부호로 감싸 OR 결합하고,
    키워드 간에도 OR로 연결한다.
    """
    groups = []
    for keyword in keywords:
        field_terms = [f'{field}:"{keyword}"' for field in search_fields]
        groups.append('(' + ' OR '.join(field_terms) + ')')
    return ' OR '.join(groups)


def parse_entry(entry, paper_url_pattern: str) -> dict:
    """feedparser entry 객체를 논문 딕셔너리로 변환한다.

    arXiv ID, 제목, 저자, 초록, 게시일, 논문 링크를 추출한다.
    paper_url_pattern은 '{arxiv_id}' 플레이스홀더를 포함해야 한다.
    """
    raw_id = entry.id.split('/abs/')[-1]
    arxiv_id = raw_id.split('v')[0]

    title = ' '.join(entry.title.split())
    abstract = getattr(entry, 'summary', '').strip()
    authors = [a.name for a in getattr(entry, 'authors', [])]
    published_raw = getattr(entry, 'published', '')
    published = published_raw[:10] if published_raw else '날짜 없음'

    return {
        'id': arxiv_id,
        'title': title,
        'authors': authors,
        'abstract': abstract,
        'link': paper_url_pattern.format(arxiv_id=arxiv_id),
        'published': published,
    }


def fetch_papers(query, max_results, sort_by, sort_order, date_from, date_to,
                 timeout, retry_attempts, retry_wait, api_url, paper_url_pattern) -> list:
    """arXiv API에서 논문 목록을 가져온다.

    날짜 필터를 포함한 전체 쿼리를 구성하고, tenacity로 재시도하며 Atom feed를 파싱한다.
    중복 arXiv ID는 제거되며, 최종 실패 시 빈 리스트를 반환한다.
    """
    date_filter = f'submittedDate:[{date_from}000000 TO {date_to}235959]'
    full_query = f'({query}) AND {date_filter}'
    encoded_query = urllib.parse.quote(full_query, safe='')
    url = (
        f'{api_url}'
        f'?search_query={encoded_query}'
        f'&max_results={max_results}'
        f'&sortBy={sort_by}'
        f'&sortOrder={sort_order}'
    )

    retryer = Retrying(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_fixed(retry_wait),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )

    try:
        for attempt in retryer:
            with attempt:
                with urllib.request.urlopen(url, timeout=timeout) as resp:
                    data = resp.read()
                result = feedparser.parse(io.BytesIO(data))
                if result.bozo:
                    raise ValueError(f'feedparser bozo 오류: {result.bozo_exception}')
                papers = {}
                for e in result.entries:
                    p = parse_entry(e, paper_url_pattern)
                    papers[p['id']] = p
                return list(papers.values())
    except Exception:
        logger.error('arXiv API 최종 실패, 빈 리스트 반환')
        return []
