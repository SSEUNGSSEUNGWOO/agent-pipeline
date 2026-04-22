# 한국 AI 정책 모니터 에이전트

국내외 AI 정책·규제 뉴스를 RSS/HTML 크롤링으로 매일 수집하고, Claude API로 한국어 3줄 요약과 정책 영향도 태그를 자동 추출하여 Markdown 리포트로 저장하는 에이전트입니다. 매일 `python main.py`를 실행하면 당일 신규 기사를 수집·분석·보고서 생성까지 자동으로 처리합니다.

---

## 주요 기능

- **다중 소스 수집**: RSS 피드 + HTML 크롤링 동시 지원 (과기정통부, 개인정보보호위원회, AI타임스, Future of Life Institute, Stanford HAI 등)
- **키워드 필터링**: 소스별 `filter_keywords` 설정으로 관련 기사만 선별
- **중복 방지**: SHA256 해시 기반 상태 관리로 이미 수집한 기사 자동 스킵
- **Claude AI 요약**: 기사당 3줄 한국어 요약 + 지역/카테고리 태그 자동 추출
- **Markdown 리포트**: 국내/글로벌/미분류 섹션으로 구분된 일일 보고서 생성
- **크래시 복구**: 수집 후 요약 전 비정상 종료 시 다음 실행에서 자동 롤백·재수집
- **동시 실행 방지**: `fcntl` 기반 파일 잠금으로 중복 실행 차단
- **라운드로빈 병합**: 소스 간 균형 잡힌 기사 선택 (`max_articles_per_run` 적용)
- **원자적 파일 쓰기**: `os.replace()`를 사용하여 보고서·상태 파일 손상 방지

---

## 요구사항

| 항목 | 조건 |
|---|---|
| **OS** | macOS 또는 Linux (Windows 미지원 — `fcntl` 모듈이 Unix 전용) |
| **Python** | 3.10 이상 |
| **API 키** | Anthropic API 키 (`ANTHROPIC_API_KEY`) |

---

## 설치 방법

```bash
# 1. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력
```

### lxml 설치 실패 시 (ARM, Alpine 등)

```bash
bash install.sh
```

실행 후 `config.yaml`의 `http.bs_parser`를 `"html.parser"`로 변경하세요.

---

## 환경 설정

### `.env` 파일 작성법

```dotenv
ANTHROPIC_API_KEY=sk-ant-api03-...
```

