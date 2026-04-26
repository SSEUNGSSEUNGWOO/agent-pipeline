# 지원서 평가 에이전트 (루브릭 기반 설명 가능 평가)

YAML 루브릭 기반으로 지원서 텍스트를 자동 평가하는 CLI 에이전트입니다. 모든 채점에 대해 원문 인용 근거(1층)와 학술 근거(2층)를 제공하여 "왜 이 점수인지" 설명 가능한 평가를 수행합니다.

---

## 주요 기능

- **루브릭 기반 평가**: YAML 형식 커스텀 루브릭으로 항목별 채점
- **2층 설명 구조**: 원문 인용 + 학술 근거로 평가 투명성 확보
- **블라인드 모드**: PII 자동 마스킹으로 편향 최소화
- **배치 평가**: 복수 지원서 비동기 병렬 처리 + 비교 매트릭스
- **캘리브레이션**: 사람 평가와 비교·보정하여 정확도 향상
- **일관성 검증**: N회 반복 평가로 채점 안정성 확인
- **시각화**: 레이더 차트, 히스토그램 자동 생성
- **피드백 생성**: 점수 제외한 지원자 안내용 피드백
- **이력 관리**: SQLite DB에 모든 평가 결과 누적 저장
- **루브릭 자동 선택**: 지원서 내용 분석 후 최적 루브릭 추천

---

## 요구사항

- **Python**: 3.11 이상
- **API 키**: Anthropic API Key (Claude 사용)
- **OS**: macOS, Linux, Windows

---

## 설치 방법

```bash
# 저장소 클론 후 해당 디렉토리로 이동
cd application-evaluator

# 가상환경 생성
python -m venv .venv

# 가상환경 활성화
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt
```

---

## 환경 설정

### `.env` 파일 작성

```bash
cp .env.example .env
```

