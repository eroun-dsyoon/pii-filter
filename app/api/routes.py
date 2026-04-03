"""API 라우트 정의"""
from __future__ import annotations

import time
import uuid
import json
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks

from ..models.schemas import (
    DetectRequest, DetectResponse, PIIEntityResponse,
    FalsePositiveReport, FalsePositiveResponse,
    SyntheticDataRequest, AgentRunStatus,
)
from ..core.filter_engine import detect_pii
from ..agents.orchestrator import get_orchestrator
from ..config import DATA_DIR, REPORTS_DIR

router = APIRouter()


@router.post("/detect", response_model=DetectResponse)
async def detect(request: DetectRequest):
    """텍스트에서 PII 검출"""
    start = time.perf_counter()
    entities = detect_pii(request.text, level=request.level, strict=request.strict)
    elapsed = (time.perf_counter() - start) * 1000  # ms

    return DetectResponse(
        has_pii=len(entities) > 0,
        entities=[PIIEntityResponse(**e) for e in entities],
        elapsed_ms=round(elapsed, 3),
        text_length=len(request.text),
    )


@router.post("/detect/file", response_model=DetectResponse)
async def detect_file(file: UploadFile = File(...), level: int = 3):
    """파일에서 PII 검출"""
    content = await file.read()
    text = content.decode("utf-8", errors="ignore")

    start = time.perf_counter()
    entities = detect_pii(text, level=level)
    elapsed = (time.perf_counter() - start) * 1000

    return DetectResponse(
        has_pii=len(entities) > 0,
        entities=[PIIEntityResponse(**e) for e in entities],
        elapsed_ms=round(elapsed, 3),
        text_length=len(text),
    )


# 오탐 신고 저장소 (메모리 기반, 프로덕션에서는 DB 사용)
_fp_reports: list[dict] = []


@router.post("/report/false-positive", response_model=FalsePositiveResponse)
async def report_false_positive(report: FalsePositiveReport):
    """오탐 신고"""
    report_id = str(uuid.uuid4())[:8]
    _fp_reports.append({
        "id": report_id,
        "text": report.text,
        "entity": report.entity,
        "entity_type": report.entity_type,
        "reason": report.reason,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    })

    return FalsePositiveResponse(
        id=report_id,
        status="pending",
        message="오탐 신고가 접수되었습니다.",
    )


@router.get("/report/false-positives")
async def list_false_positives():
    """오탐 신고 목록 조회"""
    return _fp_reports


# === Admin 라우트 ===

@router.post("/admin/generate", response_model=AgentRunStatus)
async def start_generation(request: SyntheticDataRequest, background_tasks: BackgroundTasks):
    """합성 데이터 생성 및 모델 개선 파이프라인 시작"""
    orchestrator = get_orchestrator()

    # 백그라운드에서 파이프라인 실행
    run_id_future = asyncio.get_event_loop().create_future()

    async def run_pipeline():
        run_id = await orchestrator.run_pipeline(
            count=request.count,
            level=request.level,
        )
        if not run_id_future.done():
            run_id_future.set_result(run_id)

    task = asyncio.create_task(run_pipeline())

    # run_id 초기화를 기다림 (짧은 시간)
    await asyncio.sleep(0.1)

    # orchestrator에서 최신 run 가져오기
    runs = orchestrator.list_runs()
    if runs:
        latest = runs[-1]
        return AgentRunStatus(
            run_id=latest["run_id"],
            status=latest["status"],
            total=latest["total"],
            processed=latest["processed"],
            message=latest["message"],
            metrics=latest.get("metrics"),
        )

    return AgentRunStatus(
        run_id="pending",
        status="starting",
        total=request.count,
        processed=0,
        message="파이프라인 시작 중...",
    )


@router.get("/admin/status/{run_id}", response_model=AgentRunStatus)
async def get_run_status(run_id: str):
    """파이프라인 실행 상태 조회"""
    orchestrator = get_orchestrator()
    status = orchestrator.get_run_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="실행을 찾을 수 없습니다.")

    return AgentRunStatus(
        run_id=run_id,
        status=status["status"],
        total=status["total"],
        processed=status["processed"],
        message=status["message"],
        metrics=status.get("metrics"),
    )


@router.get("/admin/runs")
async def list_runs():
    """모든 파이프라인 실행 목록"""
    orchestrator = get_orchestrator()
    return orchestrator.list_runs()


@router.get("/admin/reports")
async def list_reports():
    """저장된 리포트 목록"""
    reports = []
    for f in sorted(REPORTS_DIR.glob("report_*.json"), reverse=True):
        try:
            with open(f, encoding="utf-8") as fp:
                report = json.load(fp)
                reports.append({
                    "id": report.get("id"),
                    "created_at": report.get("created_at"),
                    "config": report.get("config"),
                    "before": report.get("before"),
                    "after": report.get("after"),
                    "file": f.name,
                })
        except Exception:
            continue
    return reports


@router.get("/admin/reports/{report_id}")
async def get_report(report_id: str):
    """특정 리포트 상세 조회"""
    for f in REPORTS_DIR.glob(f"report_{report_id}_*.json"):
        with open(f, encoding="utf-8") as fp:
            return json.load(fp)
    raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")


@router.get("/admin/synthetic-data")
async def list_synthetic_data():
    """생성된 합성 데이터 파일 목록"""
    files = []
    for f in sorted(DATA_DIR.glob("synthetic_*.jsonl"), reverse=True):
        line_count = sum(1 for _ in open(f, encoding="utf-8"))
        files.append({
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "count": line_count,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return files
