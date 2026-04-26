# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import json
import logging
from datetime import datetime
from src.models import (
    Rubric, EvaluationResult, ItemScore, BiasCheck, CalibrationProfile
)
from src.api_client import call_claude_json
from src.config import get_config

logger = logging.getLogger("evaluator")


def evaluate(
    text: str,
    rubric: Rubric,
    calibration_profile: CalibrationProfile | None = None,
    file_path: str = "",
    applicant_name: str = "미상",
    blind_mode: bool = False,
    bias_flags: list[str] | None = None,
    temperature: float | None = None,
) -> EvaluationResult:
    """지원서 텍스트를 루브릭 기준으로 평가하고 EvaluationResult를 반환한다."""
    config = get_config()
    temp = temperature if temperature is not None else config["api"]["temperature"]

    system_prompt, messages = _build_evaluation_prompt(text, rubric, calibration_profile)
    try:
        response = call_claude_json(system_prompt, messages, temperature=temp)
    except Exception as e:
        logger.error(f"평가 API 호출 실패: {e}")
        item_scores = [
            ItemScore(
                item_name=item.name,
                section_name=section.name,
                max_score=item.max_score,
                score=0,
                scoring_rationale="API 호출 실패로 평가 불가",
            )
            for section in rubric.sections
            for item in section.items
            if section.scoring_type != "checklist"
        ]
        return EvaluationResult(
            applicant_name=applicant_name,
            file_path=file_path,
            rubric_name=rubric.name,
            total_score=0,
            max_total=rubric.total_score,
            item_scores=item_scores,
            bias_check=BiasCheck(blind_mode=blind_mode, flags=bias_flags or []),
        )

    item_scores, strengths, improvements, questions = _parse_evaluation_response(response, rubric)
    item_scores = _attach_academic_basis(item_scores, rubric)

    bonus_scores = _evaluate_bonus(text, rubric)
    if bonus_scores:
        item_scores.extend(bonus_scores)

    total = _calculate_total(item_scores, rubric)

    return EvaluationResult(
        applicant_name=applicant_name,
        file_path=file_path,
        rubric_name=rubric.name,
        total_score=total,
        max_total=rubric.total_score,
        item_scores=item_scores,
        strengths_top3=strengths,
        improvements_top3=improvements,
        follow_up_questions=questions,
        bias_check=BiasCheck(blind_mode=blind_mode, flags=bias_flags or []),
        evaluated_at=datetime.now(),
    )


def _build_evaluation_prompt(
    text: str,
    rubric: Rubric,
    calibration: CalibrationProfile | None = None,
) -> tuple[str, list[dict]]:
    """평가용 시스템 프롬프트와 사용자 메시지를 구성하여 반환한다."""
    system = """당신은 전문 인사평가 심사위원입니다.
반드시 제공된 루브릭의 scoring_anchors 기준만으로 평가하세요.
지원서 원문에 없는 내용을 추론하거나 가정하지 마세요."""

    rubric_yaml = _rubric_to_text(rubric)
    calibration_note = ""
    if calibration and calibration.entries:
        adjustments = [
            f"- {e.item_name}: {e.adjustment_prompt}"
            for e in calibration.entries
            if e.adjustment_prompt
        ]
        if adjustments:
            calibration_note = "\n\n[보정 지침]\n다음 보정 지침을 적용하세요:\n" + "\n".join(adjustments)

    items_json_template = []
    for section in rubric.sections:
        if section.scoring_type == "checklist":
            continue
        for item in section.items:
            items_json_template.append({
                "item_name": item.name,
                "section_name": section.name,
                "max_score": item.max_score,
            })

    user_content = f"""[평가 루브릭]
{rubric_yaml}
{calibration_note}

[지원서 텍스트]
{text}

다음 JSON 형식으로 평가 결과를 반환하세요. 반드시 유효한 JSON만 출력하세요:
{{
  "item_scores": [
    {{
      "item_name": "항목명",
      "section_name": "섹션명",
      "score": 0,
      "anchor_range": "X-Y",
      "scoring_rationale": "원문 인용 포함 득점 근거",
      "deduction_rationale": "상위 구간 미달 사유",
      "evidence_quotes": ["원문 발췌1", "원문 발췌2"]
    }}
  ],
  "strengths_top3": ["강점1", "강점2", "강점3"],
  "improvements_top3": ["보완점1", "보완점2", "보완점3"],
  "follow_up_questions": ["질문1", "질문2", "질문3"]
}}

평가 대상 항목: {json.dumps([i['item_name'] for i in items_json_template], ensure_ascii=False)}"""

    messages = [{"role": "user", "content": user_content}]
    return system, messages


