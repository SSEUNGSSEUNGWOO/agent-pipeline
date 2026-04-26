# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import json
import logging
from datetime import datetime
from pathlib import Path
from src.models import EvaluationResult, BatchStatistics, CalibrationProfile
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")


def generate_filename(prefix: str, applicant_name: str, config: dict | None = None) -> str:
    """리포트 파일명을 prefix_name_date_time 형식으로 생성한다."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")
    name = applicant_name.replace(" ", "_").replace("/", "_")
    return f"{prefix}_{name}_{date_str}_{time_str}"


def write_individual_report(result: EvaluationResult) -> str:
    """개별 평가 결과를 마크다운 리포트 문자열로 생성한다."""
    lines = [
        "# 지원서 평가 리포트",
        "",
        f"- **지원자**: {result.applicant_name}",
        f"- **평가 루브릭**: {result.rubric_name}",
        f"- **평가일**: {result.evaluated_at.strftime('%Y-%m-%d')}",
        f"- **총점**: {result.total_score} / {result.max_total}",
        "",
        "---",
        "",
        "## 항목별 평가",
        "",
    ]

    current_section = ""
    for item in result.item_scores:
        if item.section_name != current_section:
            current_section = item.section_name
            lines.append(f"### {current_section}")
            lines.append("")

        lines.append(f"#### {item.item_name} ({item.score} / {item.max_score})")
        lines.append("")
        lines.append("| 항목 | 내용 |")
        lines.append("|---|---|")
        lines.append(f"| **앵커 구간** | {item.anchor_range}점 |")
        lines.append(f"| **득점 근거** | {item.scoring_rationale} |")
        if item.deduction_rationale:
            lines.append(f"| **차감 사유** | {item.deduction_rationale} |")
        if item.academic_justification:
            lines.append(f"| **평가 기준 근거** | {item.academic_justification} |")
        lines.append("")

    lines.extend(["---", "", "## 강점 TOP 3"])
    for i, s in enumerate(result.strengths_top3, 1):
        lines.append(f"{i}. {s}")

    lines.extend(["", "## 보완 필요사항 TOP 3"])
    for i, s in enumerate(result.improvements_top3, 1):
        lines.append(f"{i}. {s}")

    if result.follow_up_questions:
        lines.extend(["", "## 후속 질문 (면접/면담용)"])
        for i, q in enumerate(result.follow_up_questions, 1):
            lines.append(f"{i}. {q}")

    lines.extend(["", "---", "", "## 편향 점검 메모"])
    if result.bias_check:
        mode_text = "정규식 기반 PII 마스킹 (수동 확인 권장)" if result.bias_check.blind_mode else "미적용"
        lines.append(f"- 블라인드 모드: {mode_text}")
        if result.bias_check.flags:
            for flag in result.bias_check.flags:
                lines.append(f"- {flag}")
        else:
            lines.append("- 검출된 편향 위험 요소 없음")

    return "\n".join(lines)


def write_individual_json(result: EvaluationResult) -> str:
    """개별 평가 결과를 구조화된 JSON 문자열로 생성한다."""
    sections_data = {}
    for item in result.item_scores:
        if item.section_name not in sections_data:
            sections_data[item.section_name] = []
        sections_data[item.section_name].append({
            "name": item.item_name,
            "max_score": item.max_score,
            "score": item.score,
            "anchor_range": item.anchor_range,
            "scoring_rationale": item.scoring_rationale,
            "deduction_rationale": item.deduction_rationale,
            "academic_justification": item.academic_justification,
            "evidence_quotes": item.evidence_quotes,
        })

    output = {
        "applicant_name": result.applicant_name,
        "rubric_name": result.rubric_name,
        "evaluated_at": result.evaluated_at.isoformat(),
        "total_score": result.total_score,
        "max_total": result.max_total,
        "sections": [
            {"name": name, "items": items}
            for name, items in sections_data.items()
        ],
        "strengths_top3": result.strengths_top3,
        "improvements_top3": result.improvements_top3,
        "follow_up_questions": result.follow_up_questions,
        "bias_check": result.bias_check.model_dump() if result.bias_check else {},
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def write_comparison_report(results: list[EvaluationResult], stats: BatchStatistics) -> str:
    """복수 지원자의 평가 결과를 비교 매트릭스 마크다운으로 생성한다."""
    lines = [
        "# 비교 평가 리포트",
        "",
        f"- **루브릭**: {stats.rubric_name}",
        f"- **평가 인원**: {stats.total_applicants}명",
        f"- **평가일**: {stats.generated_at.strftime('%Y-%m-%d')}",
        "",
        "## 항목별 비교 매트릭스",
        "",
    ]

    if results:
        all_items = []
        for r in results:
            for item in r.item_scores:
                if item.item_name not in all_items:
                    all_items.append(item.item_name)

        header = "| 지원자 | " + " | ".join(all_items) + " | **총점** |"
        separator = "|---" * (len(all_items) + 2) + "|"
        lines.append(header)
        lines.append(separator)

        for r in results:
            score_map = {s.item_name: s.score for s in r.item_scores}
            row = f"| {r.applicant_name} | "
            row += " | ".join(str(score_map.get(item, "-")) for item in all_items)
            row += f" | **{r.total_score}** |"
            lines.append(row)

    lines.extend(["", "## 배치 통계"])
    if stats.item_averages:
        import statistics as stat_mod
        scores = [r.total_score for r in results]
        avg = stat_mod.mean(scores) if scores else 0
        std = stat_mod.stdev(scores) if len(scores) > 1 else 0
        lines.append(f"- **평균**: {avg:.1f}점 / 표준편차: {std:.1f}")

    if stats.cutoff_score is not None:
        lines.append(
            f"- **합격선** ({stats.cutoff_score}점): "
            f"{len(stats.passed_applicants)}명 / {stats.total_applicants}명 통과"
        )

    return "\n".join(lines)


def write_batch_stats_report(stats: BatchStatistics) -> str:
    """배치 통계를 점수 분포 및 항목별 평균/표준편차 마크다운으로 생성한다."""
    lines = [
        "# 배치 통계 리포트",
        "",
        f"- **루브릭**: {stats.rubric_name}",
        f"- **평가 인원**: {stats.total_applicants}명",
        f"- **생성일**: {stats.generated_at.strftime('%Y-%m-%d')}",
        "",
        "## 점수 분포",
        "",
        "| 구간 | 인원 |",
        "|---|---|",
    ]
    for bin_name, count in stats.score_distribution.items():
        lines.append(f"| {bin_name} | {count} |")

    lines.extend(["", "## 항목별 평균/표준편차", "", "| 항목 | 평균 | 표준편차 |", "|---|---|---|"])
    for item_name in stats.item_averages:
        avg = stats.item_averages[item_name]
        std = stats.item_std_devs.get(item_name, 0)
        lines.append(f"| {item_name} | {avg} | {std} |")

    if stats.cutoff_score is not None:
        lines.extend([
            "",
            f"## 합격선: {stats.cutoff_score}점",
            f"- 합격자: {len(stats.passed_applicants)}명",
        ])
        for name in stats.passed_applicants:
            lines.append(f"  - {name}")

    return "\n".join(lines)


def write_calibration_report(profile: CalibrationProfile) -> str:
    """캘리브레이션 프로필에서 리포트를 생성하는 래퍼 함수이다."""
    from src.calibrator import generate_calibration_report
    return generate_calibration_report(profile)


def save_report(content: str, filepath: str) -> None:
    """리포트 내용을 지정된 파일 경로에 저장한다."""
    p = Path(filepath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"리포트 저장: {filepath}")
