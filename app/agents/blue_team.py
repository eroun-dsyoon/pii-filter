"""
Blue Team 에이전트: 필터링 알고리즘 실행 및 개선
- 합성 데이터에 대해 PII 필터링 수행
- Judge의 피드백을 반영하여 알고리즘 개선
- 오탐 텍스트 패턴 학습 및 화이트리스트 관리
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from collections import Counter

from ..core.filter_engine import PIIFilterEngine, detect_pii


@dataclass
class FilterResult:
    text: str
    expected_has_pii: bool
    expected_type: Optional[str]
    detected_entities: List[dict]
    is_correct: bool
    error_type: Optional[str] = None  # "false_positive", "false_negative", None


@dataclass
class EvaluationMetrics:
    total: int = 0
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        return (self.true_positives + self.true_negatives) / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
        }


class BlueTeamAgent:
    """PII 필터링 및 평가 에이전트"""

    def __init__(self, level: int = 3):
        self.engine = PIIFilterEngine(level=level)
        self.level = level
        self.improvement_log: List[dict] = []
        # 화이트리스트: 오탐으로 확인된 텍스트 패턴
        self.whitelist_texts: List[str] = []
        # 화이트리스트: 오탐으로 확인된 정규식 패턴
        self.whitelist_patterns: List[re.Pattern] = []

    def evaluate_batch(self, data: List[dict]) -> Tuple[List[FilterResult], EvaluationMetrics]:
        """합성 데이터 배치를 평가"""
        results = []
        metrics = EvaluationMetrics(total=len(data))

        for item in data:
            text = item.get("text", "")
            expected_has_pii = item.get("has_pii", False)
            expected_type = item.get("pii_type")

            detected = self.detect(text)
            detected_has_pii = len(detected) > 0

            if expected_has_pii and detected_has_pii:
                metrics.true_positives += 1
                error_type = None
                is_correct = True
            elif not expected_has_pii and not detected_has_pii:
                metrics.true_negatives += 1
                error_type = None
                is_correct = True
            elif not expected_has_pii and detected_has_pii:
                metrics.false_positives += 1
                error_type = "false_positive"
                is_correct = False
            else:
                metrics.false_negatives += 1
                error_type = "false_negative"
                is_correct = False

            results.append(FilterResult(
                text=text,
                expected_has_pii=expected_has_pii,
                expected_type=expected_type,
                detected_entities=detected,
                is_correct=is_correct,
                error_type=error_type,
            ))

        return results, metrics

    def detect(self, text: str) -> List[dict]:
        """PII 검출 (화이트리스트 적용)"""
        entities = detect_pii(text, level=self.level)

        # 텍스트 화이트리스트 필터링
        if self.whitelist_texts:
            entities = [
                e for e in entities
                if not any(wl in e["entity"] for wl in self.whitelist_texts)
            ]

        # 정규식 화이트리스트 필터링
        if self.whitelist_patterns:
            entities = [
                e for e in entities
                if not any(p.search(e["entity"]) for p in self.whitelist_patterns)
            ]

        return entities

    def analyze_errors(self, results: List[FilterResult]) -> dict:
        """오탐/미탐 케이스를 상세 분석"""
        fp_cases = [r for r in results if r.error_type == "false_positive"]
        fn_cases = [r for r in results if r.error_type == "false_negative"]

        # FP 분석: 어떤 타입이 가장 많이 오탐되는지
        fp_type_counter = Counter()
        fp_samples = []
        for r in fp_cases:
            for e in r.detected_entities:
                fp_type_counter[e.get("type", "?")] += 1
            if len(fp_samples) < 20:
                fp_samples.append({
                    "text": r.text[:200],
                    "detected": [{"type": e["type"], "entity": e["entity"]} for e in r.detected_entities],
                })

        # FN 분석: 어떤 타입이 가장 많이 미탐되는지
        fn_type_counter = Counter(r.expected_type for r in fn_cases if r.expected_type)
        fn_samples = []
        for r in fn_cases:
            if len(fn_samples) < 20:
                fn_samples.append({
                    "text": r.text[:200],
                    "expected_type": r.expected_type,
                })

        return {
            "fp_count": len(fp_cases),
            "fn_count": len(fn_cases),
            "fp_by_type": dict(fp_type_counter.most_common()),
            "fn_by_type": dict(fn_type_counter.most_common()),
            "fp_samples": fp_samples,
            "fn_samples": fn_samples,
        }

    def apply_feedback(self, feedback: dict) -> dict:
        """
        Judge의 피드백을 반영하여 알고리즘 개선.
        Returns: 적용된 개선 내역
        """
        improvement = {
            "timestamp": datetime.now().isoformat(),
            "type": feedback.get("type", "unknown"),
            "description": feedback.get("description", ""),
            "actions": [],
        }

        if feedback.get("type") == "false_positive":
            # 오탐 패턴 분석 → 화이트리스트 추가
            fp_texts = feedback.get("patterns", [])
            added = 0
            for pattern_text in fp_texts:
                if pattern_text and pattern_text not in self.whitelist_texts:
                    self.whitelist_texts.append(pattern_text)
                    added += 1
            if added:
                improvement["actions"].append(f"텍스트 화이트리스트에 {added}개 패턴 추가")

            # FP 타입 분포에서 특정 패턴 자동 생성
            fp_type_dist = feedback.get("type_distribution", {})
            for pii_type, count in fp_type_dist.items():
                if count >= 3:  # 3건 이상 반복되는 오탐 패턴
                    improvement["actions"].append(
                        f"{pii_type} 타입 오탐 {count}건 반복 → 검증 강화 필요"
                    )

        elif feedback.get("type") == "false_negative":
            fn_examples = feedback.get("examples", [])
            fn_type_dist = feedback.get("type_distribution", {})
            improvement["actions"].append(f"미탐 케이스 {len(fn_examples)}건 기록")
            for pii_type, count in fn_type_dist.items():
                improvement["actions"].append(
                    f"{pii_type} 타입 미탐 {count}건 → 패턴 확장 필요"
                )
            improvement["missed_samples"] = fn_examples[:10]

        self.improvement_log.append(improvement)
        return improvement

    def get_improvement_log(self) -> List[dict]:
        return self.improvement_log
