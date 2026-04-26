# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from src.models import Rubric, CalibrationProfile, CalibrationEntry
from src.evaluator import evaluate
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")


def run_calibration(examples_dir: str, rubric: Rubric) -> CalibrationProfile:
    """캘리브레이션 샘플을 평가하고 사람 점수와 비교하여 보정 프로필을 생성한다."""
    config = get_config()
    min_examples = config["calibration"].get("min_examples", 3)

    examples = _load_examples(examples_dir)
    if not examples:
        logger.error("캘리브레이션 샘플이 없습니다.")
        return CalibrationProfile(
            rubric_name=rubric.name,
            entries=[],
            overall_agreement_rate=0.0,
        )

    if len(examples) < min_examples:
        logger.warning(
            f"캘리브레이션 샘플 부족: {len(examples)}건 (최소 {min_examples}건 권장). 신뢰도 낮음."
        )

    all_entries = []
    for text, human_scores, file_name in examples:
        result = evaluate(
            text=text,
            rubric=rubric,
            file_path=file_name,
            applicant_name=file_name,
        )
        name_map = _match_item_names(
            list(human_scores.keys()),
            [item.name for section in rubric.sections for item in section.items],
        )
        entries = _compare_scores(human_scores, result, name_map)
        all_entries.extend(entries)

    agreement_count = sum(1 for e in all_entries if abs(e.deviation) <= 1.0)
    agreement_rate = agreement_count / len(all_entries) if all_entries else 0.0

    for entry in all_entries:
        entry.adjustment_prompt = ""

    adjustment = _generate_adjustment(all_entries)
    if adjustment:
        for entry in all_entries:
            if abs(entry.deviation) > 1.0:
                direction = "높게" if entry.deviation > 0 else "낮게"
                entry.adjustment_prompt = (
                    f"'{entry.item_name}' 항목을 약 {abs(entry.deviation):.1f}점 {direction} "
                    f"평가하는 경향이 있습니다. 보정하여 채점하세요."
                )

    profile = CalibrationProfile(
        rubric_name=rubric.name,
        entries=all_entries,
        overall_agreement_rate=agreement_rate,
        created_at=datetime.now(),
    )

    return profile


def _load_examples(dir_path: str) -> list[tuple[str, dict, str]]:
    """캘리브레이션 디렉토리에서 텍스트 파일과 대응하는 점수 JSON을 로드한다."""
    import chardet
    examples_dir = Path(dir_path)
    if not examples_dir.is_absolute():
        examples_dir = get_base_dir() / examples_dir
    if not examples_dir.exists():
        logger.error(f"캘리브레이션 디렉토리 없음: {examples_dir}")
        return []

    results = []
    txt_files = sorted(examples_dir.glob("*.txt"))
    for txt_file in txt_files:
        score_file = txt_file.parent / f"{txt_file.stem}_scores.json"
        if not score_file.exists():
            logger.warning(f"점수 파일 없음: {score_file}")
            continue

        raw = txt_file.read_bytes()
        detected = chardet.detect(raw)
        encoding = detected.get("encoding", "utf-8") or "utf-8"
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            text = raw.decode("utf-8", errors="replace")

        try:
            with open(score_file, "r", encoding="utf-8") as f:
                score_data = json.load(f)
            human_scores = score_data.get("scores", {})
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"점수 JSON 파싱 실패: {score_file} - {e}")
            continue

        results.append((text, human_scores, txt_file.name))

    return results


def _match_item_names(human_keys: list[str], rubric_items: list[str]) -> dict[str, str]:
    """사람이 부여한 항목명을 루브릭 항목명과 유사도 기반으로 매핑한다."""
    from src.config import get_config
    config = get_config()
    threshold = config["calibration"].get("name_match_threshold", 0.6)

    name_map = {}
    for hk in human_keys:
        if hk in rubric_items:
            name_map[hk] = hk
            continue
        best_match = None
        best_ratio = 0.0
        for ri in rubric_items:
            ratio = SequenceMatcher(None, hk, ri).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = ri
        if best_ratio >= threshold and best_match:
            name_map[hk] = best_match
            logger.info(f"항목명 매핑: '{hk}' → '{best_match}' (유사도: {best_ratio:.2f})")
        else:
            logger.warning(f"항목명 매칭 불가: '{hk}' (최고 유사도: {best_ratio:.2f})")

    return name_map


def _compare_scores(
    human_scores: dict, result, name_map: dict[str, str]
) -> list[CalibrationEntry]:
    """사람 점수와 에이전트 점수를 비교하여 편차 목록을 생성한다."""
    entries = []
    agent_score_map = {s.item_name: s.score for s in result.item_scores}

    for human_key, rubric_key in name_map.items():
        human_score = float(human_scores.get(human_key, 0))
        agent_score = agent_score_map.get(rubric_key, 0.0)
        deviation = agent_score - human_score
        entries.append(CalibrationEntry(
            item_name=rubric_key,
            human_score=human_score,
            agent_score=agent_score,
            deviation=deviation,
        ))

    return entries


def _generate_adjustment(entries: list[CalibrationEntry]) -> str:
    """항목별 평균 편차를 분석하여 보정 지침 텍스트를 생성한다."""
    from collections import defaultdict
    item_devs = defaultdict(list)
    for e in entries:
        item_devs[e.item_name].append(e.deviation)

    adjustments = []
    for item_name, devs in item_devs.items():
        avg_dev = sum(devs) / len(devs)
        if abs(avg_dev) > 1.0:
            direction = "높게" if avg_dev > 0 else "낮게"
            adjustments.append(
                f"- '{item_name}': 평균 {abs(avg_dev):.1f}점 {direction} 평가 경향"
            )

    return "\n".join(adjustments) if adjustments else ""


def save_profile(profile: CalibrationProfile, path: str | None = None) -> None:
    """캘리브레이션 프로필을 JSON 파일로 저장한다."""
    if path is None:
        config = get_config()
        path = str(get_base_dir() / config["calibration"]["profile_path"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(mode="json"), f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"캘리브레이션 프로필 저장: {path}")


def load_profile(path: str | None = None) -> CalibrationProfile | None:
    """저장된 캘리브레이션 프로필을 로드하여 반환한다. 없으면 None을 반환한다."""
    if path is None:
        config = get_config()
        path = str(get_base_dir() / config["calibration"]["profile_path"])
    p = Path(path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CalibrationProfile(**data)
    except Exception as e:
        logger.warning(f"캘리브레이션 프로필 로드 실패: {e}")
        return None


def generate_calibration_report(profile: CalibrationProfile) -> str:
    """캘리브레이션 결과를 마크다운 리포트로 생성한다."""
    lines = [
        "# 캘리브레이션 리포트",
        "",
        f"- **루브릭**: {profile.rubric_name}",
        f"- **일치율 (±1점 이내)**: {profile.overall_agreement_rate:.1%}",
        f"- **생성일**: {profile.created_at}",
        "",
        "## 항목별 편차 분석",
        "",
        "| 항목 | 사람 점수 | 에이전트 점수 | 편차 | 보정 지침 |",
        "|---|---|---|---|---|",
    ]
    for entry in profile.entries:
        lines.append(
            f"| {entry.item_name} | {entry.human_score} | {entry.agent_score} | "
            f"{entry.deviation:+.1f} | {entry.adjustment_prompt or '-'} |"
        )
    return "\n".join(lines)
