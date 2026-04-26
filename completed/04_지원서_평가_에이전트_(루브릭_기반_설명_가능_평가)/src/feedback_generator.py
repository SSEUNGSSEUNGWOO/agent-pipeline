# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import json
import logging
from datetime import datetime
from pathlib import Path
from src.models import EvaluationResult, FeedbackReport
from src.db import get_latest

logger = logging.getLogger("evaluator")


def generate_feedback(eval_result: EvaluationResult) -> FeedbackReport:
    """평가 결과에서 강점과 개선점을 추출하여 피드백 리포트를 생성한다."""
    strengths = eval_result.strengths_top3[:]
    suggestions = []
    for imp in eval_result.improvements_top3:
        suggestions.append(imp)
    return FeedbackReport(
        applicant_name=eval_result.applicant_name,
        strengths=strengths,
        improvement_suggestions=suggestions,
        generated_at=datetime.now(),
    )


def generate_feedback_from_file(json_path: str) -> FeedbackReport:
    """평가 결과 JSON 파일을 읽어 피드백 리포트를 생성한다."""
    p = Path(json_path)
    if not p.exists():
        raise FileNotFoundError(f"파일 없음: {json_path}")
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = _parse_eval_json(data)
    return generate_feedback(result)


def generate_feedback_from_db(applicant_name: str, rubric_name: str) -> FeedbackReport:
    """DB에서 최신 평가 결과를 조회하여 피드백 리포트를 생성한다."""
    record = get_latest(applicant_name, rubric_name)
    if not record:
        raise ValueError(f"DB에서 평가 결과를 찾을 수 없습니다: {applicant_name}, {rubric_name}")

    from src.models import ItemScore, BiasCheck
    item_scores_data = json.loads(record["item_scores_json"])
    item_scores = [ItemScore(**d) for d in item_scores_data]
    strengths = json.loads(record["strengths"]) if record["strengths"] else []
    improvements = json.loads(record["improvements"]) if record["improvements"] else []
    questions = json.loads(record["follow_up_questions"]) if record["follow_up_questions"] else []

    result = EvaluationResult(
        applicant_name=record["applicant_name"],
        file_path=record["file_path"],
        rubric_name=record["rubric_name"],
        total_score=record["total_score"],
        max_total=record["max_total"],
        item_scores=item_scores,
        strengths_top3=strengths,
        improvements_top3=improvements,
        follow_up_questions=questions,
    )
    return generate_feedback(result)


def _parse_eval_json(data: dict) -> EvaluationResult:
    """평가 결과 JSON 딕셔너리를 EvaluationResult 객체로 변환한다."""
    from src.models import ItemScore, BiasCheck
    item_scores = []
    sections = data.get("sections", [])
    if sections:
        for section in sections:
            for item in section.get("items", []):
                item_scores.append(ItemScore(
                    item_name=item.get("name", ""),
                    section_name=section.get("name", ""),
                    max_score=item.get("max_score", 0),
                    score=item.get("score", 0),
                    anchor_range=item.get("anchor_range", ""),
                    scoring_rationale=item.get("scoring_rationale", ""),
                    deduction_rationale=item.get("deduction_rationale", ""),
                    academic_justification=item.get("academic_justification", ""),
                    evidence_quotes=item.get("evidence_quotes", []),
                ))
    else:
        for item in data.get("item_scores", []):
            item_scores.append(ItemScore(**item))

    bias_data = data.get("bias_check", {})
    bias_check = BiasCheck(**bias_data) if bias_data else BiasCheck()

    return EvaluationResult(
        applicant_name=data.get("applicant_name", "미상"),
        file_path=data.get("file_path", ""),
        rubric_name=data.get("rubric_name", ""),
        total_score=data.get("total_score", 0),
        max_total=data.get("max_total", 0),
        item_scores=item_scores,
        strengths_top3=data.get("strengths_top3", []),
        improvements_top3=data.get("improvements_top3", []),
        follow_up_questions=data.get("follow_up_questions", []),
        bias_check=bias_check,
    )


def format_feedback_md(feedback: FeedbackReport) -> str:
    """피드백 리포트를 마크다운 형식의 문자열로 포맷팅한다."""
    lines = [
        "# 지원서 피드백",
        "",
        "안녕하세요, 지원서를 검토한 결과를 안내드립니다.",
        "",
        "## 강점",
    ]
    for s in feedback.strengths:
        lines.append(f"- {s}")

    lines.extend(["", "## 개선 방향"])
    for s in feedback.improvement_suggestions:
        lines.append(f"- {s}")

    lines.extend([
        "",
        "---",
        f"*생성일: {feedback.generated_at.strftime('%Y-%m-%d %H:%M:%S')}*",
    ])
    return "\n".join(lines)
