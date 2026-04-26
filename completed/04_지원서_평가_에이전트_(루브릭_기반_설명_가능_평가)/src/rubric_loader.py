# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
from pathlib import Path
import yaml
from src.models import Rubric, RubricSection, RubricItem, RubricBonusRule
from src.config import get_base_dir


def load_rubric(path: str) -> Rubric:
    """지정된 경로의 YAML 파일에서 루브릭을 로드하여 Rubric 객체로 반환한다."""
    rubric_path = Path(path)
    if not rubric_path.is_absolute():
        rubric_path = get_base_dir() / rubric_path
    with open(rubric_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return _parse_rubric(data)


def _parse_rubric(data: dict) -> Rubric:
    """YAML 데이터 딕셔너리를 Rubric 객체 구조로 파싱한다."""
    sections = []
    for sec_data in data.get("sections", []):
        items = []
        for item_data in sec_data.get("items", []):
            bonus_rules = None
            if "bonus_rules" in item_data and item_data["bonus_rules"]:
                bonus_rules = [RubricBonusRule(**br) for br in item_data["bonus_rules"]]
            items.append(RubricItem(
                name=item_data["name"],
                max_score=item_data["max_score"],
                weight=item_data.get("weight", 1.0),
                scoring_anchors=item_data.get("scoring_anchors", {}),
                evidence_guide=item_data.get("evidence_guide"),
                academic_basis=item_data.get("academic_basis"),
                bonus_rules=bonus_rules,
            ))
        sections.append(RubricSection(
            name=sec_data["name"],
            scoring_type=sec_data.get("scoring_type", "standard"),
            total_subscore=sec_data.get("total_subscore"),
            items=items,
        ))
    return Rubric(
        name=data["name"],
        description=data["description"],
        total_score=data["total_score"],
        sections=sections,
    )


def list_presets() -> list[dict]:
    """rubrics 디렉토리의 프리셋 루브릭 목록을 반환한다."""
    rubrics_dir = get_base_dir() / "rubrics"
    presets = []
    if not rubrics_dir.exists():
        return presets
    for f in sorted(rubrics_dir.glob("*.yaml")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = yaml.safe_load(fp)
            presets.append({
                "file": f.name,
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
            })
        except Exception:
            continue
    return presets


def validate_rubric(rubric: Rubric) -> bool:
    """루브릭의 점수 합산 정합성과 앵커 범위 겹침을 검증한다."""
    import logging
    logger = logging.getLogger("evaluator")
    valid = True

    items_total = sum(
        item.max_score * item.weight
        for section in rubric.sections
        for item in section.items
        if section.scoring_type != "checklist"
    )

    if abs(items_total - rubric.total_score) > 0.01:
        logger.warning(
            f"루브릭 점수 합산 불일치: items 합계={items_total}, total_score={rubric.total_score}"
        )

    for section in rubric.sections:
        for item in section.items:
            anchors = item.scoring_anchors
            if not anchors:
                continue
            ranges = []
            for key in anchors:
                parts = key.replace("~", "-").split("-")
                try:
                    low = float(parts[0])
                    high = float(parts[-1])
                    ranges.append((low, high))
                except ValueError:
                    continue
            ranges.sort()
            for i in range(len(ranges) - 1):
                if ranges[i][1] >= ranges[i + 1][0]:
                    logger.warning(
                        f"앵커 범위 겹침: {item.name} - {ranges[i]} & {ranges[i+1]}"
                    )

    return valid
