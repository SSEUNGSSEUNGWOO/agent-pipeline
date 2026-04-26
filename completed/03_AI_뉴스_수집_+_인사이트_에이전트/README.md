# AI 뉴스 수집 + 인사이트 에이전트

## 프로젝트 소개

RSS 피드에서 AI 관련 뉴스를 매일 자동으로 수집하고, Claude API를 활용해 핵심 인사이트를 추출한 뒤 마크다운 리포트로 저장하는 에이전트입니다. TechCrunch, MIT Technology Review, The Verge 등 주요 AI 뉴스 소스를 지원하며, 중복 기사 필터링과 카테고리 분류 기능을 내장하고 있습니다.

---

## 주요 기능

- **다중 RSS 피드 수집**: 여러 AI 뉴스 소스를 동시에 수집하며, 실패한 피드는 자동으로 재시도
- **중복 기사 필터링**: MD5 해시 기반 ID로 이미 수집된 기사를 제외
- **카테고리 자동 분류**: 키워드 매칭을 통해 기사를 모델 출시 / 투자 / 정책 / 연구 등으로 분류
- **Claude API 인사이트 추출**: 수집된 기사를 분석해 핵심 인사이트를 JSON 형식으로 추출
- **마크다운 리포트 생성**: 인사이트, 카테고리 분포, 기사 목록을 포함한 구조화된 리포트 저장
- **자동 재시도**: tenacity를 이용한 네트워크 오류 및 API Rate Limit 대응
- **날짜별 로그**: 실행 이력을 날짜별 로그 파일로 저장, 오래된 로그 자동 삭제
- **상태 관리**: state.json으로 수집 이력 관리, 90일 기준 자동 pruning

---

## 요구사항

- **Python**: 3.9 이상 (필수)
- **API 키**:
  - `ANTHROPIC_API_KEY`: Claude API 키 (필수)

---

## 설치 방법

```bash
# 1. 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 패키지 설치 (개발 모드)
pip install -e .

# 또는 requirements.txt로 설치
pip install -r requirements.txt
```

---

## 환경 설정

`.env.example`을 복사해 `.env` 파일을 생성하고 API 키를 입력합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용:

```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxx
```

