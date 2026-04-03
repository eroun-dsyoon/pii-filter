"""
한국 개인정보 체계 기반 검증 모듈
각 PII 유형의 실제 구조와 검증 규칙을 구현
"""
from __future__ import annotations

import re
import calendar
from typing import Optional

# ============================================================
# 1. 주민등록번호 (RRN) - 13자리
# 구조: YYMMDD-GRRRSSC
# G: 성별(1-4), RRR: 지역코드, SS: 일련번호, C: 체크디짓
# 체크섬: 가중치 mod 11
# ============================================================

RRN_WEIGHTS = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]

DAYS_IN_MONTH = {
    1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31,
}


def validate_rrn(digits: str) -> bool:
    """주민등록번호 유효성 검증"""
    if len(digits) != 13:
        return False
    if not digits.isdigit():
        return False

    # 생년월일 검증
    month = int(digits[2:4])
    day = int(digits[4:6])
    gender = int(digits[6])

    if month < 1 or month > 12:
        return False
    if day < 1 or day > DAYS_IN_MONTH.get(month, 31):
        return False
    if gender < 1 or gender > 4:
        return False

    # 체크디짓 검증 (가중치 mod 11)
    weighted_sum = sum(int(digits[i]) * RRN_WEIGHTS[i] for i in range(12))
    check = (11 - (weighted_sum % 11)) % 10
    if check != int(digits[12]):
        return False

    return True


# ============================================================
# 2. 사업자등록번호 (CRN) - 10자리
# 구조: RRR-MM-SSSSSC
# RRR: 관할 세무서 지역코드 (100-899)
# MM: 사업 개시 구분 (01-99)
# SSSSS: 일련번호, C: 체크디짓
# 체크섬: 가중치 mod 10
# ============================================================

CRN_WEIGHTS = [1, 3, 7, 1, 3, 7, 1, 3, 5]


def validate_crn(digits: str) -> bool:
    """사업자등록번호 유효성 검증"""
    if len(digits) != 10:
        return False
    if not digits.isdigit():
        return False

    # 지역코드 검증: 100 이상
    region = int(digits[:3])
    if region < 100:
        return False

    # 체크디짓 검증
    weighted_sum = 0
    for i in range(9):
        weighted_sum += int(digits[i]) * CRN_WEIGHTS[i]
    # 8번째 자리(index 8)의 가중치 5로 곱한 후 10으로 나눈 몫도 더함
    weighted_sum += (int(digits[8]) * 5) // 10
    check = (10 - (weighted_sum % 10)) % 10

    return check == int(digits[9])


# ============================================================
# 3. 전화번호 (Phone)
# 휴대폰: 010/011/016/017/018/019-XXXX-XXXX
# 서울: 02-XXX(X)-XXXX
# 지역: 031~064-XXX(X)-XXXX
# 인터넷전화(VoIP): 070-XXXX-XXXX
# 안심번호/부가서비스: 0502/0504/0505/0507-XXX(X)-XXXX
# 수신자부담: 080-XXX(X)-XXXX
# 대표번호: 1588/1577/1544/1566/1600/1670 등-XXXX
# ============================================================

VALID_MOBILE_PREFIXES = {'010', '011', '016', '017', '018', '019'}

# 유효한 지역번호: 02(서울), 031~064
VALID_AREA_CODES = {
    '02',   # 서울
    '031',  # 경기
    '032',  # 인천
    '033',  # 강원
    '041',  # 충남
    '042',  # 대전
    '043',  # 충북
    '044',  # 세종
    '051',  # 부산
    '052',  # 울산
    '053',  # 대구
    '054',  # 경북
    '055',  # 경남
    '061',  # 전남
    '062',  # 광주
    '063',  # 전북
    '064',  # 제주
}

# VoIP (인터넷전화)
VALID_VOIP_PREFIXES = {'070'}

# 안심번호/부가통신: 0502, 0504, 0505, 0507 등
VALID_VIRTUAL_PREFIXES = {'0502', '0504', '0505', '0506', '0507', '0508'}

# 수신자부담
VALID_TOLL_FREE_PREFIXES = {'080'}

