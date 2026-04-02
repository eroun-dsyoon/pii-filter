"""
Judge 에이전트: Blue Team 결과 평가 및 피드백 제공
- 오탐/미탐 판정
- Haiku 모델 사용
"""
from __future__ import annotations

import json
import asyncio

import anthropic

from ..config import ANTHROPIC_API_KEY, HAIKU_MODEL
from .blue_team import FilterResult

SYSTEM_PROMPT = """당신은 개인정보(PII) 필터링 결과를 검증하는 판사입니다.

Blue Team 에이전트가 텍스트에서 PII를 검출한 결과를 평가하고, 오탐(False Positive)과 미탐(False Negative)을 정확히 판정합니다.

한국 PII 유형:
- RRN: 주민등록번호 (YYMMDD-GXXXXXX)
- CRN: 사업자등록번호 (XXX-XX-XXXXX)
- PHONE: 전화번호 (010-XXXX-XXXX 등)
- PASSPORT: 여권번호 (알파벳1-2 + 숫자7)
- BANK_ACCOUNT: 계좌번호
- CREDIT_CARD: 신용카드번호 (16자리)
- DRIVER_LICENSE: 운전면허번호 (XX-XX-XXXXXX-XX)
- EMAIL: 이메일 주소

판정 기준:
1. 오탐(FP): PII가 아닌데 PII로 검출된 경우
2. 미탐(FN): PII인데 검출되지 않은 경우
3. 정탐(TP): PII를 올바르게 검출한 경우
4. 정상(TN): PII가 아닌 것을 올바르게 통과시킨 경우

반드시 JSON으로 응답하세요:
{
  "judgments": [
    {
      "index": 0,
      "verdict": "TP" | "TN" | "FP" | "FN",
      "reason": "판정 사유",
      "suggestion": "개선 제안 (FP/FN인 경우만)"
    }
  ],
  "feedback": {
    "false_positive_patterns": ["오탐으로 확인된 패턴들"],
    "false_negative_examples": ["미탐된 케이스들"],
    "improvement_suggestions": ["전체적인 개선 제안"]
  }
}"""


async def judge_results(
    results: list[FilterResult],
    batch_size: int = 20,
) -> dict:
    """
    Blue Team 결과를 Judge가 평가.
    Returns: 종합 피드백
    """
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # 오류 케이스만 추출하여 검증 (전체를 다 보내면 비용이 너무 높음)
    error_cases = [r for r in results if not r.is_correct]

    if not error_cases:
        return {
            "total_errors": 0,
            "false_positive_feedback": {"type": "false_positive", "patterns": []},
            "false_negative_feedback": {"type": "false_negative", "examples": []},
            "suggestions": [],
        }

    all_judgments = []
    fp_patterns = []
    fn_examples = []
    suggestions = []

    for i in range(0, len(error_cases), batch_size):
        batch = error_cases[i:i + batch_size]
        prompt = _build_judge_prompt(batch)

        try:
            response = await client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)
            all_judgments.extend(result.get("judgments", []))

            feedback = result.get("feedback", {})
            fp_patterns.extend(feedback.get("false_positive_patterns", []))
            fn_examples.extend(feedback.get("false_negative_examples", []))
            suggestions.extend(feedback.get("improvement_suggestions", []))

        except (json.JSONDecodeError, Exception):
            continue

    return {
        "total_errors": len(error_cases),
        "judgments": all_judgments,
        "false_positive_feedback": {
            "type": "false_positive",
            "patterns": list(set(fp_patterns)),
            "description": f"오탐 패턴 {len(set(fp_patterns))}개 발견",
        },
        "false_negative_feedback": {
            "type": "false_negative",
            "examples": fn_examples,
            "description": f"미탐 케이스 {len(fn_examples)}개 발견",
        },
        "suggestions": suggestions,
    }


def _build_judge_prompt(results: list[FilterResult]) -> str:
    cases = []
    for i, r in enumerate(results):
        case = {
            "index": i,
            "text": r.text[:500],  # 텍스트 길이 제한
            "expected_has_pii": r.expected_has_pii,
            "expected_type": r.expected_type,
            "detected": r.detected_entities,
            "blue_team_verdict": r.error_type,
        }
        cases.append(case)

    return f"""다음 {len(cases)}개의 PII 필터링 오류 케이스를 검증해주세요.

각 케이스에서:
- text: 검사 대상 텍스트
- expected_has_pii: 합성 데이터 생성 시 의도한 PII 유무
- expected_type: 의도한 PII 유형
- detected: Blue Team이 검출한 결과
- blue_team_verdict: Blue Team의 판정 (false_positive 또는 false_negative)

케이스:
{json.dumps(cases, ensure_ascii=False, indent=2)}

각 케이스의 실제 판정과 개선 방안을 JSON으로 응답하세요."""
