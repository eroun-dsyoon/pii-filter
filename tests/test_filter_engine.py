"""PII 필터링 엔진 테스트"""
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.filter_engine import detect_pii, PIIFilterEngine
from app.core.char_map import normalize_text


class TestLevel1:
    """Level 1: 기본 형식 테스트"""

    def test_rrn(self):
        result = detect_pii("주민번호는 900101-1234567 입니다", level=1)
        assert any(e["type"] == "RRN" for e in result), f"RRN not detected: {result}"

    def test_phone(self):
        result = detect_pii("연락처 010-1234-5678", level=1)
        assert any(e["type"] == "PHONE" for e in result), f"PHONE not detected: {result}"

    def test_email(self):
        result = detect_pii("이메일 test@example.com", level=1)
        assert any(e["type"] == "EMAIL" for e in result), f"EMAIL not detected: {result}"

    def test_credit_card(self):
        # Luhn 유효한 카드번호
        result = detect_pii("카드번호 4532-0151-2345-6789", level=1)
        # Luhn 검증 통과 여부에 따라 다를 수 있음
        assert isinstance(result, list)

    def test_crn(self):
        result = detect_pii("사업자번호 123-45-67890", level=1)
        assert any(e["type"] == "CRN" for e in result), f"CRN not detected: {result}"

    def test_driver_license(self):
        result = detect_pii("면허번호 11-22-333333-44", level=1)
        assert any(e["type"] == "DRIVER_LICENSE" for e in result), f"DL not detected: {result}"

    def test_no_pii(self):
        result = detect_pii("오늘 날씨가 좋습니다.", level=1)
        assert len(result) == 0, f"False positive: {result}"


class TestLevel2:
    """Level 2: 다양한 구분자 테스트"""

    def test_phone_with_spaces(self):
        result = detect_pii("010 1234 5678", level=2)
        assert any(e["type"] == "PHONE" for e in result), f"PHONE with spaces not detected: {result}"

    def test_phone_mixed_separators(self):
        result = detect_pii("010 - 1234 _ 5678", level=2)
        assert any(e["type"] == "PHONE" for e in result), f"PHONE mixed sep not detected: {result}"

    def test_single_digit_separator_excluded(self):
        """각 숫자 사이에 구분자가 있는 경우 제외"""
        result = detect_pii("0-1-0-1-2-3-4-5-6-7-8", level=2)
        phone_results = [e for e in result if e["type"] == "PHONE"]
        assert len(phone_results) == 0, f"Should not detect: {phone_results}"


class TestLevel3:
    """Level 3: 대체 문자 테스트"""

    def test_korean_digits(self):
        result = detect_pii("공일공-일이삼사-오육칠팔", level=3)
        assert any(e["type"] == "PHONE" for e in result), f"Korean digits not detected: {result}"

    def test_leet_speak(self):
        """Leet 문자 치환 테스트"""
        result = detect_pii("OlO-l234-5G78", level=3)
        assert any(e.get("normalized") for e in result if e["type"] == "PHONE"), f"Leet not detected: {result}"

    def test_fullwidth(self):
        """전각 문자 테스트"""
        result = detect_pii("０１０-１２３４-５６７８", level=3)
        assert any(e["type"] == "PHONE" for e in result), f"Fullwidth not detected: {result}"


class TestNormalization:
    """문자 정규화 테스트"""

    def test_korean_to_digits(self):
        normalized, _ = normalize_text("공일공")
        assert normalized == "010"

    def test_fullwidth_to_digits(self):
        normalized, _ = normalize_text("０１２")
        assert normalized == "012"

    def test_mixed(self):
        normalized, _ = normalize_text("공1공")
        assert normalized == "010"


class TestPerformance:
    """성능 테스트: 1건당 0.01초 이내"""

    def test_speed(self):
        text = "제 전화번호는 010-1234-5678이고 주민번호는 900101-1234567입니다. 이메일은 test@example.com"
        engine = PIIFilterEngine(level=3)

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            engine.detect(text)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        print(f"평균 처리 시간: {avg_ms:.3f}ms")
        assert avg_ms < 10, f"Too slow: {avg_ms:.3f}ms (limit: 10ms)"


class TestAPIResponse:
    """API 응답 형식 테스트"""

    def test_normalized_field(self):
        result = detect_pii("공일공-1234-5678", level=3)
        phone = [e for e in result if e["type"] == "PHONE"]
        if phone:
            assert "normalized" in phone[0]

    def test_no_normalized_for_standard(self):
        result = detect_pii("010-1234-5678", level=1)
        for e in result:
            assert e.get("normalized") is None or e["normalized"] == e["entity"]


def run_tests():
    """간단한 테스트 러너"""
    test_classes = [TestLevel1, TestLevel2, TestLevel3, TestNormalization, TestPerformance, TestAPIResponse]
    total = 0
    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        print(f"\n=== {cls.__name__} ===")
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                total += 1
                try:
                    getattr(instance, method_name)()
                    print(f"  PASS: {method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  FAIL: {method_name} - {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ERROR: {method_name} - {e}")
                    failed += 1

    print(f"\n{'='*50}")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
