# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config, get_config, get_base_dir
from src.logger import setup_logger


def parse_args() -> argparse.Namespace:
    """CLI 인자를 파싱하여 Namespace 객체로 반환한다."""
    parser = argparse.ArgumentParser(
        description="지원서 평가 에이전트 - 루브릭 기반 설명 가능 평가"
    )
    parser.add_argument("--file", type=str, help="단일 지원서 파일 경로")
    parser.add_argument("--dir", type=str, help="복수 지원서 디렉토리 경로")
    parser.add_argument("--rubric", type=str, help="루브릭 YAML 파일 경로")
    parser.add_argument("--calibrate", type=str, help="캘리브레이션 샘플 디렉토리")
    parser.add_argument("--consistency-check", action="store_true", help="일관성 검증 모드")
    parser.add_argument("--runs", type=int, default=None, help="일관성 검증 반복 횟수")
    parser.add_argument("--feedback", action="store_true", help="피드백 생성 (평가 시)")
    parser.add_argument("--feedback-from", type=str, help="기존 평가 JSON에서 피드백 재생성")
    parser.add_argument("--cutoff", type=float, help="합격 기준 점수")
    parser.add_argument("--config", type=str, default="config.yaml", help="설정 파일 경로")
    return parser.parse_args()


def validate_text(text: str, config: dict) -> tuple[str, list[str]]:
    """지원서 텍스트의 길이를 검증하고 초과 시 설정된 전략에 따라 처리한다."""
    warnings = []
    eval_config = config.get("evaluation", {})
    min_len = eval_config.get("min_text_length", 50)
    max_len = eval_config.get("max_text_length", 50000)

    if len(text) < min_len:
        warnings.append(f"텍스트 길이 부족: {len(text)}자 (최소 {min_len}자)")

    if len(text) > max_len:
        overflow_config = config.get("text_overflow", {})
        strategy = overflow_config.get("strategy", "section_split")

        if strategy == "truncate_tail":
            text = text[:max_len]
            warnings.append(f"텍스트 절삭됨 (원본 {len(text)}자 → {max_len}자)")
        else:
            warnings.append(f"텍스트 초과 ({len(text)}자). 섹션 분할 처리 예정.")

    return text, warnings


def _read_file(file_path: str) -> str:
    """파일을 읽어 인코딩을 자동 감지하여 문자열로 반환한다."""
    import chardet
    p = Path(file_path)
    if not p.is_absolute():
        p = get_base_dir() / p
    if not p.exists():
        raise FileNotFoundError(f"파일 없음: {p}")
    raw = p.read_bytes()
    detected = chardet.detect(raw)
    encoding = detected.get("encoding", "utf-8") or "utf-8"
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def main():
    """메인 진입점. CLI 인자에 따라 적절한 평가 모드를 실행한다."""
    args = parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent / config_path
    load_config(str(config_path))
    config = get_config()

    logger = setup_logger()

    if args.feedback_from:
        _mode_feedback_from(args, logger)
        return

    if args.calibrate:
        _mode_calibrate(args, config, logger)
        return

    if args.dir:
        _mode_batch(args, config, logger)
        return

    if args.file:
        _mode_single(args, config, logger)
        return

    print("사용법: python main.py --file <파일> 또는 --dir <디렉토리>")
    print("       python main.py --help 로 전체 옵션 확인")


def _mode_single(args, config, logger):
    """단일 지원서 파일을 평가하고 리포트를 생성한다."""
    from src.rubric_loader import load_rubric, validate_rubric
    from src.rubric_selector import auto_select_rubric
    from src.blind_processor import mask_pii, check_bias_risk
    from src.evaluator import evaluate
    from src.calibrator import load_profile
    from src.consistency_checker import check_consistency
    from src.feedback_generator import generate_feedback, format_feedback_md
    from src.report_writer import (
        generate_filename, write_individual_report, write_individual_json, save_report
    )
    from src.db import save_evaluation

    text = _read_file(args.file)
    text, warnings = validate_text(text, config)
    for w in warnings:
        logger.warning(w)

    if args.rubric:
        rubric = load_rubric(args.rubric)
    elif config["evaluation"].get("default_rubric"):
        rubric = load_rubric(config["evaluation"]["default_rubric"])
    else:
        rubric_path = auto_select_rubric(text)
        rubric = load_rubric(rubric_path)

    validate_rubric(rubric)
    bias_flags = check_bias_risk(rubric)
    blind_mode = config["evaluation"].get("blind_mode", True)

    pii_map = {}
    eval_text = text
    if blind_mode:
        eval_text, pii_map = mask_pii(text, config)

    calibration = load_profile()
    applicant_name = Path(args.file).stem

    if args.consistency_check:
        runs = args.runs or config["evaluation"].get("consistency_default_runs", 3)
        consistency_results, result = check_consistency(
            text=eval_text,
            rubric=rubric,
            runs=runs,
            file_path=args.file,
            applicant_name=applicant_name,
            calibration_profile=calibration,
        )
        logger.info("일관성 검증 완료:")
        for cr in consistency_results:
            status = "✓" if cr.is_stable else "⚠️"
            logger.info(f"  {status} {cr.item_name}: 평균={cr.mean}, 표준편차={cr.std_dev}")
    else:
        result = evaluate(
            text=eval_text,
            rubric=rubric,
            calibration_profile=calibration,
            file_path=args.file,
            applicant_name=applicant_name,
            blind_mode=blind_mode,
            bias_flags=bias_flags,
        )

    if pii_map:
        from src.blind_processor import unmask_pii
        result.applicant_name = unmask_pii(result.applicant_name, pii_map)

    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = generate_filename("eval", result.applicant_name, config)
    md_content = write_individual_report(result)
    json_content = write_individual_json(result)
    save_report(md_content, str(output_dir / f"{base_name}.md"))
    save_report(json_content, str(output_dir / f"{base_name}.json"))

    if args.feedback:
        feedback = generate_feedback(result)
        fb_name = generate_filename("feedback", result.applicant_name, config)
        fb_content = format_feedback_md(feedback)
        save_report(fb_content, str(output_dir / f"{fb_name}.md"))

    save_evaluation(result)
    logger.info(f"평가 완료: {result.applicant_name} - {result.total_score}/{result.max_total}")


