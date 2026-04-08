import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path


logger = logging.getLogger("github_trending")


class ReportGenerator:
    """수집 데이터와 분석 결과를 md/json/csv 형식으로 저장하는 보고서 생성기."""

    def __init__(self, config: dict):
        """보고서 생성기 초기화: 출력 디렉토리와 형식 설정을 읽는다."""
        output_cfg = config.get("output", {})
        self.output_dir = output_cfg.get("output_dir", "output")
        self.formats = output_cfg.get("formats", ["md", "json", "csv"])
        self.report_title = output_cfg.get("report_title", "GitHub 트렌딩 분석 보고서")
        self.date_format = output_cfg.get("date_format", "%Y-%m-%d")
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _get_filepath(self, date: datetime, ext: str) -> str:
        """날짜와 확장자를 기반으로 출력 파일 경로를 반환한다."""
        filename = f"trending_{date.strftime(self.date_format)}.{ext}"
        return os.path.join(self.output_dir, filename)

    def _generate_markdown(self, repos: list[dict], analysis: str, date: datetime) -> str:
        """레포지토리 목록과 분석 결과를 마크다운 문자열로 변환한다."""
        date_str = date.strftime(self.date_format)
        lines = [
            f"# {self.report_title}",
            f"",
            f"**날짜:** {date_str}  ",
            f"**수집된 레포지토리:** {len(repos)}개",
            f"",
            f"---",
            f"",
            f"## AI 분석 결과",
            f"",
            analysis,
            f"",
            f"---",
            f"",
            f"## 수집된 레포지토리 목록",
            f"",
            f"| 순위 | 레포지토리 | 언어 | 스타 | 오늘 증가 | 포크 | 설명 |",
            f"|------|-----------|------|------|-----------|------|------|",
        ]

        for i, repo in enumerate(repos, 1):
            name = f"[{repo['full_name']}]({repo['url']})"
            lang = repo.get("language") or "-"
            stars = f"{repo.get('stars', 0):,}"
            today = f"+{repo.get('stars_today', 0):,}"
            forks = f"{repo.get('forks', 0):,}"
            desc = repo.get("description", "")[:60]
            if len(repo.get("description", "")) > 60:
                desc += "..."
            lines.append(f"| {i} | {name} | {lang} | {stars} | {today} | {forks} | {desc} |")

        return "\n".join(lines)

    def _save_markdown(self, repos: list[dict], analysis: str, date: datetime) -> str:
        """마크다운 보고서를 파일로 저장하고 경로를 반환한다."""
        filepath = self._get_filepath(date, "md")
        content = self._generate_markdown(repos, analysis, date)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"마크다운 보고서 저장: {filepath}")
        return filepath

    def _save_json(self, repos: list[dict], analysis: str, date: datetime) -> str:
        """JSON 형식으로 보고서를 저장하고 경로를 반환한다."""
        filepath = self._get_filepath(date, "json")
        data = {
            "date": date.strftime(self.date_format),
            "total": len(repos),
            "analysis": analysis,
            "repositories": repos,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"JSON 보고서 저장: {filepath}")
        return filepath

    def _save_csv(self, repos: list[dict], date: datetime) -> str:
        """CSV 형식으로 레포지토리 목록을 저장하고 경로를 반환한다."""
        filepath = self._get_filepath(date, "csv")
        fieldnames = [
            "rank", "full_name", "url", "language", "stars",
            "stars_today", "forks", "description", "trending_language", "period"
        ]

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for i, repo in enumerate(repos, 1):
                row = {"rank": i}
                row.update(repo)
                writer.writerow(row)

        logger.info(f"CSV 보고서 저장: {filepath}")
        return filepath

    def generate(self, repos: list[dict], analysis: str, date: datetime = None) -> list[str]:
        """설정된 모든 형식으로 보고서를 생성하고 저장된 파일 경로 목록을 반환한다."""
        if date is None:
            date = datetime.now()

        saved_files = []

        if "md" in self.formats:
            path = self._save_markdown(repos, analysis, date)
            saved_files.append(path)

        if "json" in self.formats:
            path = self._save_json(repos, analysis, date)
            saved_files.append(path)

        if "csv" in self.formats:
            path = self._save_csv(repos, date)
            saved_files.append(path)

        logger.info(f"보고서 생성 완료: {len(saved_files)}개 파일")
        return saved_files
