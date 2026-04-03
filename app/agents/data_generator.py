"""
알고리즘 기반 합성 데이터 생성기
- 체계 기반 검증을 통과하는 유효한 PII 생성
- Level 1/2/3 변형 적용
- LLM 호출 없이 빠르게 동작
"""
from __future__ import annotations

import random
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from ..core.char_map import DIGIT_ALTERNATIVES
from ..core.validators import (
    RRN_WEIGHTS, CRN_WEIGHTS, DRIVER_LICENSE_REGIONS,
    VALID_MOBILE_PREFIXES, VALID_AREA_CODES,
    VALID_BIN_RANGES, DAYS_IN_MONTH,
)
from ..config import DATA_DIR

# === 체계 기반 PII 값 생성기 ===

def _random_rrn() -> Tuple[str, str]:
    """체크섬이 유효한 주민등록번호 생성"""
    year = random.randint(50, 99)
    month = random.randint(1, 12)
    max_day = DAYS_IN_MONTH[month]
    day = random.randint(1, max_day)
    gender = random.choice([1, 2])  # 1900년대
    region = random.randint(0, 95)
    serial = random.randint(0, 99)

    first_12 = f"{year:02d}{month:02d}{day:02d}{gender}{region:02d}{random.randint(10,99):02d}{serial:02d}"
    # 12자리에서 체크디짓 계산
    first_12 = first_12[:12]
    weighted_sum = sum(int(first_12[i]) * RRN_WEIGHTS[i] for i in range(12))
    check = (11 - (weighted_sum % 11)) % 10
    digits = first_12 + str(check)
    formatted = f"{digits[:6]}-{digits[6:]}"
    return formatted, digits


def _random_crn() -> Tuple[str, str]:
    """체크섬이 유효한 사업자등록번호 생성"""
    region = random.randint(100, 899)
    issue_month = random.randint(1, 12)
    serial = random.randint(0, 9999)

    first_9 = f"{region:03d}{issue_month:02d}{serial:04d}"
    # 체크디짓 계산
    weighted_sum = 0
    for i in range(9):
        weighted_sum += int(first_9[i]) * CRN_WEIGHTS[i]
    weighted_sum += (int(first_9[8]) * 5) // 10
    check = (10 - (weighted_sum % 10)) % 10
    digits = first_9 + str(check)
    formatted = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return formatted, digits


def _random_phone() -> Tuple[str, str]:
    """유효한 지역번호를 가진 전화번호 생성"""
    phone_type = random.choice(["mobile", "seoul", "regional"])

    if phone_type == "mobile":
        prefix = random.choice(list(VALID_MOBILE_PREFIXES))
        mid = random.randint(1000, 9999)
        last = random.randint(1000, 9999)
        digits = f"{prefix}{mid}{last}"
        formatted = f"{prefix}-{mid}-{last}"
    elif phone_type == "seoul":
        mid = random.randint(100, 9999)
        last = random.randint(1000, 9999)
        digits = f"02{mid}{last}"
        formatted = f"02-{mid}-{last}"
    else:
        area = random.choice([c for c in VALID_AREA_CODES if c != '02'])
        mid = random.randint(100, 9999)
        last = random.randint(1000, 9999)
        digits = f"{area}{mid}{last}"
        formatted = f"{area}-{mid}-{last}"
    return formatted, digits


def _random_email() -> str:
    """유효한 이메일 생성"""
    names = ["kim", "lee", "park", "choi", "jung", "kang", "cho", "yoon",
             "jang", "lim", "user", "admin", "test", "hello", "info"]
    domains = ["gmail.com", "naver.com", "daum.net", "kakao.com",
               "hanmail.net", "outlook.com", "company.co.kr"]
    name = random.choice(names) + str(random.randint(1, 999))
    domain = random.choice(domains)
    return f"{name}@{domain}"


def _random_credit_card() -> Tuple[str, str]:
    """BIN 유효 + Luhn 유효한 신용카드 번호 생성"""
    # 유효한 BIN 범위에서 선택
    bin_range = random.choice(VALID_BIN_RANGES)
    bin_num = random.randint(bin_range[0], bin_range[1])
    prefix = str(bin_num)

    # 나머지 자릿수 랜덤 (15자리까지)
    digits = prefix
    while len(digits) < 15:
        digits += str(random.randint(0, 9))
    digits = digits[:15]

    # Luhn 체크디짓 계산
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 0:  # 15자리 기준 짝수 인덱스
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - (total % 10)) % 10
    digits += str(check)
    formatted = f"{digits[:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:16]}"
    return formatted, digits


def _random_passport() -> Tuple[str, str]:
    """유효한 여권번호 생성"""
    letter = random.choice(["M", "S", "R", "G"])
    num = random.randint(1000000, 9999999)
    text = f"{letter}{num}"
    return text, text