# 대표번호 (15XX, 16XX)
VALID_REPRESENTATIVE_PREFIXES = {
    '1588', '1577', '1544', '1566', '1600', '1670', '1599',
    '1644', '1660', '1661', '1688', '1666', '1899', '1800',
    '1811', '1833', '1855', '1877',
}


def validate_phone(digits: str) -> bool:
    """전화번호 유효성 검증 (모든 한국 전화번호 체계 포함)"""
    if not digits.isdigit():
        return False
    length = len(digits)

    # 대표번호: 15XX-XXXX, 16XX-XXXX (8자리)
    if length == 8 and digits[:4] in VALID_REPRESENTATIVE_PREFIXES:
        return True

    if length < 9 or length > 12:
        return False

    # 휴대폰: 010/011/016/017/018/019
    if digits[:3] in VALID_MOBILE_PREFIXES:
        return 10 <= length <= 11

    # VoIP (인터넷전화): 070-XXXX-XXXX (11자리)
    if digits[:3] in VALID_VOIP_PREFIXES:
        return length == 11

    # 수신자부담: 080-XXX(X)-XXXX (10~11자리)
    if digits[:3] in VALID_TOLL_FREE_PREFIXES:
        return 10 <= length <= 11

    # 안심번호/부가통신: 0502/0505 등-XXX(X)-XXXX (11~12자리)
    if digits[:4] in VALID_VIRTUAL_PREFIXES:
        return 11 <= length <= 12

    # 서울: 02-XXX(X)-XXXX (9~10자리)
    if digits.startswith('02'):
        return 9 <= length <= 10

    # 지역번호: 031~064-XXX(X)-XXXX (10~11자리)
    if digits[:3] in VALID_AREA_CODES:
        return 10 <= length <= 11

    return False


# ============================================================
# 4. 여권번호 (Passport)
# 구조: 알파벳 1~2자리 + 숫자 7자리
# 유효 알파벳: M(일반), S(관용), R(거주), G(긴급) 등
# ============================================================

VALID_PASSPORT_PREFIXES = {
    'M',   # 일반여권 (2008년 이후)
    'PM',  # 일반여권 (구형)
    'PS',  # 관용여권 (구형)
    'PD',  # 외교관여권 (구형)
    'S',   # 관용여권
    'R',   # 거주여권
    'G',   # 긴급여권
    'D',   # 외교관여권
}


def validate_passport(text: str) -> bool:
    """여권번호 유효성 검증"""
    text = text.strip()
    if len(text) < 8 or len(text) > 9:
        return False

    # 영문+숫자 분리
    alpha = ""
    num = ""
    for c in text:
        if c.isalpha():
            alpha += c.upper()
        elif c.isdigit():
            num += c

    if not alpha or not num:
        return False

    # 알파벳 1~2자리
    if len(alpha) < 1 or len(alpha) > 2:
        return False

    # 숫자 7자리
    if len(num) != 7:
        return False

    # 유효한 접두사 확인
    if alpha not in VALID_PASSPORT_PREFIXES and alpha[0] not in 'MSPRDG':
        return False

    return True


# ============================================================
# 5. 신용카드 (Credit Card) - 16자리
# BIN(처음 6자리): 카드사 식별
# Luhn 알고리즘 체크섬
# ============================================================

# 한국에서 사용되는 주요 BIN 범위
VALID_BIN_RANGES = [
    (300000, 305999),   # Diners Club
    (340000, 349999),   # AMEX
    (370000, 379999),   # AMEX
    (400000, 499999),   # VISA
    (510000, 559999),   # Mastercard
    (600000, 699999),   # Discover / UnionPay
    (900000, 999999),   # 한국 내수카드
    (352800, 358999),   # JCB
]


