"""
PII 유형별 정규식 패턴 정의 (Level 1 기본 패턴)
"""
import re

# === Level 1: 기본 형식 패턴 ===

# 주민등록번호: 6자리-7자리 (앞자리 생년월일, 뒷자리 첫째 1-4)
RRN_PATTERN = re.compile(
    r'\b(\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))'
    r'[-]'
    r'([1-4]\d{6})\b'
)

# 사업자등록번호: 3자리-2자리-5자리
CRN_PATTERN = re.compile(
    r'\b(\d{3})[-](\d{2})[-](\d{5})\b'
)

# 전화번호: 010-xxxx-xxxx, 02-xxx-xxxx, 0xx-xxx(x)-xxxx
PHONE_PATTERN = re.compile(
    r'\b(01[016789])[-](\d{3,4})[-](\d{4})\b'
    r'|'
    r'\b(02)[-](\d{3,4})[-](\d{4})\b'
    r'|'
    r'\b(0[3-6]\d)[-](\d{3,4})[-](\d{4})\b'
)

# 여권번호: 알파벳 1-2자리 + 숫자 7자리
PASSPORT_PATTERN = re.compile(
    r'\b([A-Z]{1,2})(\d{7})\b'
)

# 계좌번호: 은행별 다양한 형식 (10-14자리 숫자, 하이픈 구분)
BANK_ACCOUNT_PATTERN = re.compile(
    r'\b(\d{3,6})[-](\d{2,6})[-](\d{2,6})(?:[-](\d{1,3}))?\b'
)

# 신용카드: 4자리-4자리-4자리-4자리
CREDIT_CARD_PATTERN = re.compile(
    r'\b(\d{4})[-](\d{4})[-](\d{4})[-](\d{4})\b'
)

# 운전면허번호: 지역코드(2자리)-2자리-6자리-2자리
DRIVER_LICENSE_PATTERN = re.compile(
    r'\b(\d{2})[-](\d{2})[-](\d{6})[-](\d{2})\b'
)

# 이메일
EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)


# 각 패턴과 PII 타입 매핑
LEVEL1_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("RRN", RRN_PATTERN),
    ("CRN", CRN_PATTERN),
    ("PHONE", PHONE_PATTERN),
    ("PASSPORT", PASSPORT_PATTERN),
    ("BANK_ACCOUNT", BANK_ACCOUNT_PATTERN),
    ("CREDIT_CARD", CREDIT_CARD_PATTERN),
    ("DRIVER_LICENSE", DRIVER_LICENSE_PATTERN),
    ("EMAIL", EMAIL_PATTERN),
]