def _random_driver_license() -> Tuple[str, str]:
    """지역코드와 체크디짓이 유효한 운전면허번호 생성"""
    region = random.choice(list(DRIVER_LICENSE_REGIONS.keys()))
    year = random.randint(0, 99)
    serial = random.randint(1, 999999)

    first_10_str = f"{region}{year:02d}{serial:06d}"
    first_10 = int(first_10_str)
    check = first_10 % 97
    digits = f"{first_10_str}{check:02d}"
    formatted = f"{digits[:2]}-{digits[2:4]}-{digits[4:10]}-{digits[10:12]}"
    return formatted, digits


def _random_bank_account() -> Tuple[str, str]:
    """은행별 형식에 맞는 계좌번호 생성"""
    patterns = [
        (3, 3, 6),      # 신한/KB국민
        (4, 2, 7),      # 카카오뱅크
        (4, 3, 6),      # 우리은행
        (3, 2, 6, 2),   # NH농협
        (3, 6, 5),      # 하나은행
    ]
    pattern = random.choice(patterns)
    parts = []
    for n in pattern:
        lo = 10 ** (n - 1) if n > 1 else 1
        hi = 10 ** n - 1
        parts.append(str(random.randint(lo, hi)))
    # 앞 4자리가 연도처럼 보이지 않게
    digits = "".join(parts)
    if 2000 <= int(digits[:4]) <= 2099:
        parts[0] = str(random.randint(100, 199))
        digits = "".join(parts)
    formatted = "-".join(parts)
    return formatted, digits


PII_GENERATORS = {
    "RRN": _random_rrn,
    "PHONE": _random_phone,
    "CRN": _random_crn,
    "CREDIT_CARD": _random_credit_card,
    "PASSPORT": _random_passport,
    "DRIVER_LICENSE": _random_driver_license,
    "BANK_ACCOUNT": _random_bank_account,
}


# === 구분자 변형 (Level 2) ===

SEPARATORS = [" ", "  ", " - ", " _ ", "  -  ", "--", "__", " -_ ", "- ", " -"]


def _apply_level2_separator(formatted: str) -> str:
    sep = random.choice(SEPARATORS)
    return formatted.replace("-", sep)


def _apply_level2_space_in_group(formatted: str) -> str:
    result = []
    for ch in formatted:
        result.append(ch)
        if ch.isdigit() and random.random() < 0.2:
            result.append(" ")
    return "".join(result)


# === 대체 문자 변형 (Level 3) ===

def _apply_level3_substitution(formatted: str, sub_ratio: float = 0.3) -> Tuple[str, str]:
    result = []
    normalized = []
    for ch in formatted:
        if ch.isdigit() and random.random() < sub_ratio:
            alternatives = DIGIT_ALTERNATIVES.get(ch, [])
            simple_alts = [a for a in alternatives if len(a) <= 3]
            if simple_alts:
                alt = random.choice(simple_alts)
                result.append(alt)
                normalized.append(ch)
                continue
        result.append(ch)
        normalized.append(ch)
    return "".join(result), "".join(normalized)


# === 문맥 문장 템플릿 ===

CONTEXT_TEMPLATES = {
    "RRN": [
        "주민등록번호는 {pii} 입니다.",
        "본인확인을 위해 {pii}를 입력해주세요.",
        "주민번호 {pii} 으로 조회됩니다.",
        "생년월일/주민번호: {pii}",
        "{pii} 이 맞는지 확인해주세요.",
    ],
    "PHONE": [
        "연락처: {pii}",
        "전화번호는 {pii} 입니다.",
        "핸드폰 {pii}로 연락주세요.",
        "HP: {pii}",
        "제 번호는 {pii}에요.",
        "문의전화 {pii}",
    ],
    "CRN": [
        "사업자등록번호: {pii}",
        "사업자번호 {pii}로 조회해주세요.",
        "등록번호는 {pii} 입니다.",
    ],
    "CREDIT_CARD": [
        "카드번호 {pii}",
        "결제카드: {pii}",
        "신용카드 {pii}로 결제합니다.",
    ],
    "PASSPORT": [
        "여권번호: {pii}",
        "PASSPORT NO. {pii}",
        "여권 {pii} 확인 부탁드립니다.",
    ],
    "DRIVER_LICENSE": [
        "운전면허번호 {pii}",
        "면허번호: {pii}",
        "운전면허 {pii} 입니다.",
    ],
    "BANK_ACCOUNT": [
        "계좌번호: {pii}",
        "입금계좌 {pii}",
        "{pii}로 이체해주세요.",
        "계좌: {pii} (국민은행)",
    ],
    "EMAIL": [
        "이메일: {pii}",
        "메일 주소는 {pii} 입니다.",
        "{pii}로 보내주세요.",
        "E-mail: {pii}",
    ],
}

# === 비PII 문장 (Negative 샘플) - 확대 ===