def _rubric_to_text(rubric: Rubric) -> str:
    """루브릭 객체를 사람이 읽을 수 있는 텍스트 형식으로 변환한다."""
    lines = [f"# {rubric.name}", f"설명: {rubric.description}", f"총점: {rubric.total_score}", ""]
    for section in rubric.sections:
        if section.scoring_type == "checklist":
            continue
        lines.append(f"## {section.name} (유형: {section.scoring_type})")
        for item in section.items:
            lines.append(f"### {item.name} (배점: {item.max_score}, 가중치: {item.weight})")
            if item.evidence_guide:
                lines.append(f"  근거 가이드: {item.evidence_guide}")
            lines.append("  채점 앵커:")
            for anchor_range, desc in item.scoring_anchors.items():
                lines.append(f"    {anchor_range}점: {desc}")
            lines.append("")
    return "\n".join(lines)


def _parse_evaluation_response(
    response: dict, rubric: Rubric
) -> tuple[list[ItemScore], list[str], list[str], list[str]]:
    """Claude 응답 JSON을 파싱하여 항목별 점수와 강점/보완점/질문 목록을 반환한다."""
    item_scores = []
    for item_data in response.get("item_scores", []):
        max_score = item_data.get("max_score", 0)
        if max_score == 0:
            for section in rubric.sections:
                for item in section.items:
                    if item.name == item_data.get("item_name"):
                        max_score = item.max_score
                        break

        score = min(float(item_data.get("score", 0)), max_score)
        item_scores.append(ItemScore(
            item_name=item_data.get("item_name", ""),
            section_name=item_data.get("section_name", ""),
            max_score=max_score,
            score=score,
            anchor_range=item_data.get("anchor_range", ""),
            scoring_rationale=item_data.get("scoring_rationale", ""),
            deduction_rationale=item_data.get("deduction_rationale", ""),
            evidence_quotes=item_data.get("evidence_quotes", []),
        ))

    strengths = response.get("strengths_top3", [])[:3]
    improvements = response.get("improvements_top3", [])[:3]
    questions = response.get("follow_up_questions", [])[:3]

    return item_scores, strengths, improvements, questions


def _attach_academic_basis(item_scores: list[ItemScore], rubric: Rubric) -> list[ItemScore]:
    """루브릭에 정의된 학술적 근거를 각 항목 점수에 부착한다."""
    basis_map = {}
    for section in rubric.sections:
        for item in section.items:
            if item.academic_basis:
                basis_map[item.name] = item.academic_basis

    for score in item_scores:
        if score.item_name in basis_map:
            score.academic_justification = basis_map[score.item_name]

    return item_scores


def _evaluate_bonus(text: str, rubric: Rubric) -> list[ItemScore]:
    """체크리스트 유형 섹션의 보너스 항목을 평가하여 점수 목록을 반환한다."""
    checklist_sections = [s for s in rubric.sections if s.scoring_type == "checklist"]
    if not checklist_sections:
        return []

    bonus_items = []
    for section in checklist_sections:
        for item in section.items:
            bonus_items.append({"name": item.name, "max_score": item.max_score, "section": section.name})

    if not bonus_items:
        return []

    system = "지원서 텍스트에서 다음 보너스 항목의 충족 여부를 판단하세요."
    items_desc = "\n".join(
        f"- {b['name']} (최대 {b['max_score']}점)"
        for b in bonus_items
    )

    rules_desc = ""
    for section in checklist_sections:
        for item in section.items:
            if item.bonus_rules:
                for rule in item.bonus_rules:
                    rules_desc += f"\n- {item.name}: {rule.condition} → +{rule.bonus}점"

    messages = [{
        "role": "user",
        "content": f"""[보너스 항목]
{items_desc}

[충족 조건]
{rules_desc}

[지원서 텍스트]
{text}

JSON으로만 답변:
{{
  "bonus_scores": [
    {{"item_name": "항목명", "score": 0, "rationale": "충족 근거"}}
  ]
}}""",
    }]

    try:
        result = call_claude_json(system, messages)
        scores = []
        for bs in result.get("bonus_scores", []):
            section_name = ""
            max_score = 0
            for b in bonus_items:
                if b["name"] == bs.get("item_name"):
                    section_name = b["section"]
                    max_score = b["max_score"]
                    break
            scores.append(ItemScore(
                item_name=bs.get("item_name", ""),
                section_name=section_name,
                max_score=max_score,
                score=min(float(bs.get("score", 0)), max_score),
                scoring_rationale=bs.get("rationale", ""),
            ))
        return scores
    except Exception as e:
        logger.warning(f"보너스 평가 실패: {e}")
        return []


def _calculate_total(item_scores: list[ItemScore], rubric: Rubric) -> float:
    """가중치를 적용하여 전체 합산 점수를 계산한다."""
    weight_map = {}
    for section in rubric.sections:
        for item in section.items:
            weight_map[item.name] = item.weight

    total = 0.0
    for score in item_scores:
        weight = weight_map.get(score.item_name, 1.0)
        total += score.score * weight
    return round(total, 2)