`.env` 파일을 열어 API 키를 입력합니다:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**API 키 발급**: [Anthropic Console](https://console.anthropic.com/) → API Keys → Create Key

---

## config.yaml 설정

### API 설정

| 필드 | 기본값 | 설명 |
|---|---|---|
| `api.model` | `claude-sonnet-4-20250514` | 사용할 Claude 모델 |
| `api.max_tokens` | `8192` | 최대 응답 토큰 수 |
| `api.temperature` | `0.2` | 평가 시 temperature (낮을수록 일관적) |
| `api.consistency_temperature` | `0.7` | 일관성 검증 시 다양성을 위한 높은 값 |
| `api.retry_attempts` | `3` | 일반 API 에러 재시도 횟수 |
| `api.retry_delay_seconds` | `2` | 재시도 간 대기 시간 (초) |
| `api.retry_backoff_multiplier` | `2` | 지수 백오프 배수 |
| `api.rate_limit_max_retries` | `5` | Rate limit (429) 전용 재시도 |
| `api.max_concurrency` | `5` | 배치 모드 동시 API 호출 수 |

### 평가 설정

| 필드 | 기본값 | 설명 |
|---|---|---|
| `evaluation.default_rubric` | `null` | 기본 루브릭 경로 (null이면 자동 선택) |
| `evaluation.blind_mode` | `true` | PII 마스킹 활성화 |
| `evaluation.max_text_length` | `50000` | 지원서 최대 글자 수 |
| `evaluation.min_text_length` | `50` | 최소 글자 수 (미달 시 경고) |
| `evaluation.consistency_default_runs` | `3` | 일관성 검증 기본 반복 횟수 |
| `evaluation.consistency_threshold` | `1.5` | 표준편차 경고 임계값 |
| `evaluation.max_batch_size` | `100` | 배치 최대 파일 수 |
| `evaluation.auto_select_fallback` | `essay.yaml` | 자동 선택 실패 시 폴백 루브릭 |

### 블라인드 모드

| 필드 | 기본값 | 설명 |
|---|---|---|
| `blind.scope` | `header` | 마스킹 범위: `header` (첫 N줄) / `full` (전체) |
| `blind.header_lines` | `10` | scope=header일 때 대상 줄 수 |

### 출력 설정

| 필드 | 기본값 | 설명 |
|---|---|---|
| `output.dir` | `output` | 결과 출력 폴더 |
| `output.include_charts` | `true` | 차트 자동 생성 여부 |
| `output.chart_dpi` | `150` | 차트 해상도 |

### 텍스트 초과 처리

| 필드 | 기본값 | 설명 |
|---|---|---|
| `text_overflow.strategy` | `section_split` | `section_split` (섹션 분할) / `truncate_tail` (뒷부분 절삭) |

---

## 실행 방법

### 단일 파일 평가

```bash
# 루브릭 자동 선택
python main.py --file 지원서.txt

# 루브릭 지정
python main.py --file 지원서.txt --rubric rubrics/ax_training.yaml

# 피드백 동시 생성
python main.py --file 지원서.txt --rubric rubrics/ax_training.yaml --feedback
```

### 디렉토리 배치 평가

```bash
# 전체 평가
python main.py --dir applications/ --rubric rubrics/job_hiring.yaml

# 합격선 지정
python main.py --dir applications/ --rubric rubrics/ax_training.yaml --cutoff 34
```

### 일관성 검증

```bash
# 기본 3회 반복
python main.py --file 지원서.txt --rubric rubrics/ax_training.yaml --consistency-check

# 5회 반복
python main.py --file 지원서.txt --rubric rubrics/ax_training.yaml --consistency-check --runs 5
```

### 캘리브레이션

```bash
python main.py --calibrate examples/ --rubric rubrics/ax_training.yaml
```

### 기존 결과에서 피드백 재생성

```bash
python main.py --feedback-from output/eval_홍길동_2026-04-18_14-30-00.json
```

### 전체 CLI 옵션

```
옵션                          설명
--file PATH                  단일 지원서 파일 경로
--dir PATH                   복수 지원서 디렉토리 경로
--rubric PATH                루브릭 YAML 파일 경로
--calibrate PATH             캘리브레이션 샘플 디렉토리
--consistency-check          일관성 검증 모드
--runs N                     일관성 검증 반복 횟수 (기본: 3)
--feedback                   피드백 동시 생성
--feedback-from PATH         기존 평가 JSON에서 피드백 재생성
--cutoff SCORE               합격 기준 점수
--config PATH                설정 파일 경로 (기본: config.yaml)
```

---

## 출력 결과

### output/ 폴더 구조

```
output/
├── eval_홍길동_2026-04-18_14-30-00.md       # 개별 평가 리포트 (마크다운)
├── eval_홍길동_2026-04-18_14-30-00.json     # 구조화 평가 결과 (JSON)
├── feedback_홍길동_2026-04-18_14-30-00.md   # 지원자 피드백
├── comparison_batch_2026-04-18_14-30-00.md  # 비교 평가 리포트
├── batch_stats_batch_2026-04-18_14-30-00.md # 배치 통계
├── calibration_report_2026-04-18_14-30-00.md # 캘리브레이션 리포트
├── radar_2026-04-18_14-30-00.png            # 레이더 차트
├── histogram_2026-04-18_14-30-00.png        # 점수 분포 히스토그램
├── item_comparison_2026-04-18_14-30-00.png  # 항목별 비교 차트
└── evaluation_history.db                     # 평가 이력 DB
```

### 개별 리포트 예시

```markdown
# 지원서 평가 리포트

- **지원자**: 홍길동
- **평가 루브릭**: AX 교육과정 선발 평가
- **총점**: 34.5 / 50

## 항목별 평가

#### 지원동기 (8 / 10)

| 항목 | 내용 |
|---|---|
| **앵커 구간** | 7-8점 |
| **득점 근거** | "기관의 디지털 전환 로드맵에 AI 역량을 내재화하기 위해..." |
| **차감 사유** | 전파 계획의 실행 가능 수준 미흡 |
| **평가 기준 근거** | Noe & Wilk (1993) |
```

---

## 에러 대처법

### 1. `ANTHROPIC_API_KEY가 설정되지 않았습니다`

```bash
# .env 파일이 프로젝트 루트에 있는지 확인
cat .env
# ANTHROPIC_API_KEY=sk-ant-... 형식이어야 함
```

### 2. `Rate limit 도달` 반복

- `config.yaml`의 `api.max_concurrency`를 줄이세요 (예: 5 → 3)
- `api.rate_limit_max_retries`를 늘리세요
- API 플랜을 확인하세요 (무료 플랜은 분당 호출 제한이 낮음)

### 3. `루브릭 YAML 형식 오류`

- YAML 들여쓰기가 정확한지 확인 (스페이스 2칸)
- `scoring_anchors`의 키가 문자열인지 확인 (`"9-10"`: 따옴표 필수)
- `total_score`와 각 항목 `max_score` 합이 일치하는지 확인

### 4. `JSON 파싱 실패`

- 네트워크 불안정으로 응답이 잘린 경우 → 자동 1회 재시도
- 반복 발생 시 `logs/` 폴더의 로그에서 raw response 확인
- `api.max_tokens`를 늘려보세요

### 5. `파일 인코딩 에러`

- 지원서 파일을 UTF-8로 저장하세요
- 다른 인코딩(EUC-KR 등)도 자동 감지하지만 UTF-8 권장

---

## 프리셋 루브릭

| 파일 | 용도 | 총점 |
|---|---|---|
| `ax_training.yaml` | AI 전환 교육과정 선발 | 50점 |
| `job_hiring.yaml` | 일반 채용 자기소개서 | 100점 |
| `scholarship.yaml` | 장학금/학술 지원 | 100점 |
| `project_proposal.yaml` | 프로젝트/공모전 제안서 | 100점 |
| `essay.yaml` | 자유 에세이/동기 서술 (범용) | 100점 |

커스텀 루브릭 작성 시 기존 YAML 파일을 참고하세요.

---

## 라이선스

MIT License
