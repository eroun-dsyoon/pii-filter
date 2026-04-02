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
from .red_team import generate_synthetic_data as generate_synthetic_data_api
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
        """
        전체 파이프라인 실행:
        1. Red Team: 합성 데이터 생성
        2. Blue Team: PII 필터링 실행
        3. Judge: 결과 평가 및 피드백
        4. Blue Team: 피드백 반영
        5. 리포트 생성
        """
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
            # Phase 1: Red Team - 합성 데이터 생성
            logger.info(f"[{run_id}] Phase 1: Red Team 시작 (count={count}, level={level})")

            # 알고리즘 기반 생성 (API 키 불필요, 빠름)
            self.runs[run_id]["message"] = f"합성 데이터 {count}개 생성 중..."
            data, data_path = generate_synthetic_data_local(count=count, level=level)

            logger.info(f"[{run_id}] Red Team 완료: {len(data)}개 생성")

            if not data:
                raise RuntimeError("합성 데이터가 생성되지 않았습니다.")

            # Phase 2: Blue Team - 필터링 실행
            self.runs[run_id]["phase"] = "blue_team"
            self.runs[run_id]["message"] = f"Blue Team 에이전트가 {len(data)}개 데이터 필터링 수행 중..."
            logger.info(f"[{run_id}] Phase 2: Blue Team 시작")

            blue_agent = BlueTeamAgent(level=level)
            results, metrics = blue_agent.evaluate_batch(data)

            self.runs[run_id]["metrics"] = metrics.to_dict()
            self.runs[run_id]["message"] = f"필터링 완료. F1: {metrics.f1_score:.4f}, Accuracy: {metrics.accuracy:.4f}"
            logger.info(f"[{run_id}] Blue Team 완료: {metrics.to_dict()}")

            # Phase 3: Judge - 결과 평가
            self.runs[run_id]["phase"] = "judge"
            self.runs[run_id]["message"] = "Judge 에이전트가 결과를 평가 중..."
            logger.info(f"[{run_id}] Phase 3: Judge 시작")

            feedback = await judge_results(results)
            logger.info(f"[{run_id}] Judge 완료: 오류 {feedback.get('total_errors', 0)}건")

            # Phase 4: Blue Team - 피드백 반영
            self.runs[run_id]["phase"] = "improvement"
            self.runs[run_id]["message"] = "Blue Team이 알고리즘을 개선 중..."

            if feedback.get("false_positive_feedback"):
                blue_agent.apply_feedback(feedback["false_positive_feedback"])
            if feedback.get("false_negative_feedback"):
                blue_agent.apply_feedback(feedback["false_negative_feedback"])

            # 개선 후 재평가
            results_v2, metrics_v2 = blue_agent.evaluate_batch(data)
            logger.info(f"[{run_id}] 개선 후 메트릭: {metrics_v2.to_dict()}")

            # Phase 5: 리포트 생성
            report = self._generate_report(
                run_id=run_id,
                count=count,
                level=level,
                metrics_before=metrics,
                metrics_after=metrics_v2,
                feedback=feedback,
                improvements=blue_agent.get_improvement_log(),
                data_path=str(data_path),
            )

            self.runs[run_id].update({
                "status": "completed",
                "phase": "done",
                "processed": count,
                "metrics": metrics_v2.to_dict(),
                "message": f"파이프라인 완료 (데이터 {len(data)}개, F1: {metrics_v2.f1_score:.4f})",
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
        feedback: dict,
        improvements: list,
        data_path: str,
    ) -> dict:
        """개선 리포트 생성"""
        report = {
            "id": run_id,
            "created_at": datetime.now().isoformat(),
            "config": {"count": count, "level": level},
            "data_path": data_path,
            "before": metrics_before.to_dict(),
            "after": metrics_after.to_dict(),
            "improvements": [
                {
                    "metric": "precision",
                    "before": metrics_before.precision,
                    "after": metrics_after.precision,
                    "delta": metrics_after.precision - metrics_before.precision,
                },
                {
                    "metric": "recall",
                    "before": metrics_before.recall,
                    "after": metrics_after.recall,
                    "delta": metrics_after.recall - metrics_before.recall,
                },
                {
                    "metric": "f1_score",
                    "before": metrics_before.f1_score,
                    "after": metrics_after.f1_score,
                    "delta": metrics_after.f1_score - metrics_before.f1_score,
                },
                {
                    "metric": "accuracy",
                    "before": metrics_before.accuracy,
                    "after": metrics_after.accuracy,
                    "delta": metrics_after.accuracy - metrics_before.accuracy,
                },
            ],
            "feedback_summary": {
                "total_errors": feedback.get("total_errors", 0),
                "false_positive_patterns": feedback.get("false_positive_feedback", {}).get("patterns", []),
                "false_negative_count": len(feedback.get("false_negative_feedback", {}).get("examples", [])),
                "suggestions": feedback.get("suggestions", []),
            },
            "improvement_log": improvements,
        }

        # 파일로 저장
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
