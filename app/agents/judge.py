"""
Judge 에이전트: Blue Team 결과 평가 및 피드백 제공
- 오탐/미탐 패턴 분석 (로컬)
- API 키가 있으면 Haiku 모델로 상세 분석 가능
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import List

from .blue_team import FilterResult

logger = logging.getLogger(__name__)


async def judge_results(
    results: List[FilterResult],
    batch_size: int = 20,
) -> dict:
    """
    Blue Team 결과를 Judge가 평가.
    로컬 분석으로 오탐/미탐 패턴 도출.
    """
    error_cases = [r for r in results if not r.is_correct]

    if not error_cases:
        return {
            "total_errors": 0,
            "false_positive_feedback": {"type": "false_positive", "patterns": []},
            "false_negative_feedback": {"type": "false_negative", "examples": []},
            "suggestions": [],
        }

    fp_cases = [r for r in error_cases if r.error_type == "false_positive"]
    fn_cases = [r for r in error_cases if r.error_type == "false_negative"]

    # FP 패턴 분석
    fp_patterns = _analyze_fp_patterns(fp_cases)

    # FN 패턴 분석
    fn_examples = _analyze_fn_patterns(fn_cases)

    suggestions = []
    if fp_cases:
        suggestions.append(f"오탐 {len(fp_cases)}건 중 가장 빈번한 유형: {fp_patterns.get('most_common_type', 'N/A')}")
    if fn_cases:
        suggestions.append(f"미탐 {len(fn_cases)}건 중 가장 빈번한 유형: {fn_examples.get('most_common_type', 'N/A')}")

    return {
        "total_errors": len(error_cases),
        "false_positive_feedback": {
            "type": "false_positive",
            "patterns": fp_patterns.get("patterns", []),
            "description": f"오탐 패턴 {len(fp_patterns.get('patterns', []))}개 발견",
        },
        "false_negative_feedback": {
            "type": "false_negative",
            "examples": fn_examples.get("examples", []),
            "description": f"미탐 케이스 {len(fn_examples.get('examples', []))}개 발견",
        },
        "suggestions": suggestions,
    }


def _analyze_fp_patterns(fp_cases: List[FilterResult]) -> dict:
    """오탐 케이스에서 반복되는 패턴 추출"""
    if not fp_cases:
        return {"patterns": [], "most_common_type": "N/A"}

    # 어떤 PII 타입이 가장 많이 오탐되는지
    detected_types = []
    text_patterns = []

    for r in fp_cases:
        for entity in r.detected_entities:
            detected_types.append(entity.get("type", "UNKNOWN"))

        # 텍스트에서 날짜/코드 등의 패턴 추출
        text = r.text
        if re.search(r'(?:19|20)\d{2}[\-./]\d{2,4}[\-./]\d{2,4}', text):
            text_patterns.append("날짜 형식")
        elif re.search(r'ISBN', text, re.IGNORECASE):
            text_patterns.append("ISBN")
        elif re.search(r'[A-Z]{2,}\-\d+', text):
            text_patterns.append("코드/문서번호")
        elif re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', text):
            text_patterns.append("IP 주소")
        else:
            text_patterns.append("기타")

    type_counter = Counter(detected_types)
    pattern_counter = Counter(text_patterns)

    return {
        "patterns": [f"{p}: {c}건" for p, c in pattern_counter.most_common(10)],
        "most_common_type": type_counter.most_common(1)[0][0] if type_counter else "N/A",
        "type_distribution": dict(type_counter),
    }


def _analyze_fn_patterns(fn_cases: List[FilterResult]) -> dict:
    """미탐 케이스에서 반복되는 패턴 추출"""
    if not fn_cases:
        return {"examples": [], "most_common_type": "N/A"}

    type_counter = Counter(r.expected_type for r in fn_cases if r.expected_type)

    # 미탐된 텍스트에서 우회 기법 분석
    evasion_types = []
    for r in fn_cases:
        text = r.text
        has_korean_digit = any(c in text for c in "공일이삼사오육칠팔구영")
        has_hanja = any(c in text for c in "〇一二三四五六七八九")
        has_special = any(ord(c) > 0x2000 and not c.isspace() for c in text)

        if has_korean_digit:
            evasion_types.append("한글 숫자")
        elif has_hanja:
            evasion_types.append("한자")
        elif has_special:
            evasion_types.append("특수 유니코드")
        else:
            evasion_types.append("구분자 변형")

    evasion_counter = Counter(evasion_types)

    return {
        "examples": [r.text[:100] for r in fn_cases[:50]],
        "most_common_type": type_counter.most_common(1)[0][0] if type_counter else "N/A",
        "type_distribution": dict(type_counter),
        "evasion_distribution": dict(evasion_counter),
    }
