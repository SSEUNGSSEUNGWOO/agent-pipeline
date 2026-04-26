# 수정 사항: 모든 함수에 한국어 docstring 추가 (Critic 이슈 #1)
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def group_by_company(entries: list[dict]) -> dict[str, list[dict]]:
    """항목 리스트를 기업명(company) 기준으로 그룹화한다.

    Args:
        entries: 요약 결과가 포함된 피드 항목 dict 리스트.

    Returns:
        {기업명: [항목, ...]} 형태의 dict. 삽입 순서를 유지한다.
    """
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        company = entry.get("company", "기타")
        if company not in groups:
            groups[company] = []
        groups[company].append(entry)
    return groups


def group_by_category(entries: list[dict], categories: list[str]) -> dict[str, list[dict]]:
    """항목 리스트를 카테고리 기준으로 그룹화한다.

    config에 정의된 카테고리 순서를 유지하며, 알 수 없는 카테고리는 '미분류'로 처리한다.
    항목이 없는 카테고리 버킷은 결과에서 제외된다.

    Args:
        entries: 요약 결과가 포함된 피드 항목 dict 리스트.
        categories: 카테고리 이름 문자열 리스트 (순서 유지).

    Returns:
        {카테고리명: [항목, ...]} 형태의 dict (빈 카테고리 제외).
    """
    buckets: dict[str, list[dict]] = {c: [] for c in categories}
    buckets["미분류"] = []
    for entry in entries:
        cat = entry.get("category", "미분류")
        if cat in buckets:
            buckets[cat].append(entry)
        else:
            buckets["미분류"].append(entry)
    return {k: v for k, v in buckets.items() if v}


def render_entry(entry: dict, show_raw: bool = False, show_company: bool = False) -> str:
    """단일 피드 항목을 마크다운 문자열로 렌더링한다.

    GFM blockquote 형식으로 요약을 출력하며, show_raw가 True이면
    원문 요약을 <details> 펼치기 블록으로 추가한다.

    Args:
        entry: 렌더링할 항목 dict.
        show_raw: True이면 원문 요약(summary_raw)을 펼치기 블록으로 포함.
        show_company: True이면 출처(기업명)를 메타 정보에 포함.

    Returns:
        마크다운 형식의 항목 문자열 (후행 구분선 포함).
    """
    title = entry.get("title", "(제목 없음)")
    link = entry.get("link", "")
    published_date = entry.get("published", "")[:10]
    company = entry.get("company", "")
    category = entry.get("category", "미분류")
    keywords = entry.get("keywords", [])

    # GFM blockquote 줄바꿈: 마지막 줄을 제외한 각 줄 끝에 trailing hard-break(  ) 추가.
    summary_lines = [line for line in entry.get("summary_ko", "").split("\n") if line.strip()]
    summary_block = "\n".join(
        f"> {line}  " if i < len(summary_lines) - 1 else f"> {line}"
        for i, line in enumerate(summary_lines)
    )

    lines = [
        f"### [{title}]({link})",
        f"- **발행일:** {published_date}",
        f"- **카테고리:** {category}",
    ]

    if show_company and company:
        lines.append(f"- **출처:** {company}")

    if keywords:
        keyword_str = ", ".join(f"`{kw}`" for kw in keywords)
        lines.append(f"- **키워드:** {keyword_str}")

    if summary_block:
        lines += ["", summary_block]

    if show_raw and entry.get("summary_raw"):
        lines += [
            "",
            "<details><summary>원문 요약</summary>",
            "",
            entry["summary_raw"],
            "",
            "</details>",
        ]

    lines += ["", "---", ""]
    return "\n".join(lines)


def render_report(entries: list[dict], date_str: str, config: dict) -> str:
    """전체 항목을 마크다운 리포트 문자열로 렌더링한다.

    config의 report.group_by 설정에 따라 기업별 또는 카테고리별로 그룹화한다.

    Args:
        entries: 요약 결과가 포함된 피드 항목 dict 리스트.
        date_str: 리포트 수집일 문자열 (YYYY-MM-DD).
        config: 전체 애플리케이션 설정 dict.

    Returns:
        마크다운 형식의 전체 리포트 문자열.
    """
    group_by = config.get("report", {}).get("group_by", "company")
    show_raw = config.get("report", {}).get("show_raw_summary", False)
    categories = config.get("report", {}).get("categories", [])

    if group_by == "category":
        groups = group_by_category(entries, categories)
        show_company = True
    elif group_by == "company":
        groups = group_by_company(entries)
        show_company = False
    else:
        logger.warning(f"알 수 없는 group_by 값: '{group_by}'. 'company'로 폴백.")
        groups = group_by_company(entries)
        show_company = False

    seen: dict[str, None] = {}
    for e in entries:
        seen[e["company"]] = None
    companies = list(seen.keys())
    total = len(entries)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# AI 기업 블로그 수집 리포트",
        f"**수집일:** {date_str}  ",
        f"**총 신규 글:** {total}개  ",
        f"**수집 기업:** {', '.join(companies)}",
        "",
        "---",
        "",
    ]
    for group_name, group_entries in groups.items():
        lines.append(f"## {group_name}\n")
        for entry in group_entries:
            lines.append(render_entry(entry, show_raw=show_raw, show_company=show_company))
    lines.append(f"*생성 시각: {now_utc} UTC*")
    return "\n".join(lines)


def save_report(content: str, output_dir: str, date_str: str) -> str:
    """리포트 내용을 output_dir에 마크다운 파일로 저장하고 경로를 반환한다.

    같은 날 이미 파일이 존재하면 '_2', '_3' 형식의 숫자 접미사를 붙인다.

    Args:
        content: 저장할 마크다운 문자열.
        output_dir: 저장 디렉토리 경로. 없으면 자동 생성.
        date_str: 파일명 기준 날짜 문자열 (YYYY-MM-DD).

    Returns:
        실제 저장된 파일의 전체 경로 문자열.
    """
    os.makedirs(output_dir, exist_ok=True)

    base_path = os.path.join(output_dir, f"{date_str}.md")
    if not os.path.exists(base_path):
        path = base_path
    else:
        n = 2
        while os.path.exists(os.path.join(output_dir, f"{date_str}_{n}.md")):
            n += 1
        path = os.path.join(output_dir, f"{date_str}_{n}.md")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
