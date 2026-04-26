# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import logging
from pathlib import Path
from src.api_client import call_claude_json
from src.rubric_loader import list_presets
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")


def auto_select_rubric(text: str) -> str:
    """지원서 텍스트를 분석하여 가장 적합한 루브릭을 자동 선택하고 경로를 반환한다."""
    config = get_config()
    fallback = config["evaluation"].get("auto_select_fallback", "essay.yaml")
    presets = list_presets()

    if not presets:
        logger.warning("프리셋 루브릭이 없습니다. 폴백 사용.")
        return str(get_base_dir() / "rubrics" / fallback)

    presets_desc = "\n".join(
        f"{i+1}. {p['file']} - {p['name']}: {p['description']}"
        for i, p in enumerate(presets)
    )

    preview = text[:2000]
    system = "지원서 텍스트를 읽고 가장 적합한 평가 루브릭을 선택하세요."
    messages = [
        {
            "role": "user",
            "content": f"""다음 지원서 텍스트를 읽고 가장 적합한 평가 루브릭을 선택하세요.

[지원서 텍스트 (처음 2000자)]
{preview}

[사용 가능한 루브릭]
{presets_desc}

JSON으로만 답변: {{"selected": "파일명.yaml", "reason": "선택 이유"}}""",
        }
    ]

    try:
        result = call_claude_json(system, messages)
        selected = result.get("selected", "")
        rubric_path = get_base_dir() / "rubrics" / selected
        if rubric_path.exists():
            logger.info(f"루브릭 자동 선택: {selected} (이유: {result.get('reason', '')})")
            return str(rubric_path)
        else:
            logger.warning(f"선택된 루브릭 파일 없음: {selected}. 폴백 사용.")
    except Exception as e:
        logger.warning(f"루브릭 자동 선택 실패: {e}. 폴백 사용.")

    return str(get_base_dir() / "rubrics" / fallback)
