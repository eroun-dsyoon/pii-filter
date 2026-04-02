"""
한국 은행 계좌번호 형식 기반 은행 식별
각 은행의 자릿수 구조(그룹 패턴)로 은행을 추정
"""
from __future__ import annotations

import re
from typing import Optional, List

# 은행별 계좌번호 그룹 패턴: (그룹별 자릿수 튜플, 은행명, 총 자릿수)
BANK_PATTERNS: List[tuple] = [
    # (그룹 자릿수, 은행명, 총 자릿수)
    ((4, 2, 7), "카카오뱅크", 13),
    ((3, 2, 6, 2), "NH농협", 13),
    ((3, 4, 6), "NH농협", 13),
    ((4, 3, 6), "우리은행", 13),
    ((3, 6, 5), "하나은행", 14),
    ((3, 3, 6), "신한은행", 12),       # KB국민도 동일 패턴 가능
    ((3, 2, 6), "KB국민은행", 11),
    ((6, 2, 6), "KB국민은행", 14),
    ((3, 6, 2, 3), "IBK기업은행", 14),
    ((4, 4, 4), "토스뱅크", 12),
    ((3, 3, 6), "케이뱅크", 12),
    ((3, 2, 7), "SC제일은행", 12),
    ((2, 2, 6), "제주은행", 10),
]

# 계좌번호 첫자리 기반 추가 힌트 (일부 은행)
FIRST_DIGIT_HINTS = {
    "1": ["KB국민은행", "우리은행"],
    "2": ["신한은행", "SC제일은행"],
    "3": ["IBK기업은행", "하나은행"],
    "9": ["NH농협"],
}


def identify_bank(account_number: str) -> Optional[str]:
    """
    계좌번호 문자열에서 은행을 추정.
    구분자(-, 공백 등)가 포함된 원본 형태를 분석.
    Returns: 은행명 또는 None
    """
    # 숫자 그룹 추출
    groups = re.findall(r'\d+', account_number)
    if not groups:
        return None

    group_lengths = tuple(len(g) for g in groups)
    total_digits = sum(group_lengths)

    # 패턴 매칭
    candidates = []
    for pattern, bank_name, expected_total in BANK_PATTERNS:
        if group_lengths == pattern:
            candidates.append((bank_name, 100))  # 완전 일치
        elif len(group_lengths) == len(pattern):
            # 그룹 수 동일, 자릿수 유사 (±1 허용)
            close = all(abs(a - b) <= 1 for a, b in zip(group_lengths, pattern))
            if close and abs(total_digits - expected_total) <= 1:
                candidates.append((bank_name, 70))

    if candidates:
        # 가장 높은 점수 반환
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]

    # 총 자릿수 기반 추정
    if total_digits == 11:
        return "KB국민은행 (추정)"
    elif total_digits == 12:
        return "신한은행 (추정)"
    elif total_digits == 13:
        return "우리은행/NH농협 (추정)"
    elif total_digits == 14:
        return "하나은행/IBK기업은행 (추정)"

    return None


def get_bank_info(account_number: str) -> dict:
    """
    계좌번호에 대한 은행 정보를 반환.
    Returns: {"bank": "은행명", "format": "3-3-6", "digits": 12}
    """
    groups = re.findall(r'\d+', account_number)
    group_lengths = tuple(len(g) for g in groups)
    total_digits = sum(group_lengths)
    format_str = "-".join(str(l) for l in group_lengths)

    bank = identify_bank(account_number)

    return {
        "bank": bank,
        "format": format_str,
        "digits": total_digits,
    }
