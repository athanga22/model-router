"""Data models."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ChatRequest(BaseModel):
    prompt: str
    user_id: Optional[str] = None

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