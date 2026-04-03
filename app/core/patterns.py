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

# 전화번호: 모든 한국 전화번호 체계
# 휴대폰: 010/011/016/017/018/019-XXXX-XXXX
# VoIP: 070-XXXX-XXXX
# 수신자부담: 080-XXX(X)-XXXX
# 안심번호: 0502/0504/0505/0507-XXX(X)-XXXX
# 서울: 02-XXX(X)-XXXX
# 지역: 031~064-XXX(X)-XXXX
# 대표번호: 15XX-XXXX, 16XX-XXXX
PHONE_PATTERN = re.compile(
    # 휴대폰
    r'\b(01[016789])[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # VoIP (인터넷전화)
    r'\b(070)[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # 수신자부담
    r'\b(080)[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # 안심번호/부가통신 (4자리 국번)
    r'\b(050[2-8])[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # 서울
    r'\b(02)[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # 지역번호
    r'\b(0[3-6]\d)[-](\d{3,4})[-](\d{4})\b'
    r'|'
    # 대표번호 (15XX, 16XX, 18XX)
    r'\b(1[5-8]\d{2})[-](\d{4})\b'
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
LEVEL1_PATTERNS = [
    ("RRN", RRN_PATTERN),
    ("CRN", CRN_PATTERN),
    ("PHONE", PHONE_PATTERN),
    ("PASSPORT", PASSPORT_PATTERN),
    ("BANK_ACCOUNT", BANK_ACCOUNT_PATTERN),
    ("CREDIT_CARD", CREDIT_CARD_PATTERN),
    ("DRIVER_LICENSE", DRIVER_LICENSE_PATTERN),
    ("EMAIL", EMAIL_PATTERN),
]
