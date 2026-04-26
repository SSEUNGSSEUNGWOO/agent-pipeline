# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import logging
import statistics
from src.models import Rubric, EvaluationResult, ConsistencyResult, ItemScore, CalibrationProfile
from src.evaluator import evaluate
from src.config import get_config

logger = logging.getLogger("evaluator")


def check_consistency(
    text: str,
    rubric: Rubric,
    runs: int = 3,
    file_path: str = "",
    applicant_name: str = "미상",
    calibration_profile: CalibrationProfile | None = None,
) -> tuple[list[ConsistencyResult], EvaluationResult]:
    """동일 텍스트를 여러 번 평가하여 항목별 일관성을 검증한다."""
    config = get_config()
    threshold = config["evaluation"].get("consistency_threshold", 1.5)
    temp = config["api"].get("consistency_temperature", 0.7)

    results = []
    for i in range(runs):
        logger.info(f"일관성 검증 {i+1}/{runs}회 평가 중...")
        result = evaluate(
            text=text,
            rubric=rubric,
            calibration_profile=calibration_profile,
            file_path=file_path,
            applicant_name=applicant_name,
            temperature=temp,
        )
        results.append(result)

    consistency_results = _aggregate_scores(results, threshold)
    unstable_msgs = _flag_unstable(consistency_results)
    if unstable_msgs:
        for msg in unstable_msgs:
            logger.warning(msg)

    final_result = _build_final_result(results, rubric, file_path, applicant_name)
    return consistency_results, final_result


def _aggregate_scores(results: list[EvaluationResult], threshold: float) -> list[ConsistencyResult]:
    """복수 평가 결과에서 항목별 평균과 표준편차를 산출하고 안정성을 판정한다."""
    from collections import defaultdict
    item_scores_map = defaultdict(list)

    for result in results:
        for item_score in result.item_scores:
            item_scores_map[item_score.item_name].append(item_score.score)

    consistency_results = []
    for item_name, scores in item_scores_map.items():
        mean = statistics.mean(scores)
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0
        consistency_results.append(ConsistencyResult(
            item_name=item_name,
            scores=scores,
            mean=round(mean, 2),
            std_dev=round(std_dev, 2),
            is_stable=std_dev <= threshold,
        ))

    return consistency_results


def _flag_unstable(consistency_results: list[ConsistencyResult]) -> list[str]:
    """불안정 항목에 대한 경고 메시지 목록을 생성한다."""
    messages = []
    unstable = [r for r in consistency_results if not r.is_stable]

    if not unstable:
        return []

    if len(unstable) == len(consistency_results):
        messages.append(
            "⚠️ 전체 항목이 불안정합니다. 루브릭 앵커의 모호성을 점검하세요. "
            "scoring_anchors의 구간별 설명을 더 구체적으로 작성하면 일관성이 개선됩니다."
        )
    else:
        for r in unstable:
            messages.append(
                f"⚠️ 불안정 항목: '{r.item_name}' (표준편차: {r.std_dev:.2f}, "
                f"점수: {r.scores})"
            )

    return messages


def _build_final_result(
    results: list[EvaluationResult],
    rubric: Rubric,
    file_path: str,
    applicant_name: str,
) -> EvaluationResult:
    """복수 평가 결과를 평균 기반으로 통합하여 최종 결과를 생성한다."""
    from collections import defaultdict
    item_scores_map = defaultdict(list)

    for result in results:
        for item_score in result.item_scores:
            item_scores_map[item_score.item_name].append(item_score)

    final_items = []
    for item_name, scores_list in item_scores_map.items():
        mean_score = statistics.mean([s.score for s in scores_list])
        best = min(scores_list, key=lambda s: abs(s.score - mean_score))
        final_items.append(ItemScore(
            item_name=best.item_name,
            section_name=best.section_name,
            max_score=best.max_score,
            score=round(mean_score, 2),
            anchor_range=best.anchor_range,
            scoring_rationale=best.scoring_rationale,
            deduction_rationale=best.deduction_rationale,
            academic_justification=best.academic_justification,
            evidence_quotes=best.evidence_quotes,
        ))

    all_strengths = []
    all_improvements = []
    all_questions = []
    for r in results:
        all_strengths.extend(r.strengths_top3)
        all_improvements.extend(r.improvements_top3)
        all_questions.extend(r.follow_up_questions)

    from collections import Counter
    strengths = [s for s, _ in Counter(all_strengths).most_common(3)]
    improvements = [s for s, _ in Counter(all_improvements).most_common(3)]
    questions = [s for s, _ in Counter(all_questions).most_common(3)]

    total = sum(s.score for s in final_items)

    return EvaluationResult(
        applicant_name=applicant_name,
        file_path=file_path,
        rubric_name=rubric.name,
        total_score=round(total, 2),
        max_total=rubric.total_score,
        item_scores=final_items,
        strengths_top3=strengths,
        improvements_top3=improvements,
        follow_up_questions=questions,
        bias_check=results[0].bias_check if results else None,
    )
