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

from .char_map import CHAR_TO_DIGIT, normalize_text
from .patterns import LEVEL1_PATTERNS


@dataclass
class PIIEntity:
    type: str
    entity: str
    start: int
    end: int
    normalized: str | None = None
    level: int = 1

    def to_dict(self) -> dict:
        d = {"type": self.type, "entity": self.entity, "start": self.start, "end": self.end}
        if self.normalized and self.normalized != self.entity:
            d["normalized"] = self.normalized
        d["level"] = self.level
        return d


# === Level 2: 구분자 패턴 빌더 ===

# 허용 구분자: -, _, ., \s
# 그룹 내에서는 공백만 허용, 그룹 간에는 구분자+공백 조합 허용
_SEP_BETWEEN = r'[\-_.\s]+'  # 그룹 간 구분자
_SEP_WITHIN = r'\s*'  # 그룹 내 공백

def _digits_pattern(n: int, within_group: bool = True) -> str:
    """n자리 숫자 패턴 생성. 그룹 내에서는 숫자 사이에 공백 허용."""
    if n == 1:
        return r'\d'
    if within_group:
        return r'\d' + (r'(?:\s*\d)' * (n - 1))
    return r'\d{' + str(n) + '}'


def _flexible_digits(n: int) -> str:
    """n자리 숫자, 사이에 공백 무제한 허용"""
    if n == 1:
        return r'\d'
    return r'\d' + (r'(?:\s*\d)' * (n - 1))


def _build_level2_pattern(groups: list[tuple[int, int]], first_constraints: str = r'\d') -> str:
    """
    숫자 그룹 리스트를 받아 Level 2 패턴을 생성.
    groups: [(min_digits, max_digits), ...]
    """
    parts = []
    for i, (min_d, max_d) in enumerate(groups):
        if min_d == max_d:
            parts.append(_flexible_digits(min_d))
        else:
            # 가변 길이: min~max 자리
            options = []
            for n in range(max_d, min_d - 1, -1):
                options.append(_flexible_digits(n))
            parts.append('(?:' + '|'.join(options) + ')')

    # 그룹 간 구분자로 연결
    return parts[0] + ''.join(f'(?:{_SEP_BETWEEN})' + p for p in parts[1:])


# Level 2 패턴 정의
LEVEL2_PATTERNS: list[tuple[str, re.Pattern]] = []

# 주민등록번호: 6-7
_rrn_l2 = _build_level2_pattern([(6, 6), (7, 7)])
# 앞자리 제약: 생년월일 패턴은 정규화 후 검증
LEVEL2_PATTERNS.append(("RRN", re.compile(_rrn_l2)))

# 사업자등록번호: 3-2-5
_crn_l2 = _build_level2_pattern([(3, 3), (2, 2), (5, 5)])
LEVEL2_PATTERNS.append(("CRN", re.compile(_crn_l2)))

# 전화번호: 3(4)-3(4)-4
_phone_l2_mobile = _build_level2_pattern([(3, 3), (3, 4), (4, 4)])
_phone_l2_seoul = _build_level2_pattern([(2, 2), (3, 4), (4, 4)])
_phone_l2_local = _build_level2_pattern([(3, 3), (3, 4), (4, 4)])
LEVEL2_PATTERNS.append(("PHONE", re.compile(f'(?:{_phone_l2_mobile}|{_phone_l2_seoul}|{_phone_l2_local})')))

# 여권번호: 영문1-2 + 숫자7
LEVEL2_PATTERNS.append(("PASSPORT", re.compile(r'[A-Z]{1,2}' + r'(?:\s*)' + _flexible_digits(7))))

# 계좌번호: 3~6 - 2~6 - 2~6 (- 1~3)
_bank_l2 = _build_level2_pattern([(3, 6), (2, 6), (2, 6)])
LEVEL2_PATTERNS.append(("BANK_ACCOUNT", re.compile(_bank_l2)))

