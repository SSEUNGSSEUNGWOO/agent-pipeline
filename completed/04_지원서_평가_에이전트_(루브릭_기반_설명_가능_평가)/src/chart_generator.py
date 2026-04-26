# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
# [Fix] 하드코딩된 AppleGothic 폰트를 config.yaml의 chart_font_family로 설정 가능하게 변경 — 크로스 플랫폼 호환성 확보
import logging
import platform
from datetime import datetime
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from src.models import EvaluationResult, Rubric
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")


def _get_default_font() -> str:
    """현재 OS에 맞는 기본 한국어 폰트명을 반환한다."""
    system = platform.system()
    if system == "Darwin":
        return "AppleGothic"
    elif system == "Windows":
        return "Malgun Gothic"
    else:
        return "NanumGothic"


def _setup_plot():
    """차트 스타일과 폰트를 설정한다. config.yaml의 chart_font_family 값을 우선 사용한다."""
    config = get_config()
    output_config = config.get("output", {})
    try:
        plt.style.use(output_config.get("chart_style", "seaborn-v0_8-whitegrid"))
    except OSError:
        pass
    font_family = output_config.get("chart_font_family") or _get_default_font()
    plt.rcParams["font.family"] = font_family
    plt.rcParams["axes.unicode_minus"] = False


def create_radar_chart(results: list[EvaluationResult], rubric: Rubric) -> str:
    """평가 결과를 항목별 레이더 차트로 시각화하여 PNG 파일로 저장한다."""
    _setup_plot()
    config = get_config()
    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    dpi = config["output"].get("chart_dpi", 150)

    all_items = []
    for section in rubric.sections:
        if section.scoring_type == "checklist":
            continue
        for item in section.items:
            all_items.append(item.name)

    if not all_items or not results:
        return ""

    num_items = len(all_items)
    angles = np.linspace(0, 2 * np.pi, num_items, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    for result in results[:10]:
        score_map = {s.item_name: s.score for s in result.item_scores}
        max_map = {s.item_name: s.max_score for s in result.item_scores}
        values = []
        for item_name in all_items:
            score = score_map.get(item_name, 0)
            max_s = max_map.get(item_name, 1)
            values.append(score / max_s * 100 if max_s > 0 else 0)
        values += values[:1]
        ax.plot(angles, values, linewidth=1.5, label=result.applicant_name)
        ax.fill(angles, values, alpha=0.1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(all_items, size=8)
    ax.set_ylim(0, 100)
    ax.set_title("항목별 평가 비교 (정규화 %)", size=14, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)

    now = datetime.now()
    filename = f"radar_{now.strftime('%Y-%m-%d_%H-%M-%S')}.png"
    filepath = output_dir / filename
    plt.tight_layout()
    plt.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close()
    logger.info(f"레이더 차트 저장: {filepath}")
    return str(filepath)


def create_histogram(results: list[EvaluationResult]) -> str:
    """총점 분포를 히스토그램으로 시각화하여 PNG 파일로 저장한다."""
    _setup_plot()
    config = get_config()
    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    dpi = config["output"].get("chart_dpi", 150)

    if not results:
        return ""

    scores = [r.total_score for r in results]
    max_total = results[0].max_total if results else 100

    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.linspace(0, max_total, 11)
    ax.hist(scores, bins=bins, edgecolor="black", alpha=0.7, color="#4C72B0")
    ax.axvline(np.mean(scores), color="red", linestyle="--", label=f"평균: {np.mean(scores):.1f}")
    ax.set_xlabel("총점")
    ax.set_ylabel("인원")
    ax.set_title("점수 분포 히스토그램")
    ax.legend()

    now = datetime.now()
    filename = f"histogram_{now.strftime('%Y-%m-%d_%H-%M-%S')}.png"
    filepath = output_dir / filename
    plt.tight_layout()
    plt.savefig(filepath, dpi=dpi)
    plt.close()
    logger.info(f"히스토그램 저장: {filepath}")
    return str(filepath)


def create_item_comparison_chart(results: list[EvaluationResult]) -> str:
    """지원자별 항목 점수를 막대 차트로 비교하여 PNG 파일로 저장한다."""
    _setup_plot()
    config = get_config()
    output_dir = get_base_dir() / config["output"]["dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    dpi = config["output"].get("chart_dpi", 150)

    if not results:
        return ""

    all_items = []
    for r in results:
        for item in r.item_scores:
            if item.item_name not in all_items:
                all_items.append(item.item_name)

    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(all_items))
    width = 0.8 / max(len(results), 1)

    for i, result in enumerate(results[:10]):
        score_map = {s.item_name: s.score for s in result.item_scores}
        values = [score_map.get(item, 0) for item in all_items]
        ax.bar(x + i * width, values, width, label=result.applicant_name)

    ax.set_xlabel("평가 항목")
    ax.set_ylabel("점수")
    ax.set_title("항목별 비교")
    ax.set_xticks(x + width * len(results) / 2)
    ax.set_xticklabels(all_items, rotation=45, ha="right", fontsize=8)
    ax.legend(fontsize=8)

    now = datetime.now()
    filename = f"item_comparison_{now.strftime('%Y-%m-%d_%H-%M-%S')}.png"
    filepath = output_dir / filename
    plt.tight_layout()
    plt.savefig(filepath, dpi=dpi)
    plt.close()
    logger.info(f"항목 비교 차트 저장: {filepath}")
    return str(filepath)
