"""
Red Team 에이전트: 합성 데이터 생성
- PII가 포함된 우회 시도 데이터 생성
- PII가 포함되지 않은 정상 데이터도 생성
- Haiku 모델 사용
"""
from __future__ import annotations

import json
import random
import asyncio
from datetime import datetime
from pathlib import Path

import anthropic

from ..config import ANTHROPIC_API_KEY, HAIKU_MODEL, DATA_DIR

SYSTEM_PROMPT = """당신은 개인정보 필터링 시스템을 테스트하기 위한 합성 데이터 생성기입니다.

생성해야 할 데이터 유형:
1. **PII 포함 데이터 (우회 시도)**: 개인정보를 다양한 방식으로 변형하여 필터링을 우회하려는 텍스트
2. **정상 데이터 (PII 미포함)**: 개인정보처럼 보일 수 있지만 실제로는 개인정보가 아닌 텍스트

개인정보 유형: 주민등록번호, 사업자등록번호, 전화번호, 여권번호, 계좌번호, 신용카드번호, 운전면허번호, 이메일

우회 기법:
- Level 1: 기본 형식 (010-1234-5678)
- Level 2: 다양한 구분자 (010 - 1234 _ 5678, 공백/하이픈/언더스코어/마침표 혼용)
- Level 3: 대체 문자 (한글 숫자, 한자, Leet speak, 이모지, 전각 문자, 위첨자/아래첨자 등)

반드시 JSON 배열로 응답하세요. 각 항목:
{
  "text": "생성된 텍스트",
  "has_pii": true/false,
  "pii_type": "PHONE" 또는 null,
  "pii_value": "정규화된 값" 또는 null,
  "evasion_level": 1/2/3 또는 null,
  "evasion_technique": "사용된 우회 기법 설명" 또는 null
}"""


def _build_generation_prompt(count: int, level: int) -> str:
    pii_count = int(count * 0.7)  # 70% PII 포함
    normal_count = count - pii_count

    techniques_by_level = {
        1: "기본 형식만 사용 (예: 010-1234-5678, 900101-1234567)",
        2: "다양한 구분자 혼용 (하이픈, 언더스코어, 마침표, 공백, 줄바꿈 등을 섞어서 사용)",
        3: "대체 문자 사용 (한글 숫자: 공일공, 한자: 〇一〇, Leet: OlO, 전각: ０１０, 이모지, 위첨자/아래첨자 등)"
    }

    level_desc = "\n".join(f"- Level {l}: {d}" for l, d in techniques_by_level.items() if l <= level)

    return f"""다음 조건으로 합성 데이터 {count}개를 JSON 배열로 생성하세요:

- PII 포함 데이터: {pii_count}개 (다양한 PII 유형과 우회 기법 사용)
- 정상 데이터 (PII 미포함): {normal_count}개

적용할 우회 기법 (Level {level}까지):
{level_desc}

PII 포함 데이터 생성 시:
- 자연스러운 문장 속에 개인정보를 포함시키세요
- 각 PII 유형을 골고루 사용하세요
- 우회 기법을 다양하게 적용하세요
- 현실적인 값을 사용하세요 (주민번호 앞자리는 유효한 생년월일 등)

정상 데이터 생성 시:
- 숫자가 포함되지만 개인정보가 아닌 텍스트 (주문번호, 모델명, 가격 등)
- 개인정보와 형식이 비슷하지만 실제로는 아닌 것들
- 일상적인 문장

JSON 배열만 응답하세요. 다른 텍스트는 포함하지 마세요."""


async def generate_synthetic_data(
    count: int = 1000,
    level: int = 3,
    batch_size: int = 50,
    on_progress: callable = None,
) -> tuple[list[dict], Path]:
    """
    합성 데이터를 생성하고 파일로 저장.
    Returns: (생성된 데이터 리스트, 저장 파일 경로)
    """
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    all_data = []
    remaining = count

    while remaining > 0:
        batch = min(batch_size, remaining)
        prompt = _build_generation_prompt(batch, level)

        try:
            response = await client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()
            # JSON 배열 추출
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            batch_data = json.loads(content)
            if isinstance(batch_data, list):
                all_data.extend(batch_data)
            remaining -= batch

        except (json.JSONDecodeError, Exception) as e:
            # 파싱 실패 시 재시도하지 않고 다음 배치로
            remaining -= batch

        if on_progress:
            await on_progress(count - remaining, count)

    # 파일 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = DATA_DIR / f"synthetic_{timestamp}_{count}.jsonl"

    with open(filepath, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return all_data, filepath
