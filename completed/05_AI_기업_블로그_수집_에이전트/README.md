# AI 기업 블로그 수집 에이전트

## 프로젝트 소개

주요 AI 기업(OpenAI, Anthropic, Google DeepMind, Meta AI 등)의 RSS 피드를 매일 수집해 신규 글만 필터링하고, Claude API로 한국어 3줄 요약 및 키워드 추출 후 카테고리 분류하여 마크다운 파일로 저장하는 자동화 에이전트입니다. 수집 상태를 `state.json`에 영속화하여 중복 수집 없이 신규 글만 처리합니다.

---

## 주요 기능

- **RSS 피드 수집**: `feedparser` + `requests`로 13개 AI 기업 블로그 RSS 수집
- **신규 글 필터링**: `state.json`에 마지막 처리 항목 ID 저장, 중복 수집 방지
- **한국어 요약**: Claude API로 3줄 한국어 요약 생성
- **키워드 추출**: 각 글의 핵심 키워드 3개 추출
- **카테고리 분류**: 연구·기술 동향 / AI 인프라·플랫폼·도구 / AI·데이터 활용 사례 / 정책·거버넌스
- **마크다운 리포트**: `output/YYYY-MM-DD.md` 형식으로 저장
- **날짜별 로그**: `logs/YYYY-MM-DD.log` 기록
- **안전한 저장**: `state.json` 원자적 쓰기(temp 파일 → `os.replace`)로 손상 방지
- **동시 실행 방지**: `fcntl.flock`으로 cron 중복 실행 차단 (Unix/macOS 전용)
- **자동 재시도**: tenacity로 Claude API 일시 오류 자동 재시도

---

## 요구사항

- **Python >= 3.10** (`str | None`, `list[dict]` 등 타입 구문 사용)
- **ANTHROPIC_API_KEY**: Anthropic Console에서 발급

---

## 설치 방법

```bash
# 1. 저장소 클론
git clone https://github.com/your-repo/ai-blog-agent.git
cd ai-blog-agent

# 2. 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt
```

---

## 환경 설정

`.env.example`을 복사해 `.env` 파일을 만들고 API 키를 입력합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

