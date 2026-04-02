"""
에이전트 오케스트레이터: Red Team → Blue Team → Judge 파이프라인 관리
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from ..config import DATA_DIR, REPORTS_DIR
from .data_generator import generate_and_save as generate_synthetic_data_local
from .blue_team import BlueTeamAgent, EvaluationMetrics
from .judge import judge_results

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """3개 에이전트의 파이프라인을 관리"""

    def __init__(self):
        self.runs: dict = {}

    async def run_pipeline(
        self,
        count: int = 1000,
        level: int = 3,
        on_progress: Optional[Callable] = None,
    ) -> str:
        run_id = str(uuid.uuid4())[:8]
        self.runs[run_id] = {
            "status": "running",
            "total": count,
            "processed": 0,
            "phase": "red_team",
            "metrics": None,
            "message": "Red Team 에이전트가 합성 데이터를 생성 중...",
            "started_at": datetime.now().isoformat(),
        }

        try:
            # === Phase 1: Red Team - 합성 데이터 생성 ===
            logger.info(f"[{run_id}] Phase 1: Red Team 시작 (count={count}, level={level})")
            self.runs[run_id]["message"] = f"[1/5] Red Team: 합성 데이터 {count}개 생성 중..."
            data, data_path = generate_synthetic_data_local(count=count, level=level)
            logger.info(f"[{run_id}] Red Team 완료: {len(data)}개 생성")

            if not data:
                raise RuntimeError("합성 데이터가 생성되지 않았습니다.")

            self.runs[run_id]["processed"] = count

            # === Phase 2: Blue Team - 1차 필터링 ===
            self.runs[run_id]["phase"] = "blue_team"
            self.runs[run_id]["message"] = f"[2/5] Blue Team: {len(data)}개 데이터 1차 필터링 중..."
            logger.info(f"[{run_id}] Phase 2: Blue Team 1차 필터링 시작")

            blue_agent = BlueTeamAgent(level=level)
            results_v1, metrics_v1 = blue_agent.evaluate_batch(data)
            error_analysis_v1 = blue_agent.analyze_errors(results_v1)

            self.runs[run_id]["metrics"] = metrics_v1.to_dict()
            self.runs[run_id]["message"] = (
                f"[2/5] 1차 필터링 완료 - "
                f"F1: {metrics_v1.f1_score:.4f}, FP: {metrics_v1.false_positives}, FN: {metrics_v1.false_negatives}"
            )
            logger.info(f"[{run_id}] 1차 결과: {metrics_v1.to_dict()}")

            # === Phase 3: Judge - 오탐/미탐 분석 ===
            self.runs[run_id]["phase"] = "judge"
            self.runs[run_id]["message"] = (
                f"[3/5] Judge: 오류 {error_analysis_v1['fp_count'] + error_analysis_v1['fn_count']}건 분석 중..."
            )
            logger.info(f"[{run_id}] Phase 3: Judge 시작")

            feedback = await judge_results(results_v1)
            logger.info(f"[{run_id}] Judge 완료: 오류 {feedback.get('total_errors', 0)}건")

            # === Phase 4: Blue Team - 피드백 반영 및 개선 ===
            self.runs[run_id]["phase"] = "improvement"
            self.runs[run_id]["message"] = "[4/5] Blue Team: Judge 피드백을 반영하여 알고리즘 개선 중..."

            fp_improvement = {}
            fn_improvement = {}
            if feedback.get("false_positive_feedback"):
                fp_feedback = feedback["false_positive_feedback"]
                # Judge의 타입 분포 정보도 전달
                fp_feedback["type_distribution"] = feedback.get(
                    "false_positive_feedback", {}
                ).get("type_distribution", {})
                fp_improvement = blue_agent.apply_feedback(fp_feedback)

            if feedback.get("false_negative_feedback"):
                fn_feedback = feedback["false_negative_feedback"]
                fn_feedback["type_distribution"] = feedback.get(
                    "false_negative_feedback", {}
                ).get("type_distribution", {})
                fn_improvement = blue_agent.apply_feedback(fn_feedback)

            # === Phase 5: 개선 후 재평가 ===
            self.runs[run_id]["message"] = "[5/5] 개선된 알고리즘으로 재평가 중..."
            results_v2, metrics_v2 = blue_agent.evaluate_batch(data)
            error_analysis_v2 = blue_agent.analyze_errors(results_v2)
            logger.info(f"[{run_id}] 개선 후 메트릭: {metrics_v2.to_dict()}")

            # === 리포트 생성 ===
            report = self._generate_report(
                run_id=run_id,
                count=count,
                level=level,
                metrics_before=metrics_v1,
                metrics_after=metrics_v2,
                error_analysis_before=error_analysis_v1,
                error_analysis_after=error_analysis_v2,
                feedback=feedback,
                improvements=blue_agent.get_improvement_log(),
                data_path=str(data_path),
            )

            self.runs[run_id].update({
                "status": "completed",
                "phase": "done",
                "processed": count,
                "metrics": metrics_v2.to_dict(),
                "message": (
                    f"파이프라인 완료 - "
                    f"F1: {metrics_v1.f1_score:.4f}→{metrics_v2.f1_score:.4f}, "
                    f"FP: {metrics_v1.false_positives}→{metrics_v2.false_positives}, "
                    f"FN: {metrics_v1.false_negatives}→{metrics_v2.false_negatives}"
                ),
                "report": report,
                "completed_at": datetime.now().isoformat(),
            })
            logger.info(f"[{run_id}] 파이프라인 완료")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{run_id}] 파이프라인 실패: {error_msg}")
            self.runs[run_id].update({
                "status": "failed",
                "message": f"오류 발생: {error_msg}",
            })

        return run_id

    def _generate_report(
        self,
        run_id: str,
        count: int,
        level: int,
        metrics_before: EvaluationMetrics,
        metrics_after: EvaluationMetrics,
        error_analysis_before: dict,
        error_analysis_after: dict,
        feedback: dict,
        improvements: list,
        data_path: str,
    ) -> dict:
        report = {
            "id": run_id,
            "created_at": datetime.now().isoformat(),
            "config": {"count": count, "level": level},
            "data_path": data_path,
            # 개선 전 지표
            "before": metrics_before.to_dict(),
            # 개선 후 지표
            "after": metrics_after.to_dict(),
            # 지표별 변화량
            "metric_changes": [
                {
                    "metric": "precision",
                    "before": round(metrics_before.precision, 4),
                    "after": round(metrics_after.precision, 4),
                    "delta": round(metrics_after.precision - metrics_before.precision, 4),
                },
                {
                    "metric": "recall",
                    "before": round(metrics_before.recall, 4),
                    "after": round(metrics_after.recall, 4),
                    "delta": round(metrics_after.recall - metrics_before.recall, 4),
                },
                {
                    "metric": "f1_score",
                    "before": round(metrics_before.f1_score, 4),
                    "after": round(metrics_after.f1_score, 4),
                    "delta": round(metrics_after.f1_score - metrics_before.f1_score, 4),
                },
                {
                    "metric": "accuracy",
                    "before": round(metrics_before.accuracy, 4),
                    "after": round(metrics_after.accuracy, 4),
                    "delta": round(metrics_after.accuracy - metrics_before.accuracy, 4),
                },
            ],
            # 오탐/미탐 상세 분석 (개선 전)
            "error_analysis_before": {
                "fp_count": error_analysis_before["fp_count"],
                "fn_count": error_analysis_before["fn_count"],
                "fp_by_type": error_analysis_before["fp_by_type"],
                "fn_by_type": error_analysis_before["fn_by_type"],
                "fp_samples": error_analysis_before["fp_samples"],
                "fn_samples": error_analysis_before["fn_samples"],
            },
            # 오탐/미탐 상세 분석 (개선 후)
            "error_analysis_after": {
                "fp_count": error_analysis_after["fp_count"],
                "fn_count": error_analysis_after["fn_count"],
                "fp_by_type": error_analysis_after["fp_by_type"],
                "fn_by_type": error_analysis_after["fn_by_type"],
                "fp_samples": error_analysis_after["fp_samples"],
                "fn_samples": error_analysis_after["fn_samples"],
            },
            # Judge 피드백 요약
            "judge_feedback": {
                "total_errors": feedback.get("total_errors", 0),
                "fp_patterns": feedback.get("false_positive_feedback", {}).get("patterns", []),
                "fn_description": feedback.get("false_negative_feedback", {}).get("description", ""),
                "suggestions": feedback.get("suggestions", []),
            },
            # 개선 로그
            "improvement_log": improvements,
        }

        report_path = REPORTS_DIR / f"report_{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def get_run_status(self, run_id: str):
        return self.runs.get(run_id)

    def list_runs(self) -> list:
        return [
            {"run_id": rid, **{k: v for k, v in info.items() if k != "report"}}
            for rid, info in self.runs.items()
        ]


# 싱글톤
_orchestrator = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
