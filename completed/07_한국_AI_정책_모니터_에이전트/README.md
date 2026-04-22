# 한국 AI 정책 모니터 에이전트

국내외 AI 정책·규제 뉴스를 RSS 피드와 HTML 크롤링으로 자동 수집하고, Claude API를 통해 한국어 3줄 요약과 정책 영향도 태그를 생성하여 Markdown 보고서로 저장하는 에이전트입니다. 매일 실행하면 `output/YYYY-MM-DD.md` 파일에 당일 수집된 AI 정책 뉴스 요약이 자동으로 생성됩니다.

---

## 주요 기능

- RSS 피드 및 HTML 게시판에서 AI 정책·규제 뉴스 자동 수집
- 소스별 키워드 필터링으로 관련성 높은 기사만 선별
- Claude API를 이용한 한국어 3줄 요약 자동 생성
- 국내/글로벌/규제/지원/가이드라인/연구 태그 자동 분류
- 중복 수집 방지 (`state.json` 기반 SHA256 해시 추적)
- 동시 실행 방지 (`fcntl` 기반 락 파일)
- 원자적 파일 쓰기 및 `.bak.md` 백업으로 데이터 손실 방지
- 날짜별 로그 파일 자동 생성 (`logs/YYYY-MM-DD.log`)
- HTTP 요청 재시도 및 Claude API 재시도 로직 내장

---

## 요구사항

- **OS**: macOS 또는 Linux (**Windows 미지원** — 동시 실행 방지에 `fcntl` 모듈(Unix 전용)을 사용합니다)
- **Python**: 3.10 이상
- **API 키**: Anthropic API 키 (`ANTHROPIC_API_KEY`)

---

## 설치 방법

```bash
# 1. 프로젝트 디렉토리로 이동
cd 07_한국_AI_정책_모니터_에이전트

# 2. 가상환경 생성
python3 -m venv .venv

# 3. 가상환경 활성화
source .venv/bin/activate

# 4. 의존성 설치
pip install -r requirements.txt
```

> **lxml 설치 실패 시 (ARM Mac / Alpine Linux):**
>
> ```bash
> # 방법 1: install.sh 사용
> bash install.sh
>
> # 방법 2: html.parser로 대체
> # config.yaml의 http.bs_parser를 "html.parser"로 변경 후
> # requirements.txt에서 lxml 줄 삭제하고 재설치
> pip install -r requirements.txt
> ```

---

## 환경 설정

`.env.example`을 복사하여 `.env` 파일을 생성하고 Anthropic API 키를 입력합니다.

```bash
cp .env.example .env
```

`.env` 파일 내용을 편집합니다:

```dotenv
ANTHROPIC_API_KEY=sk-ant-여기에_실제_API_키_입력
```

