import argparse
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from utils import load_config, setup_logger
from scraper import GitHubTrendingScraper
from analyzer import ClaudeAnalyzer
from storage import DataStore
from reporter import ReportGenerator


def parse_args():
    """커맨드라인 인자를 파싱하여 반환한다."""
    parser = argparse.ArgumentParser(
        description="GitHub 트렌딩 레포지토리를 수집하고 Claude AI로 분석하는 도구"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="설정 파일 경로 (기본값: config.yaml)"
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=["daily", "weekly", "monthly"],
        help="수집 기간 (config.yaml 설정을 덮어씀)"
    )
    parser.add_argument(
        "--no-analyze",
        action="store_true",
        help="Claude AI 분석 건너뛰기 (스크래핑만 수행)"
    )
    parser.add_argument(
        "--lang",
        type=str,
        help="수집할 언어 (단일 언어, config.yaml 설정을 덮어씀)"
    )
    return parser.parse_args()


def run(args):
    """전체 파이프라인을 실행한다: 수집 → 분석 → 저장 → 보고서 생성."""
    load_dotenv()

    config = load_config(args.config)

    if args.period:
        config["scraper"]["period"] = args.period

    if args.lang:
        config["scraper"]["languages"] = [args.lang]

    logger = setup_logger(config)
    logger.info("=" * 60)
    logger.info("GitHub 트렌딩 분석 에이전트 시작")
    logger.info("=" * 60)

    today = datetime.now()
    all_repos = []
    analysis = "분석이 수행되지 않았습니다."

    # 스크래핑
    try:
        scraper = GitHubTrendingScraper(config)
        all_repos = scraper.scrape_all()
        if not all_repos:
            logger.warning("수집된 레포지토리가 없습니다. 네트워크 또는 파싱 문제를 확인하세요.")
        else:
            logger.info(f"총 {len(all_repos)}개 레포지토리 수집 완료")
    except Exception as e:
        logger.error(f"스크래핑 중 예상치 못한 오류 발생: {e}", exc_info=True)

    # Claude 분석
    if not args.no_analyze and all_repos:
        try:
            analyzer = ClaudeAnalyzer(config)
            analysis = analyzer.analyze(all_repos)
        except EnvironmentError as e:
            logger.error(str(e))
            analysis = "분석 실패: API 키 미설정"
        except Exception as e:
            logger.error(f"분석 중 예상치 못한 오류 발생: {e}", exc_info=True)
            analysis = f"분석 실패: {e}"

    # 데이터 저장
    try:
        store = DataStore(config)
        data_path = store.save(all_repos, analysis, today)
        logger.info(f"원본 데이터 저장: {data_path}")
    except Exception as e:
        logger.error(f"데이터 저장 중 오류 발생: {e}", exc_info=True)

    # 보고서 생성
    try:
        reporter = ReportGenerator(config)
        output_files = reporter.generate(all_repos, analysis, today)
        logger.info("=" * 60)
        logger.info("생성된 파일:")
        for f in output_files:
            logger.info(f"  - {f}")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"보고서 생성 중 오류 발생: {e}", exc_info=True)

    logger.info("GitHub 트렌딩 분석 에이전트 완료")


if __name__ == "__main__":
    args = parse_args()
    run(args)
