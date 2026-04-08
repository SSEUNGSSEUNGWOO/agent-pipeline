import json
import logging
import os
from datetime import datetime
from pathlib import Path


logger = logging.getLogger("github_trending")


class DataStore:
    """수집된 데이터를 날짜별 JSON 파일로 저장하고 불러오는 클래스."""

    def __init__(self, config: dict):
        """스토리지 초기화: 설정에서 저장 경로와 날짜 형식을 읽는다."""
        storage_cfg = config.get("storage", {})
        self.data_dir = storage_cfg.get("data_dir", "data")
        self.json_indent = storage_cfg.get("json_indent", 2)
        self.date_format = storage_cfg.get("date_format", "%Y-%m-%d")
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

    def _get_filepath(self, date: datetime) -> str:
        """날짜를 기반으로 JSON 파일 경로를 반환한다."""
        filename = f"trending_{date.strftime(self.date_format)}.json"
        return os.path.join(self.data_dir, filename)

    def save(self, repos: list[dict], analysis: str, date: datetime = None) -> str:
        """레포지토리 목록과 분석 결과를 JSON 파일로 저장하고 파일 경로를 반환한다."""
        if date is None:
            date = datetime.now()

        filepath = self._get_filepath(date)
        data = {
            "date": date.strftime(self.date_format),
            "collected_at": datetime.now().isoformat(),
            "total_repos": len(repos),
            "repositories": repos,
            "analysis": analysis,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=self.json_indent)

        logger.info(f"데이터 저장 완료: {filepath} ({len(repos)}개 레포)")
        return filepath

    def load(self, date: datetime = None) -> dict:
        """날짜에 해당하는 JSON 데이터를 불러온다. 없으면 빈 딕셔너리를 반환한다."""
        if date is None:
            date = datetime.now()

        filepath = self._get_filepath(date)
        if not os.path.exists(filepath):
            logger.info(f"저장된 데이터 없음: {filepath}")
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info(f"데이터 로드 완료: {filepath}")
        return data
