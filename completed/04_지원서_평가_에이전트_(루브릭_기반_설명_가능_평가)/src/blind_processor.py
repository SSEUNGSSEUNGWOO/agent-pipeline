# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import re
import logging
from src.config import get_config
from src.models import Rubric

logger = logging.getLogger("evaluator")


def mask_pii(text: str, config: dict | None = None) -> tuple[str, dict]:
    """지원서 텍스트에서 개인식별정보(PII)를 마스킹하고 복원 맵을 반환한다."""
    if config is None:
        config = get_config()
    blind_config = config.get("blind", {})
    scope = blind_config.get("scope", "header")
    header_lines = blind_config.get("header_lines", 10)
    patterns = blind_config.get("mask_patterns", [])

    pii_map = {}
    counter = {"name": 0, "age": 0, "gender": 0, "university": 0, "phone": 0, "email": 0}

    if scope == "header":
        lines = text.split("\n")
        header = "\n".join(lines[:header_lines])
        body = "\n".join(lines[header_lines:])
        masked_header = _apply_patterns(header, patterns, pii_map, counter)
        return masked_header + "\n" + body, pii_map
    else:
        masked = _apply_patterns(text, patterns, pii_map, counter)
        return masked, pii_map


def _apply_patterns(text: str, patterns: list[dict], pii_map: dict, counter: dict) -> str:
    """정규식 패턴 목록을 순회하며 텍스트에서 PII를 치환한다."""
    for pat_info in patterns:
        pat_type = pat_info.get("type", "")
        pattern = pat_info.get("pattern", "")
        if not pattern:
            continue

        try:
            category = _get_category(pat_type)
            matches = list(re.finditer(pattern, text))
            for match in reversed(matches):
                original = match.group(0)
                if pat_type in ("name_labeled", "name_inline"):
                    if match.lastindex and match.lastindex >= 2:
                        original = match.group(2)
                counter[category] = counter.get(category, 0) + 1
                placeholder = f"[{category.upper()}_{counter[category]}]"
                pii_map[placeholder] = original
                if pat_type == "name_labeled":
                    prefix = match.group(1)
                    text = text[:match.start()] + f"{prefix}: {placeholder}" + text[match.end():]
                elif pat_type == "name_inline":
                    prefix = match.group(1)
                    suffix = match.group(3)
                    text = text[:match.start()] + f"{prefix} {placeholder}{suffix}" + text[match.end():]
                else:
                    text = text[:match.start()] + placeholder + text[match.end():]
        except re.error as e:
            logger.warning(f"PII 패턴 정규식 에러 ({pat_type}): {e}")
            continue

    return text


def _get_category(pat_type: str) -> str:
    """PII 패턴 유형 문자열에서 카테고리명을 추출한다."""
    if "name" in pat_type:
        return "name"
    elif "age" in pat_type:
        return "age"
    elif "gender" in pat_type:
        return "gender"
    elif "university" in pat_type or "univ" in pat_type:
        return "university"
    elif "phone" in pat_type:
        return "phone"
    elif "email" in pat_type:
        return "email"
    return "pii"


def unmask_pii(text: str, pii_map: dict) -> str:
    """마스킹된 텍스트에서 이름 플레이스홀더를 원래 값으로 복원한다."""
    for placeholder, original in pii_map.items():
        if "NAME" in placeholder:
            text = text.replace(placeholder, original)
    return text


def check_bias_risk(rubric: Rubric) -> list[str]:
    """루브릭 항목에서 편향 위험 키워드를 검출하여 경고 목록을 반환한다."""
    flags = []
    bias_keywords = {
        "성별": "성별 관련 평가 항목이 포함되어 있습니다.",
        "나이": "나이 관련 평가 항목이 포함되어 있습니다.",
        "학력": "학력 편향 위험이 있는 항목이 포함되어 있습니다.",
        "출신": "출신 편향 위험이 있는 항목이 포함되어 있습니다.",
        "대학": "대학 편향 위험이 있는 항목이 포함되어 있습니다.",
    }
    for section in rubric.sections:
        for item in section.items:
            item_text = f"{item.name} {item.evidence_guide or ''}"
            for keyword, msg in bias_keywords.items():
                if keyword in item_text:
                    flags.append(msg)

    return list(set(flags))
