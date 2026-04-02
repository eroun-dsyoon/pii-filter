"""
Blue Team 에이전트: 필터링 알고리즘 실행 및 개선
- 합성 데이터에 대해 PII 필터링 수행
- Judge의 피드백을 반영하여 알고리즘 개선
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field

from ..core.filter_engine import PIIFilterEngine, detect_pii


@dataclass
class FilterResult:
    text: str
    expected_has_pii: bool
    expected_type: str | None
    detected_entities: list[dict]
    is_correct: bool
    error_type: str | None = None  # "false_positive", "false_negative", None


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
        self.improvement_log: list[dict] = []
        # 화이트리스트: 오탐으로 확인된 패턴
        self.whitelist: list[str] = []
        # 추가 패턴: Judge 피드백으로 추가된 패턴
        self.extra_patterns: list[tuple[str, re.Pattern]] = []

    def evaluate_batch(self, data: list[dict]) -> tuple[list[FilterResult], EvaluationMetrics]:
        """합성 데이터 배치를 평가"""
        results = []
        metrics = EvaluationMetrics(total=len(data))

        for item in data:
            text = item.get("text", "")
            expected_has_pii = item.get("has_pii", False)
            expected_type = item.get("pii_type")

            # PII 검출
            detected = self.detect(text)
            detected_has_pii = len(detected) > 0

            # 결과 판정
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
            else:  # expected_has_pii and not detected_has_pii
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

    def detect(self, text: str) -> list[dict]:
        """PII 검출 (화이트리스트 적용)"""
        entities = detect_pii(text, level=self.level)

        # 화이트리스트 필터링
        if self.whitelist:
            entities = [
                e for e in entities
                if not any(wl in e["entity"] for wl in self.whitelist)
            ]

        return entities

    def apply_feedback(self, feedback: dict):
        """Judge의 피드백을 반영하여 알고리즘 개선"""
        improvement = {
            "timestamp": datetime.now().isoformat(),
            "type": feedback.get("type", "unknown"),
            "description": feedback.get("description", ""),
        }

        if feedback.get("type") == "false_positive":
            # 오탐 패턴을 화이트리스트에 추가
            patterns = feedback.get("patterns", [])
            for pattern in patterns:
                if pattern not in self.whitelist:
                    self.whitelist.append(pattern)
            improvement["action"] = f"화이트리스트에 {len(patterns)}개 패턴 추가"

        elif feedback.get("type") == "false_negative":
            # 미탐 패턴 분석 및 추가 규칙
            improvement["action"] = "미탐 케이스 기록"
            # 실제로는 패턴을 분석하여 엔진에 추가해야 하지만,
            # 정규식 기반이므로 피드백을 로그로 기록
            improvement["missed_patterns"] = feedback.get("examples", [])

        self.improvement_log.append(improvement)

    def get_improvement_log(self) -> list[dict]:
        return self.improvement_log
