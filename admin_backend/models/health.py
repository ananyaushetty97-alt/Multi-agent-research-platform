"""
System health and dependency reachability models.
"""
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class DependencyCheckResult(BaseModel):
    name: str = Field(..., description="Name of dependency: redis, postgres, groq, ollama, tavily")
    status: ServiceStatus
    latency_ms: Optional[float] = Field(None, description="Probe round-trip duration in milliseconds")
    error: Optional[str] = Field(None, description="Detailed error message if unreachable")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic metadata")


class ProcessHealthInfo(BaseModel):
    pid: int
    python_version: str
    uptime_seconds: float
    platform: str


class DetailedSystemHealth(BaseModel):
    overall_status: ServiceStatus
    timestamp: str
    process: ProcessHealthInfo
    dependencies: Dict[str, DependencyCheckResult]
    summary: str