# 신용카드: 4-4-4-4
_cc_l2 = _build_level2_pattern([(4, 4), (4, 4), (4, 4), (4, 4)])
LEVEL2_PATTERNS.append(("CREDIT_CARD", re.compile(_cc_l2)))

# 운전면허: 2-2-6-2
_dl_l2 = _build_level2_pattern([(2, 2), (2, 2), (6, 6), (2, 2)])
LEVEL2_PATTERNS.append(("DRIVER_LICENSE", re.compile(_dl_l2)))

# 이메일은 Level 2에서도 동일
LEVEL2_PATTERNS.append(("EMAIL", re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')))


def _strip_digits(text: str) -> str:
    """텍스트에서 숫자만 추출"""
    return ''.join(c for c in text if c.isdigit())


def _validate_rrn(digits: str) -> bool:
    """주민등록번호 유효성 검증"""
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
    """전화번호 유효성 검증"""
    if len(digits) < 9 or len(digits) > 11:
        return False
    if digits.startswith('01'):
        return digits[:3] in ('010', '011', '016', '017', '018', '019')
    if digits.startswith('02'):
        return True
    if digits[:2] in ('03', '04', '05', '06'):
        return True
    return False


def _validate_credit_card(digits: str) -> bool:
    """신용카드 Luhn 알고리즘 검증"""
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


VALIDATORS = {
    "RRN": _validate_rrn,
    "PHONE": _validate_phone,
    "CREDIT_CARD": _validate_credit_card,
}


class PIIFilterEngine:
    """PII 필터링 엔진"""

    def __init__(self, level: int = 3):
        self.level = level
        # Level 2 구분자 제외 규칙에 쓰이는 패턴
        self._single_digit_sep = re.compile(r'^\d([\-_.])\d([\-_.])\d')

    def detect(self, text: str) -> list[PIIEntity]:
        """텍스트에서 PII를 검출"""
        entities: list[PIIEntity] = []

        # Level 1: 기본 형식
        entities.extend(self._detect_level1(text))

        if self.level >= 2:
            entities.extend(self._detect_level2(text))

        if self.level >= 3:
            entities.extend(self._detect_level3(text))

        # 중복 제거 (같은 위치의 같은 타입)
        entities = self._deduplicate(entities)

        return entities

    def _detect_level1(self, text: str) -> list[PIIEntity]:
        """Level 1: 기본 형식 패턴 매칭"""
        results = []
        for pii_type, pattern in LEVEL1_PATTERNS:
            for match in pattern.finditer(text):
                entity_text = match.group()
                digits = _strip_digits(entity_text)

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                results.append(PIIEntity(
                    type=pii_type,
                    entity=entity_text,
                    start=match.start(),
                    end=match.end(),
                    level=1,
                ))
        return results

    def _detect_level2(self, text: str) -> list[PIIEntity]:
        """Level 2: 다양한 구분자 패턴"""
        results = []
        for pii_type, pattern in LEVEL2_PATTERNS:
            for match in pattern.finditer(text):
                entity_text = match.group()
                digits = _strip_digits(entity_text)

                # 구분자 제외 규칙 검증
                if not self._validate_level2_separators(entity_text, pii_type):
                    continue

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                # 시작/끝 구분자 제외
                stripped = entity_text.strip('-_.  \t\n\r')
                if stripped != entity_text:
                    offset = entity_text.index(stripped[0]) if stripped else 0
                    start = match.start() + offset
                    end = start + len(stripped)
                else:
                    start = match.start()
                    end = match.end()

                results.append(PIIEntity(
                    type=pii_type,
                    entity=entity_text.strip(),
                    start=start,
                    end=end,
                    level=2,
                ))
        return results

    def _validate_level2_separators(self, text: str, pii_type: str) -> bool:
        """Level 2 구분자 규칙 검증"""
        # 이메일은 구분자 검증 불필요
        if pii_type == "EMAIL":
            return True

        # 시작/끝 구분자 제외
        stripped = text.strip('-_. \t\n\r')
        if not stripped:
            return False

        # 각 숫자 사이에 구분자가 있는 경우 제외 (예: 0-1-0-1-2-3-4-5-6-7-8)
        chars = [c for c in stripped if c.isdigit() or c in '-_. \t\n\r']
        digit_count = sum(1 for c in stripped if c.isdigit())
        sep_segments = [s for s in re.split(r'\d+', stripped) if s.strip('-_. \t\n\r') == '' and s]

        # 모든 숫자가 단일 자릿수이고 각각 구분자로 분리된 경우 제외
        digit_groups = re.findall(r'\d+', stripped)
        if len(digit_groups) > 4 and all(len(g) == 1 for g in digit_groups):
            return False

        return True

    def _detect_level3(self, text: str) -> list[PIIEntity]:
        """Level 3: 대체 문자 포함 패턴"""
        # 텍스트를 정규화한 후 Level 1, 2 패턴으로 다시 검색
        normalized, mappings = normalize_text(text)

        if normalized == text:
            return []  # 대체 문자 없음

        results = []

        # 정규화된 텍스트에서 Level 1, 2 패턴 매칭
        all_patterns = LEVEL1_PATTERNS + LEVEL2_PATTERNS
        for pii_type, pattern in all_patterns:
            for match in pattern.finditer(normalized):
                entity_norm = match.group()
                digits = _strip_digits(entity_norm)

                validator = VALIDATORS.get(pii_type)
                if validator and not validator(digits):
                    continue

                # 원본 텍스트에서의 위치 계산
                norm_start = match.start()
                norm_end = match.end()
                orig_start, orig_end = self._map_to_original(norm_start, norm_end, text, normalized, mappings)

                original_entity = text[orig_start:orig_end]

                # 원본과 정규화된 값이 동일하면 이미 Level 1/2에서 검출됨
                if original_entity == entity_norm:
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
        mappings: list[tuple[int, int, str, str]],
    ) -> tuple[int, int]:
        """정규화된 텍스트의 위치를 원본 텍스트 위치로 매핑"""
        # 매핑 정보를 활용하여 원본 위치 계산
        # 간단한 접근: 정규화 과정에서의 offset 추적
        orig_pos = 0
        norm_pos = 0
        orig_start = 0
        orig_end = len(original)

        mapping_dict = {}
        for orig_p, norm_p, orig_char, digit in mappings:
            mapping_dict[norm_p] = (orig_p, len(orig_char))

        # 순차적으로 위치 매핑
        o = 0
        n = 0
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

    def _deduplicate(self, entities: list[PIIEntity]) -> list[PIIEntity]:
        """중복 엔티티 제거. 같은 범위 내 더 높은 레벨 우선, 같은 레벨이면 먼저 발견된 것"""
        if not entities:
            return []

        # 위치 기준 정렬
        entities.sort(key=lambda e: (e.start, -e.end, -e.level))

        result = []
        for entity in entities:
            # 기존 결과와 겹치는지 확인
            overlapping = False
            for existing in result:
                if (entity.start < existing.end and entity.end > existing.start
                        and entity.type == existing.type):
                    overlapping = True
                    break
            if not overlapping:
                result.append(entity)

        return result


# 싱글톤 인스턴스
_default_engine: PIIFilterEngine | None = None


def get_engine(level: int = 3) -> PIIFilterEngine:
    global _default_engine
    if _default_engine is None or _default_engine.level != level:
        _default_engine = PIIFilterEngine(level=level)
    return _default_engine


def detect_pii(text: str, level: int = 3) -> list[dict]:
    """텍스트에서 PII를 검출하여 dict 리스트로 반환"""
    engine = get_engine(level)
    entities = engine.detect(text)
    return [e.to_dict() for e in entities]
