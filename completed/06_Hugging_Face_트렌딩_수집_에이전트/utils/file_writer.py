# Fixed: output/ 파일 생성 없음 (항목 6), 날짜별 파일 저장 없음 (항목 7), 출력 형식 없음 (항목 8), 함수 분리 없음 (항목 9)
import csv
import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger("hf_trending")


def save_results(data: dict[str, list[dict]], output_dir: str, formats: list[str]) -> list[str]:
    """수집 결과를 지정된 포맷으로 날짜별 파일에 저장합니다.
    
    Args:
        data: 카테고리별 트렌딩 항목 딕셔너리
        output_dir: 출력 디렉토리 경로
        formats: 저장할 포맷 목록 (json, md, csv)
    
    Returns:
        생성된 파일 경로 목록
    """
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    saved_files = []
    
    for fmt in formats:
        fmt = fmt.lower()
        filepath = os.path.join(output_dir, f"hf_trending_{date_str}.{fmt}")
        
        if fmt == "json":
            _write_json(data, filepath)
        elif fmt == "md":
            _write_markdown(data, filepath)
        elif fmt == "csv":
            _write_csv(data, filepath)
        else:
            logger.warning(f"지원하지 않는 포맷: {fmt}, 건너뜁니다.")
            continue
        
        saved_files.append(filepath)
        logger.info(f"파일 저장 완료: {filepath}")
    
    return saved_files


def _write_json(data: dict[str, list[dict]], filepath: str) -> None:
    """JSON 포맷으로 저장합니다."""
    payload: dict[str, Any] = {
        "collected_at": datetime.now().isoformat(),
        "data": data,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _write_markdown(data: dict[str, list[dict]], filepath: str) -> None:
    """Markdown 포맷으로 저장합니다."""
    lines = [
        f"# Hugging Face 트렌딩 수집 결과",
        f"",
        f"> 수집 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
    ]
    
    for category, items in data.items():
        lines.append(f"## {category.capitalize()} ({len(items)}개)")
        lines.append("")
        lines.append("| 순위 | ID | 좋아요 | 다운로드 | 작성자 |")
        lines.append("| --- | --- | --- | --- | --- |")
        
        for i, item in enumerate(items, 1):
            repo_id = item.get("id", "-")
            likes = item.get("likes", "-")
            downloads = item.get("downloads", item.get("trendingScore", "-"))
            author = item.get("author", "-")
            lines.append(f"| {i} | {repo_id} | {likes} | {downloads} | {author} |")
        
        lines.append("")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_csv(data: dict[str, list[dict]], filepath: str) -> None:
    """CSV 포맷으로 저장합니다."""
    rows = []
    for category, items in data.items():
        for rank, item in enumerate(items, 1):
            rows.append({
                "category": category,
                "rank": rank,
                "id": item.get("id", ""),
                "author": item.get("author", ""),
                "likes": item.get("likes", ""),
                "downloads": item.get("downloads", ""),
                "trending_score": item.get("trendingScore", ""),
                "pipeline_tag": item.get("pipeline_tag", ""),
                "last_modified": item.get("lastModified", ""),
            })
    
    if not rows:
        return
    
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
