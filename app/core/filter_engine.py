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
from .bank_identifier import get_bank_info


@dataclass
class PIIEntity:
    type: str
    entity: str
    start: int
    end: int
    normalized: Optional[str] = None
    level: int = 1
    detail: Optional[dict] = None  # 추가 정보 (은행명 등)

    def to_dict(self) -> dict:
        d = {"type": self.type, "entity": self.entity, "start": self.start, "end": self.end}
        if self.normalized and self.normalized != self.entity:
            d["normalized"] = self.normalized
        d["level"] = self.level
        if self.detail:
            d["detail"] = self.detail
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

# 전화번호: 모든 체계
_phone_l2_mobile = _build_level2_pattern([(3, 3), (3, 4), (4, 4)])   # 010, 070, 080
_phone_l2_seoul = _build_level2_pattern([(2, 2), (3, 4), (4, 4)])    # 02
_phone_l2_virtual = _build_level2_pattern([(4, 4), (3, 4), (4, 4)])  # 0502, 0505
_phone_l2_rep = _build_level2_pattern([(4, 4), (4, 4)])              # 1588, 1577
LEVEL2_PATTERNS.append(("PHONE", re.compile(
    f'(?:{_phone_l2_mobile}|{_phone_l2_seoul}|{_phone_l2_virtual}|{_phone_l2_rep})'
)))

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

# 이메일 Level 2: 공백이 삽입된 이메일 (구분자 변형)
# 패턴 1: @ 앞뒤, . 앞뒤 공백 허용
# 패턴 2: 모든 문자 사이 공백 허용 (d s yoon @ eroun . a i)
_EMAIL_L2 = re.compile(
    r'(?:[A-Za-z0-9._%+\-]\s*){2,}@\s*(?:[A-Za-z0-9\-]\s*){1,}(?:\.\s*(?:[A-Za-z]\s*){2,})'
)
LEVEL2_PATTERNS.append(("EMAIL", _EMAIL_L2))


