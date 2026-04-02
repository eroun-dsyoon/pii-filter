"""
PII 필터링 엔진
Level 1: 기본 형식
Level 2: 다양한 구분자
Level 3: 대체 문자
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Tuple

from .char_map import CHAR_TO_DIGIT, normalize_text
from .patterns import LEVEL1_PATTERNS


@dataclass
class PIIEntity:
    type: str
    entity: str
    start: int
    end: int
    normalized: Optional[str] = None
    level: int = 1

    def to_dict(self) -> dict:
        d = {"type": self.type, "entity": self.entity, "start": self.start, "end": self.end}
        if self.normalized and self.normalized != self.entity:
            d["normalized"] = self.normalized
        d["level"] = self.level
        return d


# === 날짜/비PII 패턴 (오탐 방지) ===

# 날짜 형식: YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD
_DATE_PATTERN = re.compile(
    r'\b(?:19|20)\d{2}[\-./](?:0[1-9]|1[0-2])[\-./](?:0[1-9]|[12]\d|3[01])\b'
)

# ISBN: 978-XX-XXXX-XXX-X or 3-2-4~5-3-1
_ISBN_PATTERN = re.compile(
    r'\b97[89][\-]\d{1,5}[\-]\d{1,7}[\-]\d{1,6}[\-]\d\b'
)

# 영문 접두사가 붙은 코드: DOC-XXXX, ORD-XXXX, REF-XXXX 등
_CODE_PREFIX_PATTERN = re.compile(
    r'[A-Za-z]{2,}[\-]\d{2,}'
)

# IP 주소
_IP_PATTERN = re.compile(
    r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
)


def _is_date_like(text: str) -> bool:
    """텍스트가 날짜 형식인지 확인"""
    digits = ''.join(c for c in text if c.isdigit())
    if len(digits) < 6 or len(digits) > 8:
        return False
    # 첫 4자리가 연도 범위인지
    if len(digits) >= 4:
        year_candidate = int(digits[:4])
        if 1900 <= year_candidate <= 2099:
            return True
    return False


# === Level 2: 구분자 패턴 빌더 ===

_SEP_BETWEEN = r'[\-_.\s]+'
_SEP_WITHIN = r'\s*'


def _flexible_digits(n: int) -> str:
    """n자리 숫자, 사이에 공백 무제한 허용"""
    if n == 1:
        return r'\d'
    return r'\d' + (r'(?:\s*\d)' * (n - 1))


def _build_level2_pattern(groups: list) -> str:
    parts = []
    for i, (min_d, max_d) in enumerate(groups):
        if min_d == max_d:
            parts.append(_flexible_digits(min_d))
        else:
            options = []
            for n in range(max_d, min_d - 1, -1):
                options.append(_flexible_digits(n))
            parts.append('(?:' + '|'.join(options) + ')')
    return parts[0] + ''.join(f'(?:{_SEP_BETWEEN})' + p for p in parts[1:])


# Level 2 패턴 정의
LEVEL2_PATTERNS = []

# 주민등록번호: 6-7
_rrn_l2 = _build_level2_pattern([(6, 6), (7, 7)])
LEVEL2_PATTERNS.append(("RRN", re.compile(_rrn_l2)))

# 사업자등록번호: 3-2-5
_crn_l2 = _build_level2_pattern([(3, 3), (2, 2), (5, 5)])
LEVEL2_PATTERNS.append(("CRN", re.compile(_crn_l2)))

# 전화번호: 010/011/016/017/018/019-3~4-4 또는 02-3~4-4
_phone_l2_mobile = _build_level2_pattern([(3, 3), (3, 4), (4, 4)])
_phone_l2_seoul = _build_level2_pattern([(2, 2), (3, 4), (4, 4)])
LEVEL2_PATTERNS.append(("PHONE", re.compile(f'(?:{_phone_l2_mobile}|{_phone_l2_seoul})')))

# 여권번호: 영문1-2 + 숫자7
LEVEL2_PATTERNS.append(("PASSPORT", re.compile(r'[A-Z]{1,2}' + r'(?:\s*)' + _flexible_digits(7))))

# 계좌번호: 은행별 실제 형식 + 넓은 패턴 (10~14자리 총합 검증으로 오탐 방지)
_bank_patterns = [
    _build_level2_pattern([(3, 3), (3, 3), (6, 6)]),          # 국민/신한 3-3-6
    _build_level2_pattern([(3, 3), (4, 4), (6, 7)]),          # 신한/기업 3-4-6~7
    _build_level2_pattern([(4, 4), (3, 3), (6, 6)]),          # 우리 4-3-6
    _build_level2_pattern([(3, 3), (6, 6), (5, 5)]),          # 하나 3-6-5
    _build_level2_pattern([(3, 3), (2, 2), (6, 6), (2, 2)]),  # 농협 3-2-6-2
    _build_level2_pattern([(3, 4), (2, 4), (4, 6)]),          # 기타 유연 패턴
    _build_level2_pattern([(3, 6), (2, 6), (2, 6)]),          # 넓은 패턴 (validator로 검증)
]
_bank_l2 = '|'.join(f'(?:{p})' for p in _bank_patterns)
LEVEL2_PATTERNS.append(("BANK_ACCOUNT", re.compile(_bank_l2)))

# 신용카드: 4-4-4-4
_cc_l2 = _build_level2_pattern([(4, 4), (4, 4), (4, 4), (4, 4)])
LEVEL2_PATTERNS.append(("CREDIT_CARD", re.compile(_cc_l2)))

# 운전면허: 2-2-6-2
_dl_l2 = _build_level2_pattern([(2, 2), (2, 2), (6, 6), (2, 2)])
LEVEL2_PATTERNS.append(("DRIVER_LICENSE", re.compile(_dl_l2)))

# 이메일
LEVEL2_PATTERNS.append(("EMAIL", re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')))


def _strip_digits(text: str) -> str:
    """텍스트에서 숫자만 추출"""
    return ''.join(c for c in text if c.isdigit())


def _validate_rrn(digits: str) -> bool:
    if len(digits) != 13:
        return False
    month = int(digits[2:4])
    day = int(digits[4:6])
    gender = int(digits[6])
    if month < 1 or month > 12:
        return False
    if day < 1 or day > 31:
        return False
    if gender < 1 or gender > 4:
        return False
    return True


def _validate_phone(digits: str) -> bool:
    if len(digits) < 9 or len(digits) > 11:
        return False
    # 휴대폰: 010/011/016/017/018/019
    if digits.startswith('01'):
        return digits[:3] in ('010', '011', '016', '017', '018', '019')
    # 서울 지역번호: 02 (9~10자리)
    if digits.startswith('02'):
        return 9 <= len(digits) <= 10
    # 기타 지역번호: 031~064 (10~11자리)
    if digits.startswith('0') and digits[1] in '3456':
        area = digits[:3]
        area_num = int(area)
        if 31 <= area_num <= 64:
            return 10 <= len(digits) <= 11
    return False


def _validate_credit_card(digits: str) -> bool:
    if len(digits) != 16:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _validate_bank_account(digits: str) -> bool:
    """계좌번호 유효성 검증 (Judge 피드백: 자릿수 범위 제한)"""
    length = len(digits)
    # 한국 계좌번호는 일반적으로 10~14자리
    if length < 10 or length > 14:
        return False
    # 앞 4자리가 연도(2000~2099)로 시작하면 날짜/주문번호일 가능성 높음
    if length >= 4:
        first4 = int(digits[:4])
        if 2000 <= first4 <= 2099:
            return False
    return True


VALIDATORS = {
    "RRN": _validate_rrn,
    "PHONE": _validate_phone,
    "CREDIT_CARD": _validate_credit_card,
    "BANK_ACCOUNT": _validate_bank_account,
}


class PIIFilterEngine:
    """PII 필터링 엔진"""

    def __init__(self, level: int = 3):
        self.level = level

    def detect(self, text: str) -> list:
        """텍스트에서 PII를 검출"""
        entities = []

        # Level 1: 기본 형식
        entities.extend(self._detect_level1(text))

        if self.level >= 2:
            entities.extend(self._detect_level2(text))

        if self.level >= 3:
            entities.extend(self._detect_level3(text))

        # 중복 제거
        entities = self._deduplicate(entities)

        return entities

    def _is_excluded_context(self, text: str, start: int, end: int) -> bool:
        """오탐 방지: 특정 문맥에서는 PII로 판단하지 않음"""
        # 매칭된 부분의 앞뒤 문맥 확인
        context_before = text[max(0, start - 20):start]
        matched = text[start:end]

        # 영문 접두사가 붙은 코드 (DOC-2024-03-0456 등)
        if _CODE_PREFIX_PATTERN.search(text[max(0, start - 10):end]):
            return True

        # 날짜 형식 제외
        if _DATE_PATTERN.search(text[max(0, start - 5):end + 5]):
            return True

        # ISBN 형식 제외
        if _ISBN_PATTERN.search(text[max(0, start - 10):end + 5]):
            return True

        # IP 주소 제외
        if _IP_PATTERN.search(text[max(0, start - 5):end + 5]):
            return True

        return False

    def _detect_level1(self, text: str) -> list:
        results = []
        for pii_type, pattern in LEVEL1_PATTERNS:
            for match in pattern.finditer(text):
                entity_text = match.group()
                digits = _strip_digits(entity_text)

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                if self._is_excluded_context(text, match.start(), match.end()):
                    continue

                results.append(PIIEntity(
                    type=pii_type,
                    entity=entity_text,
                    start=match.start(),
                    end=match.end(),
                    level=1,
                ))
        return results

    def _detect_level2(self, text: str) -> list:
        results = []
        for pii_type, pattern in LEVEL2_PATTERNS:
            for match in pattern.finditer(text):
                entity_text = match.group()
                digits = _strip_digits(entity_text)

                if not self._validate_level2_separators(entity_text, pii_type):
                    continue

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                # 시작/끝 구분자 제거
                stripped = entity_text.strip('-_. \t\n\r')
                if stripped != entity_text:
                    offset = entity_text.index(stripped[0]) if stripped else 0
                    start = match.start() + offset
                    end = start + len(stripped)
                else:
                    start = match.start()
                    end = match.end()

                if self._is_excluded_context(text, start, end):
                    continue

                results.append(PIIEntity(
                    type=pii_type,
                    entity=entity_text.strip(),
                    start=start,
                    end=end,
                    level=2,
                ))
        return results

    def _validate_level2_separators(self, text: str, pii_type: str) -> bool:
        if pii_type == "EMAIL":
            return True

        stripped = text.strip('-_. \t\n\r')
        if not stripped:
            return False

        digit_groups = re.findall(r'\d+', stripped)
        if len(digit_groups) > 4 and all(len(g) == 1 for g in digit_groups):
            return False

        return True

    def _detect_level3(self, text: str) -> list:
        """Level 3: 대체 문자 포함 패턴"""
        normalized, mappings = normalize_text(text)

        if normalized == text:
            return []

        results = []

        all_patterns = LEVEL1_PATTERNS + LEVEL2_PATTERNS
        for pii_type, pattern in all_patterns:
            for match in pattern.finditer(normalized):
                entity_norm = match.group()
                digits = _strip_digits(entity_norm)

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                norm_start = match.start()
                norm_end = match.end()
                orig_start, orig_end = self._map_to_original(
                    norm_start, norm_end, text, normalized, mappings
                )

                original_entity = text[orig_start:orig_end]

                if original_entity == entity_norm:
                    continue

                if self._is_excluded_context(text, orig_start, orig_end):
                    continue

                results.append(PIIEntity(
                    type=pii_type,
                    entity=original_entity,
                    start=orig_start,
                    end=orig_end,
                    normalized=entity_norm,
                    level=3,
                ))

        return results

    def _map_to_original(
        self,
        norm_start: int,
        norm_end: int,
        original: str,
        normalized: str,
        mappings: list,
    ) -> tuple:
        """정규화된 텍스트의 위치를 원본 텍스트 위치로 매핑"""
        mapping_dict = {}
        for orig_p, norm_p, orig_char, digit in mappings:
            mapping_dict[norm_p] = (orig_p, len(orig_char))

        o = 0
        n = 0
        orig_start = 0
        orig_end = len(original)
        start_found = False

        while o < len(original) and n < len(normalized):
            if n == norm_start and not start_found:
                orig_start = o
                start_found = True
            if n == norm_end:
                orig_end = o
                return orig_start, orig_end

            if n in mapping_dict:
                orig_p, char_len = mapping_dict[n]
                o = orig_p + char_len
                n += 1
            else:
                o += 1
                n += 1

        if n == norm_end:
            orig_end = o
        if not start_found:
            orig_start = o

        return orig_start, orig_end

    def _deduplicate(self, entities: list) -> list:
        if not entities:
            return []

        entities.sort(key=lambda e: (e.start, -e.end, -e.level))

        result = []
        for entity in entities:
            overlapping = False
            for existing in result:
                # 같은 타입이거나 범위가 완전히 겹치면 중복
                if entity.start < existing.end and entity.end > existing.start:
                    if entity.type == existing.type:
                        overlapping = True
                        break
                    # 다른 타입이라도 범위가 80% 이상 겹치면 더 구체적인 타입 우선
                    overlap = min(entity.end, existing.end) - max(entity.start, existing.start)
                    entity_len = entity.end - entity.start
                    if entity_len > 0 and overlap / entity_len > 0.8:
                        overlapping = True
                        break
            if not overlapping:
                result.append(entity)

        return result


# 싱글톤
_default_engine = None


def get_engine(level: int = 3) -> PIIFilterEngine:
    global _default_engine
    if _default_engine is None or _default_engine.level != level:
        _default_engine = PIIFilterEngine(level=level)
    return _default_engine


def detect_pii(text: str, level: int = 3) -> list:
    """텍스트에서 PII를 검출하여 dict 리스트로 반환"""
    engine = get_engine(level)
    entities = engine.detect(text)
    return [e.to_dict() for e in entities]
