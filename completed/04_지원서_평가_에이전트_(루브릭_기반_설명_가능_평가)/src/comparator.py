# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import asyncio
import logging
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import chardet
from src.models import Rubric, EvaluationResult, BatchStatistics, CalibrationProfile
from src.evaluator import evaluate
from src.blind_processor import mask_pii
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")


def batch_evaluate(
    dir_path: str,
    rubric: Rubric,
    cutoff: float | None = None,
    calibration_profile: CalibrationProfile | None = None,
) -> tuple[list[EvaluationResult], BatchStatistics]:
    """디렉토리 내 모든 TXT 파일을 비동기로 배치 평가하고 통계를 반환한다."""
    config = get_config()
    max_concurrency = config["api"].get("max_concurrency", 5)
    max_batch = config["evaluation"].get("max_batch_size", 100)
    blind_mode = config["evaluation"].get("blind_mode", True)

    target_dir = Path(dir_path)
    if not target_dir.is_absolute():
        target_dir = get_base_dir() / target_dir

    txt_files = sorted(target_dir.glob("*.txt"))
    if not txt_files:
        logger.warning(f"디렉토리에 TXT 파일 없음: {target_dir}")
        return [], BatchStatistics(
            rubric_name=rubric.name,
            total_applicants=0,
        )

    if len(txt_files) > max_batch:
        logger.warning(f"파일 수 초과: {len(txt_files)}건 → {max_batch}건으로 제한")
        txt_files = txt_files[:max_batch]

    results = asyncio.run(
        _run_batch(txt_files, rubric, max_concurrency, blind_mode, calibration_profile)
    )

    stats = calculate_batch_stats(results, cutoff)
    return results, stats


async def _run_batch(
    files: list[Path],
    rubric: Rubric,
    max_concurrency: int,
    blind_mode: bool,
    calibration_profile: CalibrationProfile | None,
) -> list[EvaluationResult]:
    """세마포어로 동시성을 제한하며 파일 목록을 비동기 평가한다."""
    semaphore = asyncio.Semaphore(max_concurrency)
    tasks = [
        _evaluate_single(f, rubric, semaphore, blind_mode, calibration_profile)
        for f in files
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"배치 평가 실패: {r}")
        else:
            valid_results.append(r)

    return valid_results


async def _evaluate_single(
    file_path: Path,
    rubric: Rubric,
    semaphore: asyncio.Semaphore,
    blind_mode: bool,
    calibration_profile: CalibrationProfile | None,
) -> EvaluationResult:
    """단일 파일을 읽고 블라인드 처리 후 평가하여 결과를 반환한다."""
    async with semaphore:
        raw = file_path.read_bytes()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding", "utf-8") or "utf-8"
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")

        applicant_name = file_path.stem
        if blind_mode:
            text, _ = mask_pii(text)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: evaluate(
                text=text,
                rubric=rubric,
                calibration_profile=calibration_profile,
                file_path=str(file_path),
                applicant_name=applicant_name,
                blind_mode=blind_mode,
            ),
        )
        logger.info(f"평가 완료: {applicant_name} ({result.total_score}/{result.max_total})")
        return result


def generate_comparison_matrix(results: list[EvaluationResult]) -> dict:
    """평가 결과 목록에서 지원자별 항목 점수 비교 매트릭스를 생성한다."""
    matrix = {}
    for result in results:
        row = {}
        for item_score in result.item_scores:
            row[item_score.item_name] = item_score.score
        row["총점"] = result.total_score
        matrix[result.applicant_name] = row
    return matrix


def calculate_batch_stats(
    results: list[EvaluationResult], cutoff: float | None = None
) -> BatchStatistics:
    """배치 평가 결과에서 점수 분포, 항목별 평균/표준편차, 합격자 목록을 산출한다."""
    if not results:
        return BatchStatistics(
            rubric_name="",
            total_applicants=0,
        )

    rubric_name = results[0].rubric_name
    total_scores = [r.total_score for r in results]

    bins = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
    distribution = {b: 0 for b in bins}
    for score in total_scores:
        for b in bins:
            low, high = map(int, b.split("-"))
            if low <= score < high or (high == 100 and score == 100):
                distribution[b] += 1
                break

    item_scores_map = defaultdict(list)
    for result in results:
        for item_score in result.item_scores:
            item_scores_map[item_score.item_name].append(item_score.score)

    item_averages = {name: round(statistics.mean(scores), 2) for name, scores in item_scores_map.items()}
    item_std_devs = {
        name: round(statistics.stdev(scores), 2) if len(scores) > 1 else 0.0
        for name, scores in item_scores_map.items()
    }

    passed = []
    if cutoff is not None:
        max_total = results[0].max_total if results else 0
        if cutoff > max_total:
            logger.warning(f"합격선({cutoff})이 총점({max_total})을 초과합니다.")
        passed = [r.applicant_name for r in results if r.total_score >= cutoff]

    distribution_clean = {k: v for k, v in distribution.items() if v > 0}

    return BatchStatistics(
        rubric_name=rubric_name,
        total_applicants=len(results),
        score_distribution=distribution_clean,
        item_averages=item_averages,
        item_std_devs=item_std_devs,
        cutoff_score=cutoff,
        passed_applicants=passed,
        generated_at=datetime.now(),
    )
