# Hugging Face 트렌딩 수집 에이전트

Hugging Face의 트렌딩 모델·데이터셋·스페이스를 자동으로 수집하여 JSON / Markdown / CSV 형식으로 저장하는 에이전트입니다.

---

## 주요 기능

- Hugging Face 공개 API를 통해 트렌딩 항목 수집 (모델, 데이터셋, 스페이스)
- JSON / Markdown / CSV 다중 포맷 출력
- 날짜별 파일 저장 (`output/hf_trending_YYYYMMDD.*`)
- API 재시도 로직 (최대 3회)
- 타임아웃 처리 (15초)
- 에러 로깅 (`logs/hf_trending_YYYYMMDD.log`)
- HF_TOKEN 선택적 지원 (없어도 작동)

---

## 요구사항

- Python 3.10+
- 인터넷 연결

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 환경 설정

```bash
cp .env.example .env
# .env 파일에서 HF_TOKEN 설정 (선택사항)
```

`.env` 파일이 없거나 `HF_TOKEN`이 비어 있어도 공개 API로 동작합니다.

---

## config.yaml 설명

| 키 | 설명 | 기본값 |
|---|---|---|
| `hf.categories` | 수집할 카테고리 | models, datasets, spaces |
| `hf.limits.models` | 모델 수집 개수 | 30 |
| `hf.limits.datasets` | 데이터셋 수집 개수 | 20 |
| `hf.limits.spaces` | 스페이스 수집 개수 | 20 |
| `output.formats` | 출력 포맷 목록 | json, md, csv |
| `output.dir` | 출력 디렉토리 | output |
| `retry.max_attempts` | API 재시도 횟수 | 3 |
| `retry.delay_seconds` | 재시도 간 대기(초) | 2 |

---

## 실행 방법

```bash
python main.py
```

---

## 출력 예시

```
output/
├── hf_trending_20260421.json
├── hf_trending_20260421.md
└── hf_trending_20260421.csv
```

**JSON 예시:**
```json
{
  "collected_at": "2026-04-21T10:00:00",
  "data": {
    "models": [
      {"id": "meta-llama/Llama-3-8B", "author": "meta-llama", "likes": 1234, ...}
    ]
  }
}
```

---

## 에러 대처법

| 에러 | 원인 | 해결 방법 |
|---|---|---|
| `FileNotFoundError: config.yaml` | 설정 파일 없음 | 프로젝트 루트에서 실행 확인 |
| `HF API 인증 실패 (401)` | 토큰 오류 | `.env`의 `HF_TOKEN` 값 확인 또는 삭제 |
| `수집 실패: 3회 재시도 후` | 네트워크 오류 | 인터넷 연결 확인 후 재실행 |

---

## 라이선스

MIT