**ANTHROPIC_API_KEY 발급**: [Anthropic Console](https://console.anthropic.com/) → API Keys → Create Key

---

## config.yaml 설정

| 섹션 | 필드 | 기본값 | 설명 |
|---|---|---|---|
| `agent` | `name` | `"AI 기업 블로그 수집 에이전트"` | 로그에 표시되는 에이전트 이름 |
| `agent` | `state_file` | `"state.json"` | 수집 상태 저장 파일 경로 |
| `agent` | `output_dir` | `"output"` | 리포트 저장 디렉토리 |
| `agent` | `log_dir` | `"logs"` | 로그 저장 디렉토리 |
| `agent` | `lock_file` | `"agent.lock"` | 동시 실행 방지용 잠금 파일 |
| `agent` | `user_agent` | (없음) | 커스텀 User-Agent. 미설정 시 기본값 사용 |
| `collection` | `request_timeout` | `15` | HTTP 요청 타임아웃 (초) |
| `collection` | `initial_max_entries` | `5` | 피드 첫 수집 시 최대 항목 수 |
| `collection` | `max_entries_per_run` | `20` | 이후 수집 시 피드당 최대 항목 수 |
| `collection` | `delay_between_feeds` | `1` | 피드 간 대기 시간 (초) |
| `collection` | `max_summary_chars` | `2000` | Claude에 전달할 원문 최대 글자 수 |
| `claude` | `model` | `"claude-opus-4-6"` | 사용할 Claude 모델 ID |
| `claude` | `max_tokens` | `1024` | Claude 응답 최대 토큰 수 |
| `claude` | `temperature` | `0.3` | Claude 응답 온도 (0.0~1.0) |
| `claude` | `delay_between_calls` | `1` | API 호출 간 대기 시간 (초) |
| `claude` | `retry_attempts` | `3` | API 호출 실패 시 재시도 횟수 |
| `claude` | `retry_wait_min` | `2` | 재시도 최소 대기 시간 (초) |
| `claude` | `retry_wait_max` | `10` | 재시도 최대 대기 시간 (초) |
| `report` | `group_by` | `"company"` | 리포트 그룹 기준: `"company"` 또는 `"category"` |
| `report` | `show_raw_summary` | `false` | 원문 요약 펼치기 섹션 표시 여부 |
| `report` | `categories` | (4개 기본 카테고리) | 분류 카테고리 목록 |
| `feeds` | `name` | 필수 | 피드 표시 이름 |
| `feeds` | `url` | 필수 | RSS 피드 URL |
| `feeds` | `enabled` | `true` | `false`로 설정 시 해당 피드 건너뜀 |

---

## 실행 방법

```bash
# 기본 실행
python main.py
```

실행 전 체크리스트:
1. `.env` 파일에 `ANTHROPIC_API_KEY` 설정 완료
2. `config.yaml`의 `feeds` 목록에서 수집할 피드 확인
3. Python 3.10 이상 환경에서 실행

> **참고**: 한국 기업 피드(NAVER AI, Kakao Brain, LG AI Research)는 RSS 제공 여부가 불확실합니다. 수동으로 URL 유효성을 확인하거나 `enabled: false`로 설정하세요.

---

## 출력 결과

### `output/YYYY-MM-DD.md` — 수집 리포트

`group_by: "company"` 모드:

```markdown
# AI 기업 블로그 수집 리포트
**수집일:** 2026-04-21  
**총 신규 글:** 7개  
**수집 기업:** Anthropic, OpenAI, Hugging Face

---

## Anthropic

### [Claude 3.7의 추론 능력 개선에 관하여](https://www.anthropic.com/blog/claude-37-reasoning)
- **발행일:** 2026-04-20
- **카테고리:** 연구·기술 동향
- **키워드:** `추론`, `Chain-of-Thought`, `벤치마크`

> 1. Anthropic은 Claude 3.7에 강화된 단계별 추론 기능을 도입했다고 발표했다.  
> 2. 수학·코딩 벤치마크에서 이전 대비 23% 향상된 성능을 기록했다.  
> 3. 해당 기능은 API를 통해 즉시 사용 가능하며, 추가 비용은 없다.

---

*생성 시각: 2026-04-21 09:03:22 UTC*
```

- 같은 날 재실행 시 `output/2026-04-21_2.md`처럼 숫자 접미사 추가
- `state.json`이 최신 ID를 기록하므로 중복 수집 없이 신규 글만 포함됨

### `logs/YYYY-MM-DD.log` — 실행 로그

```
2026-04-21 09:00:01 INFO     AI 기업 블로그 수집 에이전트 시작
2026-04-21 09:00:02 INFO     [OpenAI] 신규 2개, state 저장
2026-04-21 09:00:03 WARNING  [xAI] HTTP 오류: 403 Client Error: Forbidden. 건너뜀.
2026-04-21 09:00:04 INFO     [Anthropic] 신규 1개, state 저장
2026-04-21 09:00:10 INFO     Claude 요약 완료 - 1/3개
2026-04-21 09:00:11 INFO     Claude 요약 완료 - 2/3개
2026-04-21 09:00:12 INFO     Claude 요약 완료 - 3/3개
2026-04-21 09:00:12 INFO     리포트 저장: output/2026-04-21.md
2026-04-21 09:00:12 INFO     완료. 총 3개 신규 글 처리.
```

### `state.json` — 수집 상태

```json
{
  "https://openai.com/blog/rss.xml": "https://openai.com/blog/gpt5-api",
  "https://www.anthropic.com/rss.xml": "tag:anthropic.com,2026:claude-37-reasoning"
}
```

---

## 에러 대처법

### 1. `ERROR: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.`

`.env` 파일이 없거나 키가 비어있는 경우입니다.

```bash
cp .env.example .env
# .env 파일을 열어 실제 API 키 입력
```

### 2. `[피드명] HTTP 오류: 403 Client Error: Forbidden. 건너뜀.`

해당 피드가 봇 접근을 차단한 경우입니다. `config.yaml`의 `agent.user_agent`를 실제 식별 가능한 URL로 설정하거나, 해당 피드를 `enabled: false`로 비활성화하세요.

```yaml
agent:
  user_agent: "Mozilla/5.0 (compatible; my-blog-agent/1.0; +https://github.com/myuser/my-blog-agent)"
```

### 3. `ERROR: 이미 실행 중인 인스턴스가 있습니다 (agent.lock). 종료합니다.`

이전 실행이 비정상 종료되어 잠금 파일이 남아있는 경우입니다.

```bash
# 실행 중인 프로세스가 없다면 잠금 파일 삭제
rm agent.lock
python main.py
```

### 4. `Claude 응답 JSON 파싱 실패. 폴백값 사용.` (WARNING)

Claude가 JSON 형식을 지키지 않은 경우입니다. 해당 항목은 `category: "미분류"`로 처리됩니다. 반복 발생 시 `config.yaml`의 `claude.max_tokens`를 늘려보세요.

### 5. state.json이 손상된 경우

```bash
# state.json 삭제 후 재실행 (모든 피드를 처음부터 수집)
rm state.json
python main.py
```

특정 피드만 재수집하려면 `state.json`에서 해당 피드 URL 키를 삭제하고 재실행하세요.

---

## 라이선스

MIT License