- **Anthropic API 키 발급**: [https://console.anthropic.com/](https://console.anthropic.com/) 에서 계정 생성 후 **API Keys** 메뉴에서 발급
- API 키는 `.gitignore`에 포함된 `.env` 파일에만 저장하고 절대 커밋하지 마세요.

---

## config.yaml 설정

### agent 섹션

| 키 | 기본값 | 설명 |
|---|---|---|
| `name` | `"한국 AI 정책 모니터"` | 에이전트 이름 (표시용) |
| `max_articles_per_run` | `50` | 1회 실행당 최대 처리 기사 수 |
| `max_articles_per_source` | `20` | 소스당 최대 수집 기사 수 |
| `request_delay_seconds` | `1.0` | 소스 간 HTTP 요청 딜레이(초) |
| `region_tie_break` | `"국내"` | 지역 태그 충돌 시 우선순위 (`"국내"` 또는 `"글로벌"`) |

### http 섹션

| 키 | 기본값 | 설명 |
|---|---|---|
| `timeout_seconds` | `15` | HTTP 요청 타임아웃(초) |
| `retry_count` | `3` | HTTP 요청 실패 시 재시도 횟수 |
| `retry_delay_seconds` | `2.0` | HTTP 재시도 대기 시간(초) |
| `user_agent` | `"Mozilla/5.0 ..."` | HTTP 요청 User-Agent |
| `bs_parser` | `"lxml"` | BeautifulSoup 파서 (`"lxml"` 또는 `"html.parser"`) |

### claude 섹션

| 키 | 기본값 | 설명 |
|---|---|---|
| `model` | `"claude-opus-4-6"` | 사용할 Claude 모델 ID |
| `max_tokens` | `512` | Claude 응답 최대 토큰 수 |
| `temperature` | `0.3` | Claude 응답 온도 (0.0~1.0, 낮을수록 일관된 출력) |
| `retry_count` | `3` | Claude API 실패 시 재시도 횟수 |
| `retry_delay_seconds` | `5.0` | Claude API 재시도 대기 시간(초) |
| `call_delay_seconds` | `1.0` | 기사 간 Claude API 호출 딜레이(초) |
| `raw_text_max_chars` | `1000` | Claude에 전달할 기사 본문 최대 글자 수 |

### state 섹션

| 키 | 기본값 | 설명 |
|---|---|---|
| `path` | `"state.json"` | 수집 이력 저장 파일 경로 |
| `max_hashes_per_source` | `500` | 소스당 최대 저장 해시 수 (초과 시 오래된 것부터 삭제) |

### output 섹션

| 키 | 기본값 | 설명 |
|---|---|---|
| `dir` | `"output"` | 보고서 출력 디렉토리 |
| `log_dir` | `"logs"` | 로그 파일 저장 디렉토리 |

### logging 섹션

| 키 | 기본값 | 허용값 | 설명 |
|---|---|---|---|
| `level` | `"INFO"` | `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"` | 로그 레벨 |

### sources 섹션

**RSS 소스 예시:**

```yaml
sources:
  - id: "unique_id"           # 고유 식별자 (영문, 변경 시 state.json 이력 초기화됨)
    name: "소스 이름"           # 보고서에 표시될 소스 이름
    type: "rss"                # 소스 타입
    enabled: true              # 활성화 여부 (기본값: true, false로 비활성화)
    url: "https://..."         # RSS 피드 URL
    filter_keywords:           # 제목에 포함될 키워드 목록 (비어있으면 전체 수집)
      - "AI"
      - "정책"
```

**HTML 게시판 소스 예시:**

```yaml
  - id: "unique_id"
    name: "소스 이름"
    type: "html"
    url: "https://..."         # 목록 페이지 URL
    link_base: "https://..."   # 상대 URL 변환 기준 도메인 (예: "https://www.example.go.kr")
    selectors:
      list: "table tbody tr"   # 기사 행 목록 CSS 선택자
      title: "td.tit a"        # 제목 CSS 선택자
      link: "td.tit a"         # 링크(href) CSS 선택자
      date: "td.date"          # 날짜 CSS 선택자 (선택사항, 없으면 현재 날짜 사용)
    filter_keywords:
      - "AI"
      - "인공지능"
```

---

## 실행 방법

```bash
# 가상환경 활성화 후 실행
source .venv/bin/activate
python main.py
```

실행 중 콘솔에 진행 상황이 출력됩니다:

```
2026-04-21 09:00:01 INFO 과학기술정보통신부 보도자료에서 수집 시작
2026-04-21 09:00:03 INFO 개인정보보호위원회 보도자료에서 수집 시작
2026-04-21 09:00:05 INFO AI타임스에서 수집 시작
2026-04-21 09:00:07 INFO Future of Life Institute에서 수집 시작
2026-04-21 09:00:09 INFO Stanford HAI에서 수집 시작
2026-04-21 09:00:20 INFO 보고서 생성 완료: .../output/2026-04-21.md
2026-04-21 09:00:20 INFO 처리 완료: 8개 글, output/2026-04-21.md 저장
```

---

## 출력 결과

실행 후 다음 파일이 생성됩니다:

| 파일 | 설명 |
|---|---|
| `output/YYYY-MM-DD.md` | 당일 AI 정책 뉴스 요약 보고서 |
| `output/YYYY-MM-DD.bak.md` | 동일 날짜 재실행 시 이전 보고서 백업 |
| `logs/YYYY-MM-DD.log` | 실행 로그 |
| `state.json` | 수집 이력 (중복 방지용, 소스별 해시 목록) |

### 보고서 예시 (`output/2026-04-21.md`)

```markdown
# AI 정책 모니터 — 2026-04-21

> 수집 출처 4개 | 신규 글 8건 | 생성 시각: 2026-04-21 09:00:20 KST

---

## 국내

### 1. [과학기술정보통신부 보도자료] 인공지능 기본법 시행령 입법예고

- **링크**: https://www.msit.go.kr/...
- **발행일**: 2026-04-20
- **태그**: `국내` `규제`

> 1. 과기정통부가 인공지능 기본법 시행령 초안을 입법예고하며 30일간 의견수렴을 시작했다.
> 2. 시행령은 고위험 AI 시스템의 사전 신고 의무와 적합성 평가 절차를 구체적으로 규정한다.
> 3. 중소기업 부담 완화를 위해 매출 기준 적용 유예 조항이 포함되었다.

---

## 글로벌

### 5. [Stanford HAI] Governing Foundation Models: New Framework Proposal

- **링크**: https://hai.stanford.edu/news/...
- **발행일**: 2026-04-19
- **태그**: `글로벌` `가이드라인` `연구`

> 1. 스탠퍼드 HAI가 기반 모델 전용 거버넌스 프레임워크 초안을 발표했다.
> 2. 개발사의 사전 위험 평가 의무화와 제3자 감사 제도 도입을 핵심 제안으로 담고 있다.
> 3. 미국 NIST AI RMF와 EU AI Act 간 상호 인정 체계 구축을 촉구했다.

---

## 미분류

*(지역 태그 미확인 글 없음)*

---

*AI 정책 모니터 에이전트 자동 생성 | claude-opus-4-6*
```

---

## 동작 참고사항

- `config.yaml`의 `filter_keywords`를 변경해도 이미 수집된(seen 처리된) 기사는 재수집되지 않습니다. 모든 기사를 새로 수집하려면 `state.json`을 삭제하세요.
- 동일 날짜에 재실행하면 기존 보고서는 `.bak.md`로 백업된 후 새 보고서로 덮어씌워집니다.
- 기사는 소스 간 라운드로빈 방식으로 병합되므로, `max_articles_per_run` 한도에 걸릴 경우 각 소스에서 균등하게 선택됩니다.

---

## 에러 대처법

### 1. `ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.`

`.env` 파일이 없거나 API 키가 비어있는 경우입니다.

```bash
cp .env.example .env
# .env 파일을 열어 실제 API 키 입력
```

### 2. `lxml` 설치 실패 (ARM Mac / Alpine Linux)

빌드 도구가 없거나 아키텍처 미지원 바이너리 문제입니다.

```bash
# 방법 1: install.sh 사용 (자동으로 html.parser 대체 처리)
bash install.sh

# 방법 2: 수동으로 html.parser로 대체
# 1) config.yaml에서 http.bs_parser를 "html.parser"로 변경
# 2) requirements.txt에서 "lxml==5.2.2" 줄 삭제
# 3) 재설치
pip install -r requirements.txt
```

### 3. `HTTP 403 Forbidden` 오류

일부 사이트가 봇 접근을 차단한 경우입니다.

- `config.yaml`의 `http.user_agent`를 실제 브라우저 User-Agent로 변경하거나
- 해당 소스에 `enabled: false`를 추가하여 비활성화합니다.

### 4. `다른 에이전트 인스턴스가 실행 중입니다.`

이전 실행이 비정상 종료되어 `.agent.lock` 파일이 남은 경우입니다.

```bash
rm .agent.lock
python main.py
```

### 5. `state.json 파싱 실패, 빈 상태로 초기화`

`state.json`이 손상된 경우 자동으로 빈 상태로 초기화됩니다. 모든 기사가 새로 수집되므로 Claude API 호출 비용이 증가할 수 있습니다.

### 6. `API 인증 실패` 또는 `API 권한 없음`

API 키가 유효하지 않거나 만료된 경우입니다. [https://console.anthropic.com/](https://console.anthropic.com/) 에서 새 API 키를 발급받아 `.env` 파일을 업데이트합니다.

### 7. `새로운 글이 없습니다.` (기사가 수집되지 않는 경우)

- `filter_keywords`가 너무 엄격한 경우: 키워드를 줄이거나 빈 리스트(`[]`)로 변경
- 소스 URL이 변경된 경우: 해당 사이트에서 최신 URL 확인 후 `config.yaml` 업데이트
- `state.json`에 이미 모든 기사가 seen 처리된 경우: `state.json` 삭제 후 재실행

---

## 라이선스

MIT License
