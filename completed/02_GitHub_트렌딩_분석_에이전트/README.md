# GitHub 트렌딩 분석 에이전트

GitHub Trending 페이지에서 인기 레포지토리를 자동으로 수집하고, Claude AI가 기술 트렌드를 분석해 마크다운·JSON·CSV 보고서를 생성합니다. 매일 실행하면 날짜별로 파일이 분리되어 저장되므로 장기 트렌드 추적이 가능합니다.

## 주요 기능

- GitHub Trending에서 전체·Python·JavaScript·TypeScript 레포지토리 자동 수집
- Claude AI를 이용한 트렌드 요약, 주목 레포 TOP 3, 언어별 동향, 개발자 인사이트 생성
- 날짜별 자동 파일 분리 저장 (output/trending_YYYY-MM-DD.{md,json,csv})
- HTTP 요청 실패 시 최대 3회 자동 재시도
- 모든 오류를 로그에 기록하고 크래시 없이 계속 실행
- `--no-analyze` 옵션으로 API 키 없이 스크래핑만 수행 가능

## 요구사항

- Python 3.10 이상
- Anthropic API 키 ([발급처](https://console.anthropic.com/))

## 설치 방법

```bash
# 1. 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate.bat     # Windows

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 파일 생성
cp .env.example .env
```

## 환경 설정

`.env` 파일을 열고 API 키를 입력합니다:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

| 키 | 발급처 |
|----|--------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |

## 실행 방법

```bash
# 기본 실행 (수집 + Claude 분석)
python main.py

# 분석 없이 스크래핑만 수행 (API 키 불필요)
python main.py --no-analyze

# 특정 기간으로 실행
python main.py --period weekly     # daily | weekly | monthly

# 특정 언어만 수집
python main.py --lang python

# 커스텀 설정 파일 사용
python main.py --config my_config.yaml
```

### CLI 옵션 전체 목록

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--config` | `config.yaml` | 설정 파일 경로 |
| `--period` | config.yaml 값 | `daily` \| `weekly` \| `monthly` |
| `--lang` | config.yaml 값 | 수집할 단일 언어 (예: `python`) |
| `--no-analyze` | False | Claude AI 분석 건너뜀 |

## config.yaml 필드 설명

```yaml
scraper:
  base_url: "https://github.com/trending"   # 트렌딩 페이지 기본 URL
  period: "daily"                           # 기간: daily | weekly | monthly
  languages: ["", "python", ...]            # 수집 언어 목록 (""=전체)
  timeout: 30                               # HTTP 요청 타임아웃 (초)
  delay_between_requests: 2                 # 요청 간 딜레이 (초)
  max_retries: 3                            # 최대 재시도 횟수
  retry_delay: 5                            # 재시도 간 대기 시간 (초)
  top_n: 25                                 # 언어별 수집 레포 수 (최대 25)
  user_agent: "Mozilla/5.0 ..."            # HTTP User-Agent 헤더

analyzer:
  model: "claude-opus-4-5"                  # Claude 모델명
  max_tokens: 2000                          # 응답 최대 토큰 수
  top_repos_for_analysis: 10               # 분석할 상위 레포 수
  max_retries: 3                            # API 재시도 횟수
  retry_delay: 10                           # API 재시도 대기 시간 (초)
  prompt_language: "ko"                     # 분석 결과 언어: ko | en

storage:
  data_dir: "data"                          # 원본 데이터 저장 디렉토리
  json_indent: 2                            # JSON 들여쓰기 칸 수
  date_format: "%Y-%m-%d"                   # 파일명 날짜 형식

output:
  output_dir: "output"                      # 보고서 저장 디렉토리
  formats: ["md", "json", "csv"]           # 출력 형식 (복수 선택 가능)
  report_title: "GitHub 트렌딩 분석 보고서" # 마크다운 보고서 제목
  date_format: "%Y-%m-%d"                   # 파일명 날짜 형식

logging:
  log_dir: "logs"                           # 로그 파일 저장 디렉토리
  level: "INFO"                             # 로그 레벨: DEBUG|INFO|WARNING|ERROR
  filename_format: "trending_%Y-%m-%d.log"  # 로그 파일명 형식
  console_output: true                      # 콘솔 출력 여부
```

## 출력 결과

실행 후 `output/` 폴더에 아래 파일이 생성됩니다:

**trending_2026-03-30.md** (마크다운 보고서 예시):
```markdown
# GitHub 트렌딩 분석 보고서

**날짜:** 2026-03-30
**수집된 레포지토리:** 46개

## AI 분석 결과

### 오늘의 주요 트렌드 요약
AI 에이전트 및 멀티에이전트 오케스트레이션 도구가 급부상하고 있습니다...

## 수집된 레포지토리 목록

| 순위 | 레포지토리 | 언어 | 스타 | 오늘 증가 | 포크 |
|------|-----------|------|------|-----------|------|
| 1 | microsoft/VibeVoice | Python | 28,620 | +2,509 | 3,146 |
```

**trending_2026-03-30.csv** (CSV 예시):
```
rank,full_name,url,language,stars,stars_today,forks,description,...
1,microsoft/VibeVoice,https://github.com/microsoft/VibeVoice,Python,28620,2509,3146,...
```

**trending_2026-03-30.json**: 전체 데이터를 구조화된 JSON으로 저장 (AI 분석 텍스트 포함)

## 에러 대처법

**1. `ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다`**
- `.env` 파일이 없거나 API 키가 비어 있음
- 해결: `cp .env.example .env` 후 실제 키 입력
- 분석 없이 스크래핑만 하려면 `--no-analyze` 옵션 사용

**2. `타임아웃 발생` / `연결 오류`**
- 네트워크 불안정 또는 GitHub 서버 응답 지연
- 해결: `config.yaml`의 `timeout` 값을 늘리거나 (예: `60`), 잠시 후 재실행
- 3회 자동 재시도 후에도 실패하면 로그에 ERROR로 기록되고 해당 언어는 건너뜀

**3. `파싱 완료: 0개 레포지토리`**
- GitHub HTML 구조가 변경되었거나 접근이 차단된 경우
- 해결: `config.yaml`의 `user_agent` 값을 최신 브라우저 User-Agent로 변경
- 또는 `delay_between_requests` 값을 늘려 요청 속도 조절

**4. `API 키가 유효하지 않습니다`**
- Anthropic API 키가 만료되었거나 잘못된 키
- 해결: https://console.anthropic.com/ 에서 새 키 발급 후 `.env` 업데이트

**5. `Rate limit 초과`**
- Claude API 요청 한도 초과
- 해결: `config.yaml`의 `analyzer.retry_delay` 값을 늘리거나 (예: `30`), 잠시 후 재실행

## 라이선스

MIT License
