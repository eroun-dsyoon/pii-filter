"""Pydantic 스키마 정의"""
from typing import Optional, List
from pydantic import BaseModel, Field


class DetectRequest(BaseModel):
    text: str = Field(..., description="검사할 텍스트")
    level: int = Field(default=3, ge=1, le=3, description="검출 레벨 (1-3)")


class PIIEntityResponse(BaseModel):
    type: str
    entity: str
    start: int
    end: int
    normalized: Optional[str] = None
    level: int
    detail: Optional[dict] = None


class DetectResponse(BaseModel):
    has_pii: bool
    entities: List[PIIEntityResponse]
    elapsed_ms: float
    text_length: int


class FalsePositiveReport(BaseModel):
    text: str = Field(..., description="원본 텍스트")
    entity: str = Field(..., description="오탐으로 신고된 엔티티")
    entity_type: str = Field(..., description="엔티티 타입")
    reason: str = Field(default="", description="오탐 사유")


class FalsePositiveResponse(BaseModel):
    id: str
    status: str
    message: str


class SyntheticDataRequest(BaseModel):
    count: int = Field(default=1000, ge=1, le=100000, description="생성할 합성 데이터 수")
    level: int = Field(default=3, ge=1, le=3, description="타겟 검출 레벨")


class AgentRunStatus(BaseModel):
    run_id: str
    status: str
    total: int
    processed: int
    metrics: Optional[dict] = None
    message: str = ""


class ReportSummary(BaseModel):
    id: str
    created_at: str
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    false_positives: int
    false_negatives: int
    improvements: List[str]
