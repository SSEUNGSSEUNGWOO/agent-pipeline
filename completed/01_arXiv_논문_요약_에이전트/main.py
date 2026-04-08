# Fixed: docstring 추가, REQUIRED_KEYS에 arxiv.api_url·arxiv.paper_url_pattern·paths.log_retention 추가,
#        setup_logger·fetch_papers 호출 시 config에서 읽은 값 전달
from datetime import datetime, timedelta, timezone
import os
import sys
import yaml
import anthropic
from dotenv import load_dotenv
from loguru import logger
from src.logger import setup_logger
from src.fetcher import build_query, fetch_papers
from src.summarizer import summarize_all
from src.writer import write_output


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

REQUIRED_KEYS = [
    ('search', 'keywords'),
    ('search', 'search_fields'),
    ('search', 'max_results'),
    ('search', 'sort_by'),
    ('search', 'sort_order'),
    ('search', 'timeout_seconds'),
    ('search', 'date_offset_days'),
    ('arxiv', 'api_url'),
    ('arxiv', 'paper_url_pattern'),
    ('claude', 'model'),
    ('claude', 'max_tokens'),
    ('claude', 'temperature'),
    ('claude', 'call_interval_seconds'),
    ('claude', 'abstract_truncate_chars'),
    ('retry', 'attempts'),
    ('retry', 'wait_seconds'),
    ('retry', 'rate_limit_backoff_min'),
    ('retry', 'rate_limit_backoff_max'),
    ('paths', 'output_dir'),
    ('paths', 'log_dir'),
    ('paths', 'log_retention'),
]


def load_config(path: str) -> dict:
    """config.yaml 파일을 로드하고 필수 키 존재 여부를 검증한다.

    파일이 없거나 필수 키가 누락된 경우 예외를 발생시킨다.
    """
    with open(path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    for section, key in REQUIRED_KEYS:
        if section not in config or key not in config[section]:
            raise ValueError(f'config.yaml 필수 키 누락: {section}.{key}')

    for field in ('keywords', 'search_fields'):
        if not config['search'][field]:
            raise ValueError(f'config.yaml search.{field}가 비어있습니다')

    return config


def main():
    """에이전트 메인 진입점. config 로드 → 논문 수집 → 요약 → 파일 저장 순서로 실행한다."""
    config_path = os.path.join(BASE_DIR, 'config.yaml')
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
        print(f'[FATAL] config 로드 실패: {e}', file=sys.stderr)
        sys.exit(1)

    log_dir = os.path.join(BASE_DIR, config['paths']['log_dir'])
    setup_logger(log_dir, config['paths']['log_retention'])

    load_dotenv(os.path.join(BASE_DIR, '.env'))
    if not os.getenv('ANTHROPIC_API_KEY'):
        logger.error('ANTHROPIC_API_KEY가 설정되지 않았습니다')
        sys.exit(1)

    offset_days = config['search']['date_offset_days']
    now_utc = datetime.now(timezone.utc)
    target_date = now_utc + timedelta(days=offset_days)

    today = target_date.strftime('%Y-%m-%d')
    today_filter = target_date.strftime('%Y%m%d')

    client = anthropic.Anthropic()

    query = build_query(
        config['search']['keywords'],
        config['search']['search_fields'],
    )
    output_dir = os.path.join(BASE_DIR, config['paths']['output_dir'])
    papers = fetch_papers(
        query,
        config['search']['max_results'],
        config['search']['sort_by'],
        config['search']['sort_order'],
        today_filter,
        today_filter,
        config['search']['timeout_seconds'],
        config['retry']['attempts'],
        config['retry']['wait_seconds'],
        config['arxiv']['api_url'],
        config['arxiv']['paper_url_pattern'],
    )

    if not papers:
        logger.warning('수집된 논문 없음 — 빈 MD 파일 생성')

    papers = summarize_all(
        client,
        papers,
        config['claude']['model'],
        config['claude']['max_tokens'],
        config['claude']['temperature'],
        config['retry']['attempts'],
        config['retry']['wait_seconds'],
        config['claude']['call_interval_seconds'],
        config['claude']['abstract_truncate_chars'],
        config['retry']['rate_limit_backoff_min'],
        config['retry']['rate_limit_backoff_max'],
    )

    path = write_output(
        papers,
        today,
        output_dir,
        config['search']['keywords'],
    )

    logger.info(f'완료: {len(papers)}개 논문 처리 → {path}')


if __name__ == '__main__':
    main()
