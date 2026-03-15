"""Data models."""
from pydantic import BaseModel, Field
from datetime import datetime


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)


class ChatResponse(BaseModel):
    response: str
    model_used: str
    difficulty_tag: str
    cost_usd: float
    latency_ms: int
    escalated: bool = False

class HealthResponse(BaseModel):
    status: str
    db: str
    classifier: str

class StatsResponse(BaseModel):
    total_requests: int
    total_cost_usd: float
    total_cost_saved_usd: float
    model_usage: dict
    escalation_rate: float
    # Time series of savings by hour for dashboard
    savings_ts: list[dict] = []


class RecentRequest(BaseModel):
    created_at: datetime
    difficulty_tag: str
    model_used: str
    cost_usd: float
    cost_saved_usd: float
    latency_ms: int
    escalated: bool


class FeedbackRequest(BaseModel):
    request_id: int
    feedback: int  # 1 = thumbs up, -1 = thumbs down
