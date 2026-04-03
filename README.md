# PII Filter - 한국 개인정보 필터링 서비스

한국 개인정보(PII)를 검출하는 서비스입니다. 기본 형식뿐 아니라 구분자 변형, 대체 문자(한글 숫자, 한자, Leet, 이모지, 전각 문자 등)를 통한 우회 시도도 탐지합니다.

## 주요 기능

- **3단계 검출 레벨**: 기본 형식 → 다양한 구분자 → 대체 문자
- **8가지 PII 유형**: 주민등록번호, 사업자등록번호, 전화번호, 여권번호, 계좌번호, 신용카드, 운전면허번호, 이메일
- **고속 처리**: 1건당 평균 0.15ms (목표 10ms 이내)
- **오탐 신고**: 사용자가 오탐(False Positive)을 신고할 수 있는 기능
- **에이전트 기반 모델 개선**: Red Team → Blue Team → Judge 파이프라인

## 에이전트 시스템

| 에이전트 | 역할 | 모델 |
|---------|------|------|
| Red Team | 합성 데이터 생성 (우회 시도 + 정상 데이터) | Claude Haiku |
| Blue Team | PII 필터링 실행 및 알고리즘 개선 | 정규식 엔진 |
| Judge | 오탐/미탐 판정 및 피드백 제공 | Claude Haiku |

## 설치 및 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 설정

# 서버 실행
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 사용법

### 웹 UI
- **사용자 페이지**: http://localhost:8000 - 텍스트/파일에서 PII 검출
- **관리자 페이지**: http://localhost:8000/admin - 합성 데이터 생성 및 모델 개선

### API

```bash
# 텍스트 PII 검출
curl -X POST http://localhost:8000/api/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "전화번호 010-1234-5678", "level": 3}'

# 파일 PII 검출
curl -X POST http://localhost:8000/api/detect/file \
  -F "file=@sample.txt" -F "level=3"

# 오탐 신고
curl -X POST http://localhost:8000/api/report/false-positive \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "entity": "...", "entity_type": "PHONE", "reason": "..."}'

# 합성 데이터 생성 파이프라인 실행
curl -X POST http://localhost:8000/api/admin/generate \
  -H "Content-Type: application/json" \
  -d '{"count": 1000, "level": 3}'
```

## 검출 레벨

| 레벨 | 검출 범위 | 오탐 가능성 |
|------|----------|-----------|
| 1단계 | 기본 형식 (010-1234-5678) | 낮음 |
| 2단계 | 1단계 + 다양한 구분자 | 중간 |
| 3단계 | 2단계 + 대체 문자 (한글, 한자, Leet 등) | 높음 |

## 테스트

```bash
python3 -m tests.test_filter_engine
```

## 프로젝트 구조

```
pii-filter/
├── app/
│   ├── main.py              # FastAPI 앱
│   ├── config.py             # 설정
│   ├── core/
│   │   ├── char_map.py       # 문자 대체 매핑
│   │   ├── patterns.py       # 정규식 패턴
│   │   └── filter_engine.py  # 필터링 엔진
│   ├── agents/
│   │   ├── red_team.py       # 합성 데이터 생성
│   │   ├── blue_team.py      # 필터링 및 평가
│   │   ├── judge.py          # 결과 판정
│   │   └── orchestrator.py   # 파이프라인 관리
│   ├── api/
│   │   └── routes.py         # API 라우트
│   ├── models/
│   │   └── schemas.py        # Pydantic 스키마
│   └── static/               # 웹 UI
├── data/synthetic/           # 합성 데이터
├── sdk/
│   ├── __init__.py           # from sdk import detect
│   └── pii_detector.py       # 개발자용 판별 함수
├── docs/
│   ├── 개발자_적용가이드.md    # 적용 및 테스트 설명서
│   └── CLAUDE_CODE_실무가이드.md  # 개발 과정 가이드
├── reports/                  # 개선 리포트
└── tests/
```