def validate_credit_card(digits: str) -> bool:
    """신용카드 유효성 검증 (Luhn + BIN)"""
    if len(digits) != 16:
        return False
    if not digits.isdigit():
        return False

    # BIN 검증: 유효한 카드사 범위인지
    bin_num = int(digits[:6])
    valid_bin = any(lo <= bin_num <= hi for lo, hi in VALID_BIN_RANGES)
    if not valid_bin:
        return False

    # Luhn 알고리즘
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ============================================================
# 6. 운전면허번호 (Driver License) - 12자리
# 구조: RR-YY-SSSSSS-CC
# RR: 지역코드 (01-17)
# YY: 발급연도 (00-99)
# SSSSSS: 일련번호
# CC: 검증번호
# ============================================================

DRIVER_LICENSE_REGIONS = {
    '01': '서울', '02': '부산', '03': '대구', '04': '인천',
    '05': '광주', '06': '대전', '07': '울산', '08': '경기',
    '09': '강원', '10': '충북', '11': '충남', '12': '전북',
    '13': '전남', '14': '경북', '15': '경남', '16': '제주',
    '17': '세종',
}


def validate_driver_license(digits: str) -> bool:
    """운전면허번호 유효성 검증"""
    if len(digits) != 12:
        return False
    if not digits.isdigit():
        return False

    # 지역코드: 01-17
    region = digits[:2]
    if region not in DRIVER_LICENSE_REGIONS:
        return False

    # 발급연도: 00-99 (제한 없음)
    # 일련번호: 000001 이상
    serial = int(digits[4:10])
    if serial < 1:
        return False

    # 검증번호 (mod 97 방식)
    first_10 = int(digits[:10])
    expected_check = first_10 % 97
    actual_check = int(digits[10:12])

    return expected_check == actual_check


# ============================================================
# 7. 계좌번호 (Bank Account) - 10~14자리
# 은행별 형식, 체크섬 없음
# 추가 검증: 날짜/주문번호/ISBN 등 비PII 제외
# ============================================================

def validate_bank_account(digits: str) -> bool:
    """계좌번호 유효성 검증"""
    if not digits.isdigit():
        return False
    length = len(digits)
    if length < 10 or length > 14:
        return False

    # 앞 4자리가 연도(2000~2099)이면 날짜/주문번호
    first4 = int(digits[:4])
    if 2000 <= first4 <= 2099:
        return False

    # 모든 자릿수가 같으면 무효 (0000000000 등)
    if len(set(digits)) == 1:
        return False

    return True


# ============================================================
# 8. 이메일 (Email)
# RFC 5321 기반 형식 검증
# ============================================================

def validate_email(text: str) -> bool:
    """이메일 형식 검증"""
    if '@' not in text:
        return False

    parts = text.split('@')
    if len(parts) != 2:
        return False

    local, domain = parts

    # local-part 검증
    if not local or len(local) > 64:
        return False
    if local.startswith('.') or local.endswith('.'):
        return False
    if '..' in local:
        return False

    # domain-part 검증
    if not domain or len(domain) > 255:
        return False
    if domain.startswith('.') or domain.startswith('-'):
        return False
    if '..' in domain:
        return False

    # TLD 최소 2자
    domain_parts = domain.split('.')
    if len(domain_parts) < 2:
        return False
    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False

    return True


# ============================================================
# 통합 Validator 인터페이스
# ============================================================

VALIDATORS = {
    "RRN": validate_rrn,
    "CRN": validate_crn,
    "PHONE": validate_phone,
    "CREDIT_CARD": validate_credit_card,
    "DRIVER_LICENSE": validate_driver_license,
    "BANK_ACCOUNT": validate_bank_account,
}

# 여권, 이메일은 텍스트 기반 검증 (숫자만이 아님)
TEXT_VALIDATORS = {
    "PASSPORT": validate_passport,
    "EMAIL": validate_email,
}


def validate_pii(pii_type: str, digits: str, original_text: str = "") -> bool:
    """
    통합 PII 검증.
    digits: 숫자만 추출된 값
    original_text: 원본 텍스트 (여권, 이메일 등에 필요)
    """
    if pii_type in VALIDATORS:
        return VALIDATORS[pii_type](digits)
    if pii_type in TEXT_VALIDATORS:
        return TEXT_VALIDATORS[pii_type](original_text or digits)
    return True  # 알 수 없는 타입은 통과