def _validate_email_l2(text: str) -> bool:
    """Level 2 이메일 검증: 공백 제거 후 RFC 기본 규칙 확인"""
    stripped = re.sub(r'\s+', '', text)

    if stripped.count('@') != 1:
        return False
    if '.' not in stripped:
        return False

    local, domain = stripped.split('@')

    if not local or len(local) > 64:
        return False
    if local.startswith('.') or local.endswith('.'):
        return False
    if '..' in local:
        return False

    if not domain or len(domain) > 255:
        return False
    if '..' in domain:
        return False

    domain_parts = domain.split('.')
    if len(domain_parts) < 2:
        return False

    tld = domain_parts[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False

    return True


def _strip_digits(text: str) -> str:
    """텍스트에서 숫자만 추출"""
    return ''.join(c for c in text if c.isdigit())


# 체계 기반 검증 모듈 import
from .validators import VALIDATORS, validate_pii


# 형식만 검증 (체크섬/유효성 무시) - strict=False 일 때 사용
def _format_only_rrn(digits: str) -> bool:
    return len(digits) == 13 and digits.isdigit()

def _format_only_crn(digits: str) -> bool:
    return len(digits) == 10 and digits.isdigit()

def _format_only_phone(digits: str) -> bool:
    return digits.isdigit() and 8 <= len(digits) <= 12 and digits.startswith('0') or digits[:2] in ('15','16','18')

def _format_only_credit_card(digits: str) -> bool:
    return len(digits) == 16 and digits.isdigit()

def _format_only_driver_license(digits: str) -> bool:
    return len(digits) == 12 and digits.isdigit()

def _format_only_bank_account(digits: str) -> bool:
    return digits.isdigit() and 10 <= len(digits) <= 14

FORMAT_ONLY_VALIDATORS = {
    "RRN": _format_only_rrn,
    "CRN": _format_only_crn,
    "PHONE": _format_only_phone,
    "CREDIT_CARD": _format_only_credit_card,
    "DRIVER_LICENSE": _format_only_driver_license,
    "BANK_ACCOUNT": _format_only_bank_account,
}


def _enrich_entity(entity: PIIEntity) -> PIIEntity:
    """엔티티에 추가 정보를 부여 (은행 식별 등)"""
    if entity.type == "BANK_ACCOUNT":
        # normalized가 있으면 우선 사용 (대체문자 정규화된 값)
        source = entity.normalized or entity.entity
        info = get_bank_info(source)
        # 은행 식별 또는 형식 정보가 있으면 추가
        if info.get("bank") or info.get("digits", 0) >= 10:
            entity.detail = info
    return entity


class PIIFilterEngine:
    """PII 필터링 엔진"""

    def __init__(self, level: int = 3, strict: bool = True):
        """
        level: 검출 레벨 (1=기본형식, 2=구분자변형, 3=대체문자)
        strict: True=체계 기반 검증(체크섬/유효성), False=형식만 검증
        """
        self.level = level
        self.strict = strict

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

        # 추가 정보 부여 (은행 식별 등)
        entities = [_enrich_entity(e) for e in entities]

        return entities

    # 비PII 문맥 키워드 (앞 30자 이내에 있으면 제외)
    _CONTEXT_EXCLUDE_KEYWORDS = re.compile(
        r'송장|택배|배송|운송장|tracking|parcel|주문번호|관리번호|'
        r'시리얼|serial|제품번호|코드번호|식별코드|사원번호|예약번호|'
        r'참조번호|인증번호|도서번호',
        re.IGNORECASE,
    )

    def _get_validator(self, pii_type: str):
        """strict 모드에 따라 적절한 validator 반환"""
        if self.strict:
            return VALIDATORS.get(pii_type)
        else:
            return FORMAT_ONLY_VALIDATORS.get(pii_type)

    def _is_excluded_context(self, text: str, start: int, end: int) -> bool:
        """오탐 방지: 특정 문맥에서는 PII로 판단하지 않음"""
        context_before = text[max(0, start - 30):start]
        context_after = text[end:min(len(text), end + 10)]
        full_context = context_before + text[start:end] + context_after

        # 비PII 문맥 키워드
        if self._CONTEXT_EXCLUDE_KEYWORDS.search(context_before):
            return True

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

                validator = self._get_validator(pii_type)
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

                # 이메일 Level 2: 공백 제거 후 별도 검증
                if pii_type == "EMAIL":
                    if not _validate_email_l2(entity_text):
                        continue
                    # 공백이 포함된 경우만 Level 2로 (공백 없으면 Level 1에서 처리)
                    normalized_email = re.sub(r'\s+', '', entity_text)
                    has_spaces = normalized_email != entity_text.strip()
                    if not has_spaces:
                        continue  # Level 1과 동일하므로 스킵

                    start = match.start()
                    end = match.end()
                    if self._is_excluded_context(text, start, end):
                        continue
                    results.append(PIIEntity(
                        type=pii_type,
                        entity=entity_text.strip(),
                        start=start,
                        end=end,
                        normalized=normalized_email,
                        level=2,
                    ))
                    continue

                if not self._validate_level2_separators(entity_text, pii_type):
                    continue

                validator = self._get_validator(pii_type)
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
            # 이메일은 Level 3 대상 아님 (숫자 대체문자 개념 없음)
            if pii_type == "EMAIL":
                continue

            for match in pattern.finditer(normalized):
                entity_norm = match.group()
                digits = _strip_digits(entity_norm)

                # Level 3 검증: 정규화된 값으로 validator 호출
                from .validators import TEXT_VALIDATORS
                if pii_type == "PASSPORT":
                    # 여권: 원본에서 영문자 확인 후 정규화 값으로 검증
                    # Leet 변환이 영문자를 숫자로 바꿔버리므로 원본 기반 확인
                    norm_s = match.start()
                    norm_e = match.end()
                    o_s, o_e = self._map_to_original(norm_s, norm_e, text, normalized, mappings)
                    orig_part = text[o_s:o_e]
                    # 원본에 영문자가 있으면 여권으로 간주
                    has_alpha = any(c.isalpha() for c in orig_part)
                    if not has_alpha:
                        continue
                    # 영문 1~2자리 + 숫자 7자리 형식 확인
                    if len(digits) < 7:
                        continue
                elif pii_type in TEXT_VALIDATORS:
                    if self.strict and not TEXT_VALIDATORS[pii_type](entity_norm):
                        continue
                else:
                    validator = self._get_validator(pii_type)
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

        # 같은 위치면 낮은 레벨(더 정확한 매칭)을 우선
        entities.sort(key=lambda e: (e.start, -e.end, e.level))

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


# 싱글톤 캐시
_engine_cache = {}


def get_engine(level: int = 3, strict: bool = True) -> PIIFilterEngine:
    key = (level, strict)
    if key not in _engine_cache:
        _engine_cache[key] = PIIFilterEngine(level=level, strict=strict)
    return _engine_cache[key]


def detect_pii(text: str, level: int = 3, strict: bool = True) -> list:
    """
    텍스트에서 PII를 검출하여 dict 리스트로 반환.
    strict=True: 체계 기반 검증 (체크섬, 유효 지역코드 등)
    strict=False: 형식만 검증 (자릿수만 맞으면 검출)
    """
    engine = get_engine(level, strict)
    entities = engine.detect(text)
    return [e.to_dict() for e in entities]
