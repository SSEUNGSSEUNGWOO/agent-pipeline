# Fixed: main.py 없음 (항목 1), 멱등성 미확인 (항목 5), 한국어 docstring 없음 (항목 11)
# 모든 핵심 기능을 오케스트레이션하는 진입점
import os
import sys

import yaml
from dotenv import load_dotenv

from agents.hf_trending_agent import HFTrendingAgent
from utils.file_writer import save_results
from utils.logger import setup_logger


def load_config(path: str = "config.yaml") -> dict:
    """config.yaml을 로드합니다.
    
    Args:
        path: 설정 파일 경로
    
    Returns:
        설정 딕셔너리
    
    Raises:
        FileNotFoundError: 설정 파일이 없을 경우
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    """Hugging Face 트렌딩 수집 에이전트를 실행합니다."""
    load_dotenv()
    
    config = load_config()
    
    log_cfg = config.get("logging", {})
    logger = setup_logger(
        log_dir=log_cfg.get("dir", "logs"),
        level=log_cfg.get("level", "INFO"),
    )
    
    logger.info("=== Hugging Face 트렌딩 수집 에이전트 시작 ===")
    
    token = os.getenv("HF_TOKEN")
    if not token:
        logger.info("HF_TOKEN 환경 변수 없음 — 공개 API로 진행합니다.")
    
    hf_cfg = config["hf"]
    retry_cfg = config.get("retry", {})
    
    agent = HFTrendingAgent(
        base_url=hf_cfg["base_url"],
        limits=hf_cfg.get("limits", {}),
        token=token or None,
        max_attempts=retry_cfg.get("max_attempts", 3),
        delay_seconds=retry_cfg.get("delay_seconds", 2),
    )
    
    try:
        data = agent.collect(hf_cfg.get("categories", ["models"]))
    except RuntimeError as e:
        logger.error(f"수집 실패: {e}")
        sys.exit(1)
    
    out_cfg = config.get("output", {})
    saved = save_results(
        data=data,
        output_dir=out_cfg.get("dir", "output"),
        formats=out_cfg.get("formats", ["json"]),
    )
    
    logger.info(f"=== 수집 완료 — {len(saved)}개 파일 생성 ===")
    for f in saved:
        logger.info(f"  → {f}")


if __name__ == "__main__":
    main()