- **ANTHROPIC_API_KEY**: [Anthropic Console](https://console.anthropic.com/)에서 발급

---

## config.yaml 설정

| 섹션 | 키 | 기본값 | 설명 |
|------|-----|--------|------|
| `agent` | `name` | `"AI 뉴스 인사이트 에이전트"` | 리포트 제목에 표시될 에이전트 이름 |
| `agent` | `lookback_days` | `1` | 수집할 기사의 최대 발행 기간 (일) |
| `agent` | `max_articles_per_feed` | `20` | 피드당 최대 수집 기사 수 |
| `agent` | `max_total_articles` | `50` | 리포트에 표시할 최대 기사 수 |
| `feeds` | `timeout` | `10` | HTTP 요청 타임아웃 (초) |
| `feeds` | `user_agent` | `"Mozilla/5.0 ..."` | HTTP 요청 시 사용할 User-Agent |
| `feeds` | `sources` | (3개 기본 피드) | RSS 피드 목록. `name`, `url`, `enabled` 필드 |
| `claude` | `model` | `"claude-sonnet-4-6"` | 사용할 Claude 모델 ID |
| `claude` | `max_tokens` | `1500` | 응답 최대 토큰 수 |
| `claude` | `temperature` | `0.3` | 응답 다양성 (0.0~1.0) |
| `claude` | `insight_count` | `3` | 추출할 인사이트 개수 |
| `claude` | `prompt_summary_max_chars` | `300` | 프롬프트에 포함할 기사 요약 최대 글자 수 |
| `claude` | `prompt_template` | (내장 템플릿) | Claude에 전달할 프롬프트 템플릿 |
| `retry` | `attempts` | `3` | 최대 재시도 횟수 |
| `retry` | `wait_min` | `2` | 재시도 최소 대기 시간 (초) |
| `retry` | `wait_max` | `10` | 재시도 최대 대기 시간 (초) |
| `retry` | `rate_limit_wait` | `60` | Rate Limit 발생 시 대기 시간 (초) |
| `categories` | `default_name` | `"기타"` | 미분류 기사의 카테고리명 |
| `categories` | `items` | (4개 기본 카테고리) | 카테고리 목록. `name`, `keywords` 필드 |
| `output` | `dir` | `"output"` | 리포트 저장 디렉토리 |
| `output` | `encoding` | `"utf-8"` | 리포트 파일 인코딩 |
| `logging` | `dir` | `"logs"` | 로그 파일 저장 디렉토리 |
| `logging` | `level` | `"INFO"` | 로그 레벨 (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `logging` | `retention_days` | `30` | 로그 파일 보관 기간 (일) |
| `state` | `path` | `"state.json"` | 수집 이력 파일 경로 |
| `state` | `retention_days` | `90` | 수집 이력 보관 기간 (일) |

---

## 실행 방법

```bash
python main.py
```

매일 자동 실행하려면 cron을 설정합니다:

```bash
# crontab -e
# 매일 오전 9시에 실행 (동시 실행 방지를 위해 flock 사용 권장)
0 9 * * * cd /path/to/ai-news-agent && flock -n /tmp/ai-news-agent.lock .venv/bin/python main.py
```

> **주의**: 동시 실행 시 `state.json`에 경쟁 조건이 발생할 수 있습니다. 크론 설정 시 `flock` 등 OS 수준 잠금 사용을 권장합니다.

---

## 출력 결과

실행 완료 후 `output/` 폴더에 `YYYY-MM-DD.md` 형식의 마크다운 리포트가 생성됩니다.

```
output/
└── 2026-04-09.md
```

**리포트 내용 예시:**

```markdown
# AI 뉴스 인사이트 에이전트
**날짜:** 2026-04-09
**수집 피드:** 3/3개 | **수집 기사:** 42개 | **신규 기사:** 18개

---

## 오늘의 핵심 인사이트

1. **오픈AI의 GPT-5 출시가 임박했다는 신호가 여러 경로에서 동시에 포착됨.**
2. **EU AI Act 시행을 앞두고 빅테크의 로비 활동이 본격화.**
3. **멀티모달 AI 연구에서 영상 이해 능력이 급격히 발전.**

---

## 카테고리별 분포

| 카테고리 | 기사 수 |
|---------|--------|
| 모델 출시 | 7 |
| 투자 | 5 |
| 정책 | 4 |
| 연구 | 6 |
| 기타 | 5 |

---

## 수집 기사 목록

### 모델 출시

#### GPT-5 출시 임박, 내부 문서에서 확인
- **출처:** TechCrunch AI
- **발행:** 2026-04-09 09:32 UTC
- **요약:** 오픈AI 내부 문서에 따르면...
- **링크:** https://techcrunch.com/...

*생성 시각: 2026-04-09 00:23:05 UTC | 모델: claude-sonnet-4-6*
```

---

## 에러 대처법

### 1. `ANTHROPIC_API_KEY가 설정되지 않았습니다.`

**원인**: `.env` 파일이 없거나 API 키가 설정되지 않음

**해결**:
```bash
cp .env.example .env
# .env 파일에 실제 API 키 입력
echo "ANTHROPIC_API_KEY=sk-ant-xxxxxxxx" >> .env
```

### 2. `피드 수집 실패 (재시도 소진): TechCrunch AI`

**원인**: 네트워크 오류, 피드 서버 응답 없음, User-Agent 차단

**해결**:
- 네트워크 연결 확인
- `config.yaml`의 `feeds.user_agent` 값을 변경
- 해당 피드의 `enabled: false`로 임시 비활성화

### 3. `Claude 응답 파싱 실패`

**원인**: Claude 응답이 JSON 형식이 아님 (프롬프트 오염 등)

**해결**:
- `config.yaml`의 `claude.prompt_template` 확인
- `claude.temperature` 값을 낮춤 (예: `0.1`)
- `logs/YYYY-MM-DD.log` 파일에서 실제 응답 내용 확인

### 4. `config.yaml에 필수 키가 없습니다.`

**원인**: config.yaml 누락 또는 필수 섹션/키 누락

**해결**:
- 현재 디렉토리에 `config.yaml`이 있는지 확인
- 예시 설정과 비교해 누락된 키 추가

### 5. `state.json 저장 실패`

**원인**: 디스크 용량 부족 또는 권한 없음

**해결**:
- 디스크 용량 확인: `df -h`
- `state.json` 경로의 쓰기 권한 확인

---

## 라이선스

MIT License
