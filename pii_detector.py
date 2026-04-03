"""
PII Detector - 한국 개인정보 검출 함수
========================================

개발자가 바로 import하여 사용할 수 있는 단일 파일 인터페이스.

사용법:
    from pii_detector import detect, PIIResult

    result = detect("전화번호는 010-1234-5678 입니다.")
    print(result.has_pii)        # True
    print(result.count)          # 1
    print(result.elapsed_ms)     # 0.05
    print(result.entities[0])    # PIIEntity(...)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Optional, List

from app.core.filter_engine import PIIFilterEngine


# ============================================================
# 출력 데이터 구조
# ============================================================

@dataclass
class PIIEntity:
    """검출된 개인정보 엔티티"""
    type: str                          # PII 유형 (RRN, PHONE, EMAIL 등)
    type_label: str                    # 한국어 라벨 (주민등록번호, 전화번호 등)
    entity: str                        # 원본 텍스트에서 매칭된 문자열
    level: int                         # 판별 레벨 (1=기본형식, 2=구분자변형, 3=대체문자)
    level_label: str                   # 판별 레벨 한국어 (1단계 - 기본 형식)
    start: int                         # 원본 텍스트에서의 시작 위치 (0-indexed)
    end: int                           # 원본 텍스트에서의 끝 위치
    normalized: Optional[str] = None   # 정규화된 값 (대체문자 → 원래 값)
    detail: Optional[dict] = None      # 추가 정보 (계좌번호: 은행명 등)

    def to_dict(self) -> dict:
        d = {
            "type": self.type,
            "type_label": self.type_label,
            "entity": self.entity,
            "level": self.level,
            "level_label": self.level_label,
            "start": self.start,
            "end": self.end,
        }
        if self.normalized:
            d["normalized"] = self.normalized
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass
class PIIResult:
    """검출 결과"""
    has_pii: bool                      # PII 존재 여부
    count: int                         # 검출된 PII 개수
    elapsed_ms: float                  # 처리 시간 (ms)
    text_length: int                   # 입력 텍스트 길이
    level: int                         # 사용된 검출 레벨
    strict: bool                       # 사용된 검증 강도
    entities: List[PIIEntity]          # 검출된 엔티티 목록

    def to_dict(self) -> dict:
        return {
            "has_pii": self.has_pii,
            "count": self.count,
            "elapsed_ms": self.elapsed_ms,
            "text_length": self.text_length,
            "level": self.level,
            "strict": self.strict,
            "entities": [e.to_dict() for e in self.entities],
        }

    def summary(self) -> str:
        """사람이 읽기 좋은 요약 문자열"""
        if not self.has_pii:
            return f"개인정보 미검출 ({self.elapsed_ms:.3f}ms)"
        types = ", ".join(set(e.type_label for e in self.entities))
        return f"개인정보 {self.count}건 검출 [{types}] ({self.elapsed_ms:.3f}ms)"


# ============================================================
# 유형 라벨 및 레벨 라벨 매핑
# ============================================================

TYPE_LABELS = {
    "RRN": "주민등록번호",
    "CRN": "사업자등록번호",
    "PHONE": "전화번호",
    "PASSPORT": "여권번호",
    "BANK_ACCOUNT": "계좌번호",
    "CREDIT_CARD": "신용카드",
    "DRIVER_LICENSE": "운전면허번호",
    "EMAIL": "이메일",
}

LEVEL_LABELS = {
    1: "1단계 - 기본 형식",
    2: "2단계 - 구분자 변형",
    3: "3단계 - 대체 문자",
}


# ============================================================
# 핵심 함수
# ============================================================

def detect(
    text: str,
    level: int = 3,
    strict: bool = True,
) -> PIIResult:
    """
    텍스트에서 한국 개인정보(PII)를 검출합니다.

    Parameters
    ----------
    text : str
        검사할 텍스트. 문장, 문단, 파일 내용 등 길이 제한 없음.

    level : int (1, 2, 3), default=3
        검출 레벨.
        1 = 기본 형식만 (010-1234-5678)
        2 = 1 + 구분자 변형 (010 - 1234 _ 5678)
        3 = 2 + 대체 문자 (공일공-일이삼사-오육칠팔)

    strict : bool, default=True
        검증 강도.
        True  = 체계 기반 검증 (체크섬, 유효 지역코드, BIN 등)
                → 정밀도 높음, 오탐 적음
        False = 형식만 검증 (자릿수만 맞으면 검출)
                → 재현율 높음, 오탐 가능성 있음

    Returns
    -------
    PIIResult
        .has_pii     : bool   - PII 존재 여부
        .count       : int    - 검출 개수
        .elapsed_ms  : float  - 처리 시간(ms)
        .text_length : int    - 입력 텍스트 길이
        .entities    : list   - PIIEntity 목록
        .to_dict()   : dict   - JSON 직렬화 가능한 dict
        .summary()   : str    - 사람이 읽기 좋은 요약

    Examples
    --------
    >>> from pii_detector import detect
    >>> r = detect("전화번호 010-1234-5678")
    >>> r.has_pii
    True
    >>> r.entities[0].type
    'PHONE'
    >>> r.entities[0].type_label
    '전화번호'

    >>> # 구분자 변형
    >>> r = detect("010 - 1234 _ 5678", level=2)
    >>> r.entities[0].level_label
    '2단계 - 구분자 변형'

    >>> # 형식만 검증 (체크섬 무시)
    >>> r = detect("990230-1234567", level=1, strict=False)
    >>> r.has_pii  # 2월30일이지만 형식만 검증이므로 검출
    True

    >>> # 대체 문자 (한글 숫자)
    >>> r = detect("공일공-일이삼사-오육칠팔", level=3)
    >>> r.entities[0].normalized
    '010-1234-5678'
    """
    engine = PIIFilterEngine(level=level, strict=strict)

    start_time = time.perf_counter()
    raw_entities = engine.detect(text)
    elapsed = (time.perf_counter() - start_time) * 1000

    entities = []
    for e in raw_entities:
        d = e.to_dict()
        entities.append(PIIEntity(
            type=d["type"],
            type_label=TYPE_LABELS.get(d["type"], d["type"]),
            entity=d["entity"],
            level=d["level"],
            level_label=LEVEL_LABELS.get(d["level"], f"{d['level']}단계"),
            start=d["start"],
            end=d["end"],
            normalized=d.get("normalized"),
            detail=d.get("detail"),
        ))

    return PIIResult(
        has_pii=len(entities) > 0,
        count=len(entities),
        elapsed_ms=round(elapsed, 3),
        text_length=len(text),
        level=level,
        strict=strict,
        entities=entities,
    )


def detect_batch(
    texts: List[str],
    level: int = 3,
    strict: bool = True,
) -> List[PIIResult]:
    """
    여러 텍스트를 한번에 검출합니다.

    Parameters
    ----------
    texts : list of str
        검사할 텍스트 목록.

    Returns
    -------
    list of PIIResult
    """
    return [detect(t, level=level, strict=strict) for t in texts]


# ============================================================
# 지원하는 PII 유형 정보
# ============================================================

def get_supported_types() -> list:
    """지원하는 PII 유형 목록을 반환합니다."""
    return [
        {"type": "RRN", "label": "주민등록번호", "format": "YYMMDD-GXXXXXX", "checksum": True,
         "description": "체크디짓(mod 11), 생년월일·성별 유효성 검증"},
        {"type": "CRN", "label": "사업자등록번호", "format": "XXX-XX-XXXXX", "checksum": True,
         "description": "체크디짓(mod 10), 지역코드(100~899) 검증"},
        {"type": "PHONE", "label": "전화번호", "format": "0XX-XXXX-XXXX", "checksum": False,
         "description": "휴대폰/070(VoIP)/080(수신자부담)/0505(안심번호)/15XX(대표번호)/지역번호"},
        {"type": "PASSPORT", "label": "여권번호", "format": "A0000000", "checksum": False,
         "description": "접두사(M,S,R,G,D) + 숫자 7자리"},
        {"type": "BANK_ACCOUNT", "label": "계좌번호", "format": "XXX-XXXX-XXXXXX", "checksum": False,
         "description": "은행별 형식 식별 (KB국민, 신한, 우리, 하나, NH농협, 카카오뱅크 등)"},
        {"type": "CREDIT_CARD", "label": "신용카드", "format": "XXXX-XXXX-XXXX-XXXX", "checksum": True,
         "description": "Luhn 알고리즘 + BIN(카드사) 범위 검증"},
        {"type": "DRIVER_LICENSE", "label": "운전면허번호", "format": "RR-YY-SSSSSS-CC", "checksum": True,
         "description": "지역코드(01~17) + 체크디짓(mod 97)"},
        {"type": "EMAIL", "label": "이메일", "format": "user@domain.com", "checksum": False,
         "description": "RFC 5321 형식 검증"},
    ]


# ============================================================
# CLI 실행 지원
# ============================================================

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("사용법: python pii_detector.py '검사할 텍스트' [레벨] [strict]")
        print("  레벨: 1, 2, 3 (기본: 3)")
        print("  strict: true, false (기본: true)")
        print()
        print("예시:")
        print("  python pii_detector.py '전화번호 010-1234-5678'")
        print("  python pii_detector.py '990230-1234567' 1 false")
        sys.exit(0)

    text = sys.argv[1]
    level = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    strict = sys.argv[3].lower() != 'false' if len(sys.argv) > 3 else True

    result = detect(text, level=level, strict=strict)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