NON_PII_TEXTS = [
    "오늘 주문번호는 2024-0312-4567 입니다.",
    "모델명: SM-G998N, 가격 1,350,000원",
    "재고수량 1234개, 배송비 3,000원",
    "서울특별시 강남구 테헤란로 152",
    "2024년 3월 15일 오후 2시 30분",
    "총 결제금액: 89,000원 (부가세 포함)",
    "회의실 A-302, 참석자 15명",
    "프로젝트 코드: PRJ-2024-0089",
    "버전 3.14.159, 빌드 번호 20240315",
    "IP 주소: 192.168.0.1",
    "좌석번호 A-15, 입장시간 14:30",
    "학번: 2020-12345",
    "주문 수량: 500박스 (1박스당 24개입)",
    "면적: 84.56㎡ (25.5평)",
    "위도 37.5665, 경도 126.9780",
    "온도 23.5도, 습도 65%",
    "KTX 열차번호 101, 출발 08:00",
    "ISBN 978-89-6848-123-4",
    "처리속도: 150,000 TPS",
    "고객번호: C-2024-00123",
    "보안등급 3등급, 접근권한 레벨 2",
    "문서번호 DOC-2024-03-0456",
    "계약기간: 2024.01.01 ~ 2024.12.31",
    "매출액 123,456,789원 (전년 대비 15% 증가)",
    "서버 포트: 8080, 타임아웃: 30초",
    "직원수 250명, 평균 연봉 4,500만원",
    "2024년 1분기 실적 보고서",
    "제품코드 ABC-12345-XY",
    "할인율 15%, 적립 포인트 1,500P",
    "배터리 용량 5000mAh, 충전시간 90분",
    "층수: 지상 30층, 지하 5층",
    "경기도 성남시 분당구 판교역로 235",
    "운영시간: 09:00 ~ 18:00 (점심 12:00-13:00)",
    "참조번호 REF-20240315-001",
    "해상도 3840x2160, 주사율 120Hz",
    "용량: 512GB SSD + 1TB HDD",
    "인증번호: KC-R-ABC-12345",
    "항공편 KE901, 탑승구 42번",
    "2024 수능 점수 280점 (100분위)",
    "마감일: D-7 (3월 22일)",
    # 유사 형식이지만 비PII
    "우편번호 06236",
    "택배 송장번호 1234-5678-9012",
    "관리번호 20240315-001234",
    "예약번호: R-2024-03-15-0042",
    "사원번호 2024-0312",
    "차량번호 12가 3456",
    "호실번호 101-1201",
    "도서번호 D-2024-00567",
    # 운전면허 유사 (지역코드 범위 밖)
    "코드번호 20-24-123456-78",
    "식별코드 99-00-000001-01",
    # 주민번호 유사 (월/일 범위 밖)
    "제품번호 001300-1234567",
    "시리얼 991332-2345678",
]


def generate_single_pii(pii_type: str, level: int) -> dict:
    """단일 PII 데이터 항목 생성"""
    if pii_type == "EMAIL":
        pii_value = _random_email()
        formatted = pii_value
    else:
        gen = PII_GENERATORS[pii_type]
        formatted, digits = gen()
        pii_value = formatted

    evasion_technique = None
    evasion_level = 1

    if level >= 2 and pii_type != "EMAIL" and random.random() < 0.5:
        formatted = _apply_level2_separator(formatted)
        if random.random() < 0.3:
            formatted = _apply_level2_space_in_group(formatted)
        evasion_level = 2
        evasion_technique = "구분자 변형"

    if level >= 3 and pii_type != "EMAIL" and random.random() < 0.4:
        sub_ratio = random.uniform(0.2, 0.7)
        formatted, _ = _apply_level3_substitution(formatted, sub_ratio)
        evasion_level = 3
        evasion_technique = f"대체 문자 ({int(sub_ratio*100)}% 치환)"

    templates = CONTEXT_TEMPLATES.get(pii_type, ["{pii}"])
    template = random.choice(templates)
    text = template.format(pii=formatted)

    return {
        "text": text,
        "has_pii": True,
        "pii_type": pii_type,
        "pii_value": pii_value,
        "evasion_level": evasion_level,
        "evasion_technique": evasion_technique,
    }


def generate_non_pii() -> dict:
    text = random.choice(NON_PII_TEXTS)
    if random.random() < 0.3:
        text = text + " " + random.choice(["입니다.", "확인바랍니다.", "참고하세요."])
    return {
        "text": text,
        "has_pii": False,
        "pii_type": None,
        "pii_value": None,
        "evasion_level": None,
        "evasion_technique": None,
    }


def generate_batch(count: int, level: int = 3, pii_ratio: float = 0.7) -> List[dict]:
    data = []
    pii_count = int(count * pii_ratio)
    non_pii_count = count - pii_count

    pii_types = list(PII_GENERATORS.keys()) + ["EMAIL"]

    for _ in range(pii_count):
        pii_type = random.choice(pii_types)
        data.append(generate_single_pii(pii_type, level))

    for _ in range(non_pii_count):
        data.append(generate_non_pii())

    random.shuffle(data)
    return data


def generate_and_save(count: int, level: int = 3) -> Tuple[List[dict], Path]:
    data = generate_batch(count, level)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = DATA_DIR / f"synthetic_{timestamp}_{len(data)}.jsonl"
    with open(filepath, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return data, filepath
