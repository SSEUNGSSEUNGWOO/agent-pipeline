import os
import yaml
from pathlib import Path


def load_config(config_path: str = None) -> dict:
    """config.yaml 파일을 로드하여 설정 딕셔너리를 반환한다."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    return config
