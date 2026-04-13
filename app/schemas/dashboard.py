from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class KPIResponse(BaseModel):
    total_deals: int
    active_deals: int
    total_pipeline_value: float
    avg_score: Optional[float] = None
    deals_by_status: dict[str, int]


class TopOpportunity(BaseModel):
    deal_id: str
    name: str
    property_type: Optional[str] = None
    asking_price: Optional[float] = None
    score: Optional[float] = None
    status: str


class PipelineSnapshot(BaseModel):
    stage: str
    count: int
    total_value: float


class RecentSignal(BaseModel):
    id: str
    deal_id: Optional[str] = None
    deal_name: Optional[str] = None
    signal_type: str
    source: Optional[str] = None
    severity: Optional[float] = None
    created_at: datetime


class AIInsight(BaseModel):
    insight_type: str
    title: str
    description: str
    deal_id: Optional[str] = None
    priority: str = "medium"