def _mode_batch(args, config, logger):
    """디렉토리 내 복수 지원서를 배치 평가하고 비교 리포트를 생성한다."""
    from src.rubric_loader import load_rubric, validate_rubric
    from src.rubric_selector import auto_select_rubric
    from src.calibrator import load_profile
    from src.comparator import batch_evaluate, generate_comparison_matrix
    from src.chart_generator import create_radar_chart, create_histogram, create_item_comparison_chart
    from src.report_writer import (
        generate_filename, write_comparison_report, write_batch_stats_report, save_report
    )
    from src.db import save_evaluation

    if args.rubric:
        rubric = load_rubric(args.rubric)
    elif config["evaluation"].get("default_rubric"):
        rubric = load_rubric(config["evaluation"]["default_rubric"])
    else:
        sample_dir = Path(args.dir)
        if not sample_dir.is_absolute():
            sample_dir = get_base_dir() / sample_dir
        sample_files = list(sample_dir.glob("*.txt"))
        if sample_files:
            sample_text = _read_file(str(sample_files[0]))
            rubric_path = auto_select_rubric(sample_text)
            rubric = load_rubric(rubric_path)
        else:
            from src.rubric_loader import load_rubric as lr
            fallback = config["evaluation"].get("auto_select_fallback", "essay.yaml")
            rubric = lr(str(get_base_dir() / "rubrics" / fallback))

    validate_rubric(rubric)
    calibration = load_profile()

    results, stats = batch_evaluate(
        dir_path=args.dir,
        rubric=rubric,
        cutoff=args.cutoff,
        calibration_profile=calibration,
    )

    if not results:
        logger.warning("평가 결과가 없습니다.")
        return

    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    if config["output"].get("include_charts", True) and len(results) > 1:
        create_radar_chart(results, rubric)
        create_histogram(results)
        create_item_comparison_chart(results)

    base_name = generate_filename("comparison", "batch", config)
    comp_report = write_comparison_report(results, stats)
    stats_report = write_batch_stats_report(stats)
    save_report(comp_report, str(output_dir / f"{base_name}.md"))
    save_report(stats_report, str(output_dir / f"batch_stats_{base_name.split('_', 1)[1]}.md"))

    for result in results:
        save_evaluation(result)

    logger.info(f"배치 평가 완료: {len(results)}건")
    if args.cutoff is not None:
        logger.info(f"합격선 {args.cutoff}점: {len(stats.passed_applicants)}명 통과")
        for name in stats.passed_applicants:
            logger.info(f"  ✓ {name}")


def _mode_calibrate(args, config, logger):
    """캘리브레이션 샘플로 에이전트 채점 편향을 분석하고 보정 프로필을 생성한다."""
    from src.rubric_loader import load_rubric, validate_rubric
    from src.calibrator import run_calibration, save_profile, generate_calibration_report
    from src.report_writer import generate_filename, save_report

    if not args.rubric:
        logger.error("캘리브레이션 모드에는 --rubric 지정이 필수입니다.")
        sys.exit(1)

    rubric = load_rubric(args.rubric)
    validate_rubric(rubric)

    profile = run_calibration(args.calibrate, rubric)
    save_profile(profile)

    report = generate_calibration_report(profile)
    print(report)

    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = generate_filename("calibration", "report", config)
    save_report(report, str(output_dir / f"{base_name}.md"))

    logger.info(f"캘리브레이션 완료. 일치율: {profile.overall_agreement_rate:.1%}")


def _mode_feedback_from(args, logger):
    """기존 평가 JSON 파일에서 피드백 리포트를 재생성한다."""
    from src.feedback_generator import generate_feedback_from_file, format_feedback_md
    from src.report_writer import generate_filename, save_report

    feedback = generate_feedback_from_file(args.feedback_from)
    content = format_feedback_md(feedback)

    output_dir = get_base_dir() / get_config()["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = generate_filename("feedback", feedback.applicant_name, get_config())
    filepath = str(output_dir / f"{base_name}.md")
    save_report(content, filepath)
    logger.info(f"피드백 생성 완료: {filepath}")


if __name__ == "__main__":
    main()
