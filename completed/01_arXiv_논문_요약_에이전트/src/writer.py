# Fixed: 모든 함수에 한국어 docstring 추가
import os
from loguru import logger


def format_paper(paper: dict, index: int) -> str:
    """논문 딕셔너리를 Markdown 섹션 문자열로 변환한다.

    제목, 저자, 게시일, 링크, 요약을 포함한 ## 헤더 블록을 반환한다.
    """
    title = paper['title']
    published = paper['published']
    link = paper['link']
    authors_str = ', '.join(paper['authors']) if paper['authors'] else '저자 정보 없음'
    summary_lines = paper.get('summary', '요약 없음')

    lines = [
        f'## {index}. {title}',
        '',
        f'- **저자:** {authors_str}',
        f'- **게시일:** {published}',
        f'- **링크:** {link}',
        '',
        '**요약:**',
        summary_lines,
        '',
        '---',
        '',
    ]
    return '\n'.join(lines)


def write_output(papers: list, date_str: str, output_dir: str, keywords: list) -> str:
    """논문 요약 결과를 날짜별 Markdown 파일로 저장하고 파일 경로를 반환한다.

    output_dir이 없으면 자동 생성하고, 기존 파일이 있으면 경고 후 덮어쓴다.
    논문이 없으면 헤더만 있는 빈 파일을 생성한다.
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f'{date_str}.md')

    if os.path.exists(path):
        logger.warning(f'기존 파일 덮어씀: {path}')

    if not papers:
        logger.warning(f'저장할 논문이 없음 — 헤더만 있는 파일 생성: {path}')

    keywords_str = ', '.join(keywords)
    header = (
        f'# arXiv 논문 요약 — {date_str}\n\n'
        f'> 키워드: {keywords_str} | 수집: {len(papers)}개\n\n'
        f'---\n\n'
    )
    body = ''.join(format_paper(p, i + 1) for i, p in enumerate(papers))

    with open(path, 'w', encoding='utf-8') as f:
        f.write(header + body)

    logger.info(f'파일 저장: {path}')
    return path
