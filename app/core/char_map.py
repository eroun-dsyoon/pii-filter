"""
숫자 대체 문자 매핑 테이블
요구사항 문서의 전체 매핑을 기반으로 구성
"""
from __future__ import annotations

from typing import Optional, Tuple, List

# 각 숫자(0-9)를 대체할 수 있는 모든 문자 목록
DIGIT_ALTERNATIVES: dict[str, list[str]] = {
    "0": [
        # 사각형 이모지
        "0\ufe0f\u20e3",
        # 점 이모지
        "\U0001f51f",  # 🔟 is actually 10, use correct one
        # 위첨자
        "\u2070",  # ⁰
        # 아래첨자
        "\u2080",  # ₀
        # 원형(흰색)
        "\u24ea",  # ⓪
        # 원형(검은색)
        "\u24ff",  # ⓿
        # 한글
        "공", "영",
        # 한자
        "〇",
        # Leet
        "O", "o",
        # 일본 전각
        "\uff10",  # ０
    ],
    "1": [
        "1\ufe0f\u20e3",
        "\u2764\ufe0f",  # ❤️ (점 이모지 열)
        "\u00b9",  # ¹
        "\u2081",  # ₁
        "\u2460",  # ①
        "\u2776",  # ❶
        "\u2474",  # ⑴
        "\u2170",  # ⅰ
        "일",
        "一",
        "l", "I",
        "\uff11",  # １
    ],
    "2": [
        "2\ufe0f\u20e3",
        "\u270c\ufe0f",  # ✌️
        "\u00b2",  # ²
        "\u2082",  # ₂
        "\u2461",  # ②
        "\u2777",  # ❷
        "\u2475",  # ⑵
        "\u2171",  # ⅱ
        "이",
        "二",
        "Z", "z",
        "\uff12",  # ２
    ],
    "3": [
        "3\ufe0f\u20e3",
        "\U0001f91f",  # 🤟
        "\u00b3",  # ³
        "\u2083",  # ₃
        "\u2462",  # ③
        "\u2778",  # ❸
        "\u2476",  # ⑶
        "\u2172",  # ⅲ
        "삼",
        "三",
        "E",
        "\uff13",  # ３
    ],
    "4": [
        "4\ufe0f\u20e3",
        "\u2074",  # ⁴
        "\u2084",  # ₄
        "\u2463",  # ④
        "\u2779",  # ❹
        "\u2477",  # ⑷
        "\u2173",  # ⅳ
        "사",
        "四",
        "A",
        "\uff14",  # ４
    ],
    "5": [
        "5\ufe0f\u20e3",
        "\U0001f590\ufe0f",  # 🖐️
        "\u2075",  # ⁵
        "\u2085",  # ₅
        "\u2464",  # ⑤
        "\u277a",  # ❺
        "\u2478",  # ⑸
        "\u2174",  # ⅴ
        "오",
        "五",
        "S", "s",
        "\uff15",  # ５
    ],
    "6": [
        "6\ufe0f\u20e3",
        "\U0001f91e",  # 🤞 (요구사항 문서에는 🤞로 되어 있음)
        "\u2076",  # ⁶
        "\u2086",  # ₆
        "\u2465",  # ⑥
        "\u277b",  # ❻
        "\u2479",  # ⑹
        "\u2175",  # ⅵ
        "육",
        "六",
        "G", "b",
        "\uff16",  # ６
    ],
    "7": [
        "7\ufe0f\u20e3",
        "\U0001f91f",  # 🤟 (점 이모지 열)
        "\u2077",  # ⁷
        "\u2087",  # ₇
        "\u2466",  # ⑦
        "\u277c",  # ❼
        "\u247a",  # ⑺
        "\u2176",  # ⅶ
        "칠",
        "七",
        "\uff17",  # ７
    ],
    "8": [
        "8\ufe0f\u20e3",
        "\U0001f3b1",  # 🎱
        "\u2078",  # ⁸
        "\u2088",  # ₈
        "\u2467",  # ⑧
        "\u277d",  # ❽
        "\u247b",  # ⑻
        "\u2177",  # ⅷ
        "팔",
        "八",
        "B",
        "\uff18",  # ８
    ],
    "9": [
        "9\ufe0f\u20e3",
        "\u2079",  # ⁹
        "\u2089",  # ₉
        "\u2468",  # ⑨
        "\u277e",  # ❾
        "\u247c",  # ⑼
        "\u2178",  # ⅸ
        "구",
        "九",
        "g",
        "\uff19",  # ９
    ],
}

# 역방향 매핑: 대체 문자 -> 숫자
CHAR_TO_DIGIT: dict[str, str] = {}
for digit, alternatives in DIGIT_ALTERNATIVES.items():
    for alt in alternatives:
        CHAR_TO_DIGIT[alt] = digit
    # 숫자 자체도 매핑
    CHAR_TO_DIGIT[digit] = digit


def normalize_char(char: str, text: str, pos: int) -> Tuple[Optional[str], int]:
    """
    주어진 위치의 문자(들)를 숫자로 변환 시도.
    이모지 등 멀티바이트 문자를 처리하기 위해 긴 매핑부터 시도.
    Returns: (변환된 숫자 또는 None, 소비한 문자 수)
    """
    # 긴 시퀀스부터 매칭 시도 (이모지 keycap 등)
    for length in range(7, 0, -1):
        candidate = text[pos:pos + length]
        if candidate in CHAR_TO_DIGIT:
            return CHAR_TO_DIGIT[candidate], length
    return None, 1


def normalize_text(text: str) -> Tuple[str, List[Tuple[int, int, str, str]]]:
    """
    텍스트의 대체 문자를 표준 숫자로 변환.
    Returns: (정규화된 텍스트, [(원본위치, 정규화위치, 원본문자, 변환문자)])
    """
    result = []
    mappings = []
    pos = 0
    norm_pos = 0
    while pos < len(text):
        digit, consumed = normalize_char(text[pos], text, pos)
        if digit is not None:
            original = text[pos:pos + consumed]
            mappings.append((pos, norm_pos, original, digit))
            result.append(digit)
            pos += consumed
        else:
            result.append(text[pos])
            pos += 1
        norm_pos += 1 if digit else 1
    return "".join(result), mappings
