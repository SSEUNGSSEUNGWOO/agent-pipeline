# arXiv 논문 요약 에이전트

arXiv API로 AI/ML 최신 논문을 자동 수집하고, Claude API를 활용해 한국어 3줄 요약을 생성한 뒤 날짜별 Markdown 파일로 저장하는 에이전트입니다. 매일 자동 실행(cron/launchd)으로 논문 트렌드를 손쉽게 추적할 수 있습니다.

---

## 주요 기능

- arXiv Atom feed에서 키워드 기반 논문 자동 수집
- Lucene 쿼리 인용부호 래핑으로 공백 포함 키워드도 정확하게 검색
- Claude API를 통한 한국어 3줄 요약 자동 생성
- output/YYYY-MM-DD.md 형식으로 날짜별 Markdown 파일 저장
- tenacity 기반 재시도 로직 (네트워크 오류, API Rate Limit 등)
- loguru 기반 날짜별 로그 파일 자동 관리
- 컨텍스트 초과 시 초록 자동 truncate 후 재시도
- cron / launchd를 통한 매일 자동 실행 지원

---

## 요구사항

- Python 3.10 이상
- Anthropic API 키 (ANTHROPIC_API_KEY)

---

## 설치 방법

```bash
cd 01_arXiv_논문_요약_에이전트
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 환경 설정

.env.example 복사: cp .env.example .env

.env 파일에 API 키 입력:

```
ANTHROPIC_API_KEY=sk-ant-...
```

API 키 발급: https://console.anthropic.com/settings/keys

---

## config.yaml 설정

| 필드 | 설명 | 기본값 |
|---|---|---|
| search.keywords | 검색 키워드 목록 | [LLM, multi-agent, ...] |
| search.search_fields | 검색 대상 필드 (ti: 제목, abs: 초록, au: 저자, cat: 카테고리) | [ti, abs] |
| search.max_results | 최대 수집 논문 수 | 10 |
| search.sort_by | 정렬 기준 (submittedDate, relevance, lastUpdatedDate) | submittedDate |
| search.sort_order | 정렬 방향 (ascending, descending) | descending |
| search.timeout_seconds | arXiv API 요청 타임아웃(초) | 30 |
| search.date_offset_days | 기준 날짜 오프셋 | -1 (어제) |
| claude.model | Claude 모델 | claude-sonnet-4-6 |
| claude.max_tokens | 요약 최대 토큰 | 512 |
| claude.temperature | 생성 다양성 | 0.3 |
| claude.call_interval_seconds | API 호출 간격(초) | 2.0 |
| claude.abstract_truncate_chars | 컨텍스트 초과 시 초록 잘라내기 문자 수 | 1000 |
| retry.attempts | 재시도 횟수 | 3 |
| retry.wait_seconds | 재시도 대기 시간(초) | 5 |
| retry.rate_limit_backoff_min | Rate Limit 지수 백오프 최솟값(초) | 10 |
| retry.rate_limit_backoff_max | Rate Limit 지수 백오프 최댓값(초) | 120 |
| paths.output_dir | 출력 디렉토리 | output |
| paths.log_dir | 로그 디렉토리 | logs |

---

## 실행 방법

```bash
source .venv/bin/activate
python main.py
```

---

## 출력 결과

output/ 디렉토리에 output/YYYY-MM-DD.md 파일이 생성됩니다.

```markdown
# arXiv 논문 요약 — 2026-03-28

> 키워드: LLM, multi-agent | 수집: 8개

---

## 1. Scaling LLM Reasoning with Multi-Agent Debate

**요약:**
1. 다수의 LLM 에이전트가 토론 방식으로 상호 검증하며 추론 정확도를 향상시키는 프레임워크를 제안한다.
2. 기존 모델에 플러그인 형태로 적용 가능하며 수학 벤치마크에서 SOTA를 달성했다.
3. 에이전트 수가 늘수록 성능이 향상되나 통신 비용도 증가한다.

---
```

---

## 에러 대처법

**1. ANTHROPIC_API_KEY가 설정되지 않았습니다**

.env 파일이 없거나 키가 비어있는 경우입니다. https://console.anthropic.com/settings/keys 에서 발급 후 .env에 추가하세요.

**2. config.yaml 필수 키 누락**

config.yaml이 손상되었거나 필드가 빠진 경우입니다. yaml.safe_load로 파일 문법을 검증하세요.

**3. arXiv API 최종 실패, 빈 리스트 반환**

네트워크 문제 또는 arXiv 서버 장애입니다. 잠시 후 재실행하거나 retry.attempts를 늘려보세요. 서비스 상태: https://status.arxiv.org/

**4. 오늘 날짜 논문이 0건 수집됨**

arXiv 반영 지연이 원인입니다. date_offset_days 기본값 -1(어제)을 유지하세요.

**5. 요약이 요약 실패로 표시됨**

Claude API 오류 또는 Rate Limit 초과입니다. logs/ 디렉토리의 로그 파일에서 상세 오류를 확인하세요.

---

## 자동 실행 설정

### macOS (launchd)

~/Library/LaunchAgents/com.user.arxiv-agent.plist 파일 생성 후 launchctl load로 등록합니다.

### Linux (crontab)

```bash
0 9 * * * cd /path/to/agents && python3 main.py >> logs/cron.log 2>&1
```

---

## 라이선스

MIT License
