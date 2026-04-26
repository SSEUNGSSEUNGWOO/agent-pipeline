# Fixed: 모든 함수에 Korean docstring 추가 (0/3 → 3/3) (#5)
from __future__ import annotations

import datetime
from collections import defaultdict
from loguru import logger


def aggregate_categories(articles: list[dict]) -> dict[str, int]:
    """기사 목록의 카테고리별 기사 수를 집계해 딕셔너리로 반환한다."""
    counts: defaultdict[str, int] = defaultdict(int)
    for article in articles:
        counts[article.get("category", "")] += 1
    return dict(counts)


def render_markdown(
    date: datetime.date,
    articles: list[dict],
    analysis: dict,
    model: str,
    agent_name: str,
    categories_order: list[str],
    default_category_name: str,
    enabled_feed_count: int,
    success_feed_count: int,
    total_article_count: int,
    new_article_count: int,
    displayed_article_count: int,
    generated_at: datetime.datetime,
) -> str:
    """수집 결과와 인사이트를 마크다운 리포트 문자열로 렌더링한다."""
    lines = []

    lines.append(f"# {agent_name}")
    lines.append(f"**날짜:** {date.isoformat()}")

    if new_article_count == displayed_article_count:
        article_info = f"**신규 기사:** {new_article_count}개"
    else:
        article_info = f"**신규 기사:** {new_article_count}개 (표시: {displayed_article_count}개)"

    header_line = (
        f"**수집 피드:** {success_feed_count}/{enabled_feed_count}개"
        f" | **수집 기사:** {total_article_count}개"
        f" | {article_info}"
    )
    lines.append(header_line)

    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 오늘의 핵심 인사이트")
    lines.append("")
    for i, insight in enumerate(analysis.get("insights", []), 1):
        lines.append(f"{i}. **{insight}**")

    lines.append("")
    lines.append("---")
    lines.append("")

    category_counts = aggregate_categories(articles)
    safe_categories_order = [c for c in categories_order if c != default_category_name]
    all_order = safe_categories_order + [default_category_name]

    lines.append("## 카테고리별 분포")
    lines.append("")
    lines.append("| 카테고리 | 기사 수 |")
    lines.append("|---------|--------|")
    for cat in all_order:
        count = category_counts.get(cat, 0)
        if count > 0:
            lines.append(f"| {cat} | {count} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 수집 기사 목록")
    lines.append("")

    grouped: defaultdict[str, list[dict]] = defaultdict(list)
    for article in articles:
        grouped[article.get("category", default_category_name)].append(article)

    for cat in all_order:
        cat_articles = grouped.get(cat, [])
        if not cat_articles:
            continue
        lines.append(f"### {cat}")
        lines.append("")
        for article in cat_articles:
            lines.append(f"#### {article['title']}")
            lines.append(f"- **출처:** {article['source']}")
            if article.get("published_at"):
                lines.append(f"- **발행:** {article['published_at'].strftime('%Y-%m-%d %H:%M')} UTC")
            else:
                lines.append("- **발행:** 알 수 없음")
            if article.get("summary"):
                lines.append(f"- **요약:** {article['summary']}")
            if article.get("link"):
                lines.append(f"- **링크:** {article['link']}")
            lines.append("")

    lines.append(f"*생성 시각: {generated_at.strftime('%Y-%m-%d %H:%M:%S')} UTC | 모델: {model}*")

    return "\n".join(lines)


def save_report(content: str, output_dir, date: datetime.date, encoding: str):
    """마크다운 콘텐츠를 output_dir/{date}.md 파일로 저장하고 경로를 반환한다."""
    from pathlib import Path
    output_path = Path(output_dir) / f"{date}.md"
    with open(output_path, "w", encoding=encoding) as f:
        f.write(content)
    return output_path
