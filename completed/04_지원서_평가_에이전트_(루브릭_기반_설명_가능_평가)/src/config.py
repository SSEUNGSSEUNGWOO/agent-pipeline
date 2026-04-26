# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
from pathlib import Path
import yaml

_config: dict | None = None
_base_dir: Path | None = None


def load_config(path: str = "config.yaml") -> dict:
    """YAML 설정 파일을 로드하고 기본값을 병합하여 전역 설정을 초기화한다."""
    global _config, _base_dir
    config_path = Path(path)
    _base_dir = config_path.parent
    with open(config_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)

    defaults = {
        "api": {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "temperature": 0.2,
            "consistency_temperature": 0.7,
            "retry_attempts": 3,
            "retry_delay_seconds": 2,
            "retry_backoff_multiplier": 2,
            "rate_limit_max_retries": 5,
            "max_concurrency": 5,
            "timeout": 120,
        },
        "evaluation": {
            "default_rubric": None,
            "blind_mode": True,
            "max_text_length": 50000,
            "min_text_length": 50,
            "consistency_default_runs": 3,
            "consistency_threshold": 1.5,
            "max_batch_size": 100,
            "auto_select_fallback": "essay.yaml",
        },
        "text_overflow": {
            "strategy": "section_split",
            "section_delimiters": ["\\n#{1,3}\\s", "\\n\\d+\\.\\s", "\\n\\n"],
        },
        "blind": {
            "scope": "header",
            "header_lines": 10,
            "mask_patterns": [],
        },
        "output": {
            "dir": "output",
            "filename_format": "{prefix}_{name}_{date}_{time}",
            "include_charts": True,
            "chart_dpi": 150,
            "chart_style": "seaborn-v0_8-whitegrid",
            "chart_font_family": None,
        },
        "logging": {
            "dir": "logs",
            "level": "INFO",
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "retention_days": 30,
            "max_bytes": 10485760,
        },
        "database": {
            "path": "output/evaluation_history.db",
        },
        "calibration": {
            "profile_path": "calibration_profile.json",
            "min_examples": 3,
            "name_match_threshold": 0.6,
        },
    }

    for section, values in defaults.items():
        if section not in _config:
            _config[section] = values
        elif isinstance(values, dict):
            for key, val in values.items():
                if key not in _config[section]:
                    _config[section][key] = val

    return _config


def get_config() -> dict:
    """전역 설정 딕셔너리를 반환한다. 미로드 시 기본 경로에서 자동 로드한다."""
    global _config
    if _config is None:
        load_config()
    return _config


def get_base_dir() -> Path:
    """설정 파일이 위치한 기준 디렉토리 경로를 반환한다."""
    global _base_dir
    if _base_dir is None:
        return Path(".")
    return _base_dir
