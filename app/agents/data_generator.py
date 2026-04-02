"""
알고리즘 기반 합성 데이터 생성기
- Level 1/2/3 PII 변형을 프로그래밍 방식으로 대량 생성
- LLM 호출 없이 빠르게 동작
"""
from __future__ import annotations

import random
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional

from ..core.char_map import DIGIT_ALTERNATIVES
from ..config import DATA_DIR

# === PII 값 생성기 ===

def _random_rrn() -> Tuple[str, str]:
    """유효한 주민등록번호 생성. Returns: (포맷된 값, 숫자만)"""
    year = random.randint(70, 99)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    gender = random.choice([1, 2])
    rest = random.randint(100000, 999999)
    digits = f"{year:02d}{month:02d}{day:02d}{gender}{rest:06d}"
    formatted = f"{digits[:6]}-{digits[6:]}"
    return formatted, digits


def _random_phone() -> Tuple[str, str]:
    """유효한 전화번호 생성"""
    prefix = random.choice(["010", "011", "016", "017", "018", "019"])
    mid = random.randint(1000, 9999)
    last = random.randint(1000, 9999)
    digits = f"{prefix}{mid}{last}"
    formatted = f"{prefix}-{mid}-{last}"
    return formatted, digits


def _random_crn() -> Tuple[str, str]:
    """사업자등록번호 생성"""
    a = random.randint(100, 999)
    b = random.randint(10, 99)
    c = random.randint(10000, 99999)
    digits = f"{a}{b:02d}{c:05d}"
    formatted = f"{a}-{b:02d}-{c:05d}"
    return formatted, digits


def _random_email() -> str:
    """이메일 생성"""
    names = ["kim", "lee", "park", "choi", "jung", "kang", "cho", "yoon", "jang", "lim",
             "user", "admin", "test", "hello", "info", "contact", "support"]
    domains = ["gmail.com", "naver.com", "daum.net", "kakao.com", "hanmail.net", "outlook.com"]
    name = random.choice(names) + str(random.randint(1, 999))
    domain = random.choice(domains)
    return f"{name}@{domain}"


def _random_credit_card() -> Tuple[str, str]:
    """신용카드번호 생성 (Luhn 유효)"""
    # 카드 프리픽스
    prefix = random.choice(["4", "5", "3"])
    digits = prefix
    for _ in range(14):
        digits += str(random.randint(0, 9))
    # Luhn 체크 디짓 계산
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - (total % 10)) % 10
    digits += str(check)
    formatted = f"{digits[:4]}-{digits[4:8]}-{digits[8:12]}-{digits[12:16]}"
    return formatted, digits


def _random_passport() -> Tuple[str, str]:
    """여권번호 생성"""
    letter = random.choice(["M", "S", "R", "G"])
    num = random.randint(1000000, 9999999)
    return f"{letter}{num}", f"{letter}{num}"


def _random_driver_license() -> Tuple[str, str]:
    """운전면허번호 생성"""
    region = random.randint(11, 28)
    seq1 = random.randint(10, 99)
    seq2 = random.randint(100000, 999999)
    seq3 = random.randint(10, 99)
    digits = f"{region}{seq1:02d}{seq2:06d}{seq3:02d}"
    formatted = f"{region}-{seq1:02d}-{seq2:06d}-{seq3:02d}"
    return formatted, digits


def _random_bank_account() -> Tuple[str, str]:
    """계좌번호 생성"""
    patterns = [
        (3, 3, 6),    # 국민
        (4, 2, 6, 2), # 신한
        (3, 4, 4, 2), # 우리
        (3, 6, 2, 3), # 하나
    ]
    pattern = random.choice(patterns)
    parts = [str(random.randint(10**(n-1), 10**n - 1)) for n in pattern]
    formatted = "-".join(parts)
    digits = "".join(parts)
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
    """하이픈을 다양한 구분자로 치환"""
    sep = random.choice(SEPARATORS)
    return formatted.replace("-", sep)


def _apply_level2_space_in_group(formatted: str) -> str:
    """숫자 그룹 내에 랜덤 공백 삽입"""
    result = []
    for ch in formatted:
        result.append(ch)
        if ch.isdigit() and random.random() < 0.2:
            result.append(" ")
    return "".join(result)


# === 대체 문자 변형 (Level 3) ===

def _apply_level3_substitution(formatted: str, sub_ratio: float = 0.3) -> Tuple[str, str]:
    """
    숫자를 대체 문자로 치환.
    sub_ratio: 치환 비율 (0.0~1.0)
    Returns: (변형된 텍스트, 정규화된 값)
    """
    result = []
    normalized = []
    for ch in formatted:
        if ch.isdigit() and random.random() < sub_ratio:
            alternatives = DIGIT_ALTERNATIVES.get(ch, [])
            if alternatives:
                # 이모지 키캡은 제외 (복잡성)
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

# === 비PII 문장 (Negative 샘플) ===

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
    """비PII 데이터 항목 생성"""
    text = random.choice(NON_PII_TEXTS)
    # 약간의 변형 추가
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
    """
    합성 데이터 배치 생성
    count: 생성할 총 개수
    level: PII 우회 레벨 (1-3)
    pii_ratio: PII 포함 비율
    """
    data = []
    pii_count = int(count * pii_ratio)
    non_pii_count = count - pii_count

    pii_types = list(PII_GENERATORS.keys()) + ["EMAIL"]

    for _ in range(pii_count):
        pii_type = random.choice(pii_types)
        item = generate_single_pii(pii_type, level)
        data.append(item)

    for _ in range(non_pii_count):
        data.append(generate_non_pii())

    random.shuffle(data)
    return data


def generate_and_save(count: int, level: int = 3) -> Tuple[List[dict], Path]:
    """합성 데이터 생성 후 파일 저장"""
    data = generate_batch(count, level)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = DATA_DIR / f"synthetic_{timestamp}_{len(data)}.jsonl"

    with open(filepath, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return data, filepath
