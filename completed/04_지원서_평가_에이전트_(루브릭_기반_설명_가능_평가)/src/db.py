# [Fix] 모든 함수에 한국어 docstring 추가 (코드 품질)
import json
import logging
import sqlite3
from pathlib import Path
from src.models import EvaluationResult
from src.config import get_config, get_base_dir

logger = logging.getLogger("evaluator")

_db_conn: sqlite3.Connection | None = None


def _get_db_path() -> Path:
    """설정에서 DB 파일 경로를 읽어 반환하고 부모 디렉토리를 생성한다."""
    config = get_config()
    db_path = get_base_dir() / config["database"]["path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_conn() -> sqlite3.Connection:
    """싱글턴 패턴으로 SQLite 연결을 반환하고 최초 호출 시 테이블을 초기화한다."""
    global _db_conn
    if _db_conn is None:
        db_path = _get_db_path()
        _db_conn = sqlite3.connect(str(db_path))
        _db_conn.row_factory = sqlite3.Row
        init_db()
    return _db_conn


def init_db() -> None:
    """평가 이력 테이블과 인덱스를 생성한다."""
    conn = _get_conn() if _db_conn else sqlite3.connect(str(_get_db_path()))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            rubric_name TEXT NOT NULL,
            total_score REAL NOT NULL,
            max_total REAL NOT NULL,
            item_scores_json TEXT NOT NULL,
            strengths TEXT,
            improvements TEXT,
            follow_up_questions TEXT,
            bias_check_json TEXT,
            evaluated_at TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(file_path, rubric_name, evaluated_at)
        );

        CREATE INDEX IF NOT EXISTS idx_applicant ON evaluations(applicant_name);
        CREATE INDEX IF NOT EXISTS idx_rubric ON evaluations(rubric_name);
        CREATE INDEX IF NOT EXISTS idx_date ON evaluations(evaluated_at);
        CREATE INDEX IF NOT EXISTS idx_file_rubric_date ON evaluations(file_path, rubric_name, evaluated_at);
    """)
    conn.commit()


def save_evaluation(result: EvaluationResult) -> int:
    """평가 결과를 DB에 저장하고 삽입된 행의 ID를 반환한다."""
    conn = _get_conn()
    item_scores_json = json.dumps(
        [s.model_dump() for s in result.item_scores], ensure_ascii=False
    )
    strengths = json.dumps(result.strengths_top3, ensure_ascii=False)
    improvements = json.dumps(result.improvements_top3, ensure_ascii=False)
    questions = json.dumps(result.follow_up_questions, ensure_ascii=False)
    bias_json = json.dumps(result.bias_check.model_dump(), ensure_ascii=False) if result.bias_check else "{}"
    evaluated_at = result.evaluated_at.strftime("%Y-%m-%d %H:%M:%S")

    cursor = conn.execute(
        """INSERT OR REPLACE INTO evaluations
        (applicant_name, file_path, rubric_name, total_score, max_total,
         item_scores_json, strengths, improvements, follow_up_questions,
         bias_check_json, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.applicant_name, result.file_path, result.rubric_name,
            result.total_score, result.max_total, item_scores_json,
            strengths, improvements, questions, bias_json, evaluated_at,
        ),
    )
    conn.commit()
    logger.info(f"DB 저장 완료: {result.applicant_name} (id={cursor.lastrowid})")
    return cursor.lastrowid


def get_existing(file_path: str, rubric_name: str, date: str) -> dict | None:
    """특정 파일+루브릭+날짜 조합의 기존 평가 기록을 조회한다."""
    conn = _get_conn()
    cursor = conn.execute(
        """SELECT * FROM evaluations
        WHERE file_path = ? AND rubric_name = ? AND evaluated_at LIKE ?
        ORDER BY created_at DESC LIMIT 1""",
        (file_path, rubric_name, f"{date}%"),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_history(
    applicant: str | None = None,
    rubric: str | None = None,
    date_range: tuple[str, str] | None = None,
) -> list[dict]:
    """조건에 맞는 평가 이력을 최신순으로 조회한다."""
    conn = _get_conn()
    query = "SELECT * FROM evaluations WHERE 1=1"
    params = []

    if applicant:
        query += " AND applicant_name LIKE ?"
        params.append(f"%{applicant}%")
    if rubric:
        query += " AND rubric_name = ?"
        params.append(rubric)
    if date_range:
        query += " AND evaluated_at BETWEEN ? AND ?"
        params.extend(date_range)

    query += " ORDER BY evaluated_at DESC"
    cursor = conn.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def get_latest(applicant_name: str, rubric_name: str) -> dict | None:
    """특정 지원자+루브릭의 가장 최근 평가 기록을 반환한다."""
    conn = _get_conn()
    cursor = conn.execute(
        """SELECT * FROM evaluations
        WHERE applicant_name = ? AND rubric_name = ?
        ORDER BY evaluated_at DESC LIMIT 1""",
        (applicant_name, rubric_name),
    )
    row = cursor.fetchone()
    return dict(row) if row else None