| 키 | 설명 | 발급처 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude API 키 | [Anthropic Console](https://console.anthropic.com/) → API Keys |

---

## config.yaml 설정

### `agent` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `name` | `"한국 AI 정책 모니터"` | 에이전트 이름 (로깅용) |
| `max_articles_per_run` | `50` | 1회 실행당 최대 처리 기사 수. 초과분은 다음 실행에서 재수집 |
| `max_articles_per_source` | `20` | 소스당 최대 수집 기사 수 |
| `request_delay_seconds` | `1.0` | 소스 간 HTTP 요청 간격 (초) |
| `region_tie_break` | `"국내"` | 지역 태그 충돌 시 우선 선택값. `"국내"` 또는 `"글로벌"` |

### `http` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `timeout_seconds` | `15` | HTTP 요청 타임아웃 (초) |
| `retry_count` | `3` | HTTP 요청 실패 시 재시도 횟수 |
| `retry_delay_seconds` | `2.0` | 재시도 간 대기 시간 (초) |
| `user_agent` | `"Mozilla/5.0 (compatible; AI-Policy-Monitor/1.0)"` | HTTP User-Agent 헤더 |
| `bs_parser` | `"lxml"` | BeautifulSoup 파서. lxml 사용 불가 시 `"html.parser"` |

### `claude` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `model` | `"claude-sonnet-4-6"` | Claude 모델 ID. 비용 절감형 기본값. `"claude-opus-4-6"`으로 변경 가능 |
| `max_tokens` | `512` | 응답 최대 토큰 수 |
| `temperature` | `0.3` | 생성 온도 (0.0~1.0) |
| `retry_count` | `3` | API 호출 실패 시 재시도 횟수 |
| `retry_delay_seconds` | `5.0` | API 재시도 간 대기 시간 (초) |
| `call_delay_seconds` | `1.0` | 기사 간 API 호출 간격 (초). Rate Limit 방지 |
| `raw_text_max_chars` | `1000` | Claude에 전달할 기사 본문 최대 글자 수 |

### `state` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `path` | `"state.json"` | 상태 파일 경로 |
| `max_hashes_per_source` | `500` | 소스당 보관할 최대 해시 수. 초과 시 오래된 것부터 삭제 |

### `output` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `dir` | `"output"` | 보고서 출력 디렉토리 |
| `log_dir` | `"logs"` | 로그 파일 디렉토리 |
| `show_untagged_section` | `true` | 미분류 기사 없을 때 `## 미분류` 섹션 표시 여부 |
| `backup_retention_days` | `7` | `.bak.md` 백업 파일 보존 기간 (일). 초과 시 기동 시 자동 삭제 |

### `logging` 섹션

| 필드 | 기본값 | 설명 |
|---|---|---|
| `level` | `"INFO"` | 로그 레벨. `DEBUG`, `INFO`, `WARNING`, `ERROR` 중 선택 |

### `sources` 섹션

각 소스는 다음 필드를 포함합니다:

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | O | 소스 고유 ID (state.json 키로 사용) |
| `name` | O | 소스 표시 이름 |
| `type` | O | `"rss"` 또는 `"html"` |
| `url` | O | 수집 대상 URL |
| `enabled` | X | `false`로 설정 시 비활성화. 기본값 `true` |
| `link_base` | HTML 필수 | 상대 URL을 절대 URL로 변환할 기준 도메인 |
| `selectors` | HTML 필수 | CSS 선택자 (`list`, `title`, `link`, `date`) |
| `filter_keywords` | X | 제목 필터링 키워드 목록. 빈 배열이면 전체 수집 |

---

## 실행 방법

```bash
python main.py
```

cron으로 매일 자동 실행:

```bash
# 매일 오전 9시 실행 (crontab -e)
0 9 * * * cd /path/to/07_한국_AI_정책_모니터_에이전트 && /path/to/venv/bin/python main.py
```

---

## 출력 결과

### 파일 구조

```
output/
└── 2026-04-22.md     # 당일 보고서

logs/
└── 2026-04-22.log    # 당일 로그

state.json            # 수집 상태 (중복 방지용)
```

### 보고서 예시 (`output/2026-04-22.md`)

```markdown
# AI 정책 모니터 — 2026-04-22

> 수집 출처 4개 | 신규 글 8건 | 생성 시각: 2026-04-22 09:14:32 KST

---

## 국내

### 1. [과학기술정보통신부 보도자료] 인공지능 기본법 시행령 입법예고

- **링크**: https://www.msit.go.kr/...
- **발행일**: 2026-04-21
- **태그**: `국내` `규제`

> 1. 과기정통부가 인공지능 기본법 시행령 초안을 입법예고하며 30일간 의견수렴을 시작했다.
> 2. 시행령은 고위험 AI 시스템의 사전 신고 의무와 적합성 평가 절차를 구체적으로 규정한다.
> 3. 중소기업 부담 완화를 위해 매출 기준 적용 유예 조항이 포함되었다.

---

## 글로벌

### 5. [Stanford HAI] Governing Foundation Models: New Framework Proposal

- **링크**: https://hai.stanford.edu/news/...
- **발행일**: 2026-04-20
- **태그**: `글로벌` `가이드라인` `연구`

> 1. 스탠퍼드 HAI가 기반 모델 전용 거버넌스 프레임워크 초안을 발표했다.
> 2. 개발사의 사전 위험 평가 의무화와 제3자 감사 제도 도입을 핵심 제안으로 담고 있다.
> 3. 미국 NIST AI RMF와 EU AI Act 간 상호 인정 체계 구축을 촉구했다.

---

*AI 정책 모니터 에이전트 자동 생성 | claude-sonnet-4-6*
```

---

## 비용 관련

- 기본 모델은 `claude-sonnet-4-6`으로 설정되어 있습니다.
- 뉴스 요약 + 태그 추출 작업에 충분한 품질을 제공합니다.
- 더 높은 품질이 필요하면 `config.yaml`의 `claude.model`을 `claude-opus-4-6`으로 변경할 수 있으나, **비용이 크게 증가**합니다.
- `max_articles_per_run: 50` 기준 일일 비용을 추정한 후 조정하세요.

---

## 동작 참고사항

- `config.yaml`의 `filter_keywords`를 변경해도 이미 수집된(seen 처리된) 기사는 재수집되지 않습니다. `state.json`을 삭제하면 모든 기사가 새로 수집됩니다.
- 총 수집 기사 수가 `max_articles_per_run`을 초과하면 초과분은 다음 실행에서 자동으로 재수집됩니다.
- 수집 완료 후 요약/보고서 생성 전 비정상 종료가 발생하면, 다음 실행 시 자동으로 해당 기사의 seen 상태를 롤백하여 재수집합니다.
- `output.show_untagged_section: false`로 설정하면 미분류 기사가 없을 때 보고서의 `## 미분류` 섹션이 생략됩니다.
- `.bak.md` 백업 파일은 `output.backup_retention_days`(기본 7일) 경과 후 기동 시 자동 삭제됩니다.

### RSS 소스 link_base 관련

- RSS 피드의 `entry.link`는 일반적으로 절대 URL이므로 `link_base` 설정이 필요 없습니다.
- 상대 URL을 반환하는 비정상 피드를 추가할 경우에만 해당 소스에 `link_base`를 설정하세요.

---

## 에러 대처법

### 1. `ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.`

**원인**: `.env` 파일이 없거나 `ANTHROPIC_API_KEY`가 비어 있음

**해결**:
```bash
cp .env.example .env
# .env 파일에 실제 API 키 입력
```

### 2. `다른 에이전트 인스턴스가 실행 중입니다. 종료합니다.`

**원인**: 이전 실행이 비정상 종료되어 `.agent.lock` 파일이 남아 있음

**해결**:
```bash
# 실제로 다른 프로세스가 실행 중인지 확인
ps aux | grep main.py

# 실행 중인 프로세스가 없다면 락 파일 삭제
rm .agent.lock
```

### 3. `config.yaml 필수 키 누락: claude.model`

**원인**: `config.yaml` 파일이 없거나 필수 설정이 빠져 있음

**해결**: `config.yaml`이 존재하는지 확인하고, 모든 필수 섹션(`agent`, `http`, `claude`, `state`, `output`, `logging`, `sources`)이 포함되어 있는지 점검

### 4. `HTTP 403 Forbidden` 반복 발생

**원인**: 대상 사이트가 봇 접근을 차단

**해결**:
- `config.yaml`의 `http.user_agent`를 일반 브라우저 User-Agent로 변경
- 해당 소스에 `enabled: false` 추가하여 비활성화

### 5. `API 인증 실패. 종료합니다.`

**원인**: `ANTHROPIC_API_KEY`가 유효하지 않음

**해결**:
- [Anthropic Console](https://console.anthropic.com/)에서 API 키 상태 확인
- 만료된 키라면 새 키 발급 후 `.env` 갱신

### 6. `lxml` 설치 실패

**원인**: C 컴파일러 또는 libxml2/libxslt 개발 헤더 미설치

**해결**:
```bash
# macOS
brew install libxml2 libxslt

# Ubuntu/Debian
sudo apt-get install libxml2-dev libxslt-dev

# 또는 lxml 없이 사용
bash install.sh
# config.yaml의 http.bs_parser를 "html.parser"로 변경
```

---

## 프로젝트 구조

```
07_한국_AI_정책_모니터_에이전트/
├── main.py              # 에이전트 진입점. 파이프라인 오케스트레이션
├── config.yaml          # 전체 설정 파일
├── .env                 # API 키 (git 추적 제외)
├── .env.example         # 환경 변수 템플릿
├── requirements.txt     # Python 의존성
├── install.sh           # lxml 대체 설치 스크립트
├── README.md            # 이 문서
├── state.json           # 수집 상태 (자동 생성)
├── .agent.lock          # 동시 실행 방지 (자동 생성)
├── agent/
│   ├── __init__.py      # 패키지 인식용 빈 파일
│   ├── utils.py         # KST 타임존, compute_hash
│   ├── state_manager.py # state.json 읽기/쓰기/롤백
│   ├── collector.py     # RSS/HTML 수집, 필터링, 라운드로빈 병합
│   ├── summarizer.py    # Claude API 호출, 요약·태그 추출
│   └── reporter.py      # Markdown 보고서 생성
├── output/              # 일일 보고서 (자동 생성)
│   └── YYYY-MM-DD.md
└── logs/                # 일일 로그 (자동 생성)
    └── YYYY-MM-DD.log
```

---

## 라이선스

MIT License
