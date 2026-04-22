# 수정 내역:
# 1. group_by_region에 region_tags 파라미터 추가, 하드코딩된 {"국내", "글로벌"} 제거
# 2. generate_report에서 config["agent"]["allowed_region_tags"] 로드하여 섹션 순서/조건 동적 처리
# 3. 모든 함수에 한국어 docstring 추가
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from agent.summarizer import SummarizedArticle
from agent.utils import KST


def render_header(date_str: str, source_count: int, article_count: int) -> str:
    """보고서 상단 헤더 마크다운 문자열을 생성한다."""
    generated_at = datetime.now(tz=KST).strftime("%Y-%m-%d %H:%M:%S KST")
    return (
        f"# AI 정책 모니터 — {date_str}\n\n"
        f"> 수집 출처 {source_count}개 | 신규 글 {article_count}건 | "
        f"생성 시각: {generated_at}\n\n---"
    )


def group_by_region(articles: list[SummarizedArticle], region_tags: list[str]) -> dict[str, list]:
    """기사를 지역 태그 기준으로 그룹화하여 반환한다. 해당하지 않는 기사는 '미분류'에 넣는다."""
    region_set = set(region_tags)
    result = {region: [] for region in region_tags}
    result["미분류"] = []
    for article in articles:
        matched = False
        for region in region_tags:
            if region in article.tags:
                result[region].append(article)
                matched = True
                break
        if not matched:
            result["미분류"].append(article)
    return result


def render_article_block(article: SummarizedArticle, number: int) -> str:
    """단일 기사를 마크다운 블록 문자열로 렌더링한다."""
    tag_str = " ".join(f"`{t}`" for t in article.tags)
    lines = article.summary.split("\n")
    quoted_lines = "\n".join(f"> {i+1}. {line}" for i, line in enumerate(lines) if line.strip())
    pub_date = article.published[:10]

    return (
        f"### {number}. [{article.source_name}] {article.title}\n\n"
        f"- **링크**: {article.url}\n"
        f"- **발행일**: {pub_date}\n"
        f"- **태그**: {tag_str}\n\n"
        f"{quoted_lines}\n"
    )


def generate_report(
    articles: list[SummarizedArticle],
    output_dir: Path,
    date_str: str,
    config: dict,
    logger: logging.Logger,
) -> Path:
    """요약된 기사 목록으로 마크다운 보고서를 생성하고 파일로 저장한다."""
    region_tags = config["agent"]["allowed_region_tags"]
    grouped = group_by_region(articles, region_tags)
    source_count = len({a.source_id for a in articles})
    article_count = len(articles)
    model_name = config["claude"]["model"]
    show_untagged = config["output"].get("show_untagged_section", True)

    all_sections = region_tags + ["미분류"]

    parts = []
    counter = 1
    for region in all_sections:
        region_articles = sorted(grouped[region], key=lambda a: a.published, reverse=True)

        if region in region_tags and not region_articles:
            continue

        if region == "미분류" and not region_articles and not show_untagged:
            continue

        parts.append(f"## {region}\n\n")

        if not region_articles:
            parts.append("*(지역 태그 미확인 글 없음)*\n\n")
            parts.append("---\n\n")
        else:
            for article in region_articles:
                parts.append(render_article_block(article, counter))
                parts.append("\n---\n\n")
                counter += 1

    content = render_header(date_str, source_count, article_count)
    content += "\n\n"
    content += "".join(parts)
    content += f"*AI 정책 모니터 에이전트 자동 생성 | {model_name}*\n"

    final_path = output_dir / f"{date_str}.md"
    bak_path = output_dir / f"{date_str}.bak.md"
    tmp_path = output_dir / f"{date_str}.md.tmp"

    if final_path.exists():
        shutil.copy2(final_path, bak_path)

    if tmp_path.exists():
        tmp_path.unlink()

    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, final_path)

    logger.info(f"보고서 생성 완료: {final_path}")
    return final_path
