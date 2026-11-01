"""
Read-only draft schemas for future system configuration.
These schemas define future contracts for cache thresholds, model selection,
and retry limits WITHOUT modifying active runtime settings.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class CacheConfigDraft(BaseModel):
    similarity_threshold: float = Field(0.90, ge=0.5, le=1.0)
    ttl_seconds: int = Field(86400, ge=60)
    max_entries_estimate: int = 10_000


class ModelRoutingConfigDraft(BaseModel):
    primary_provider: str = Field("groq", description="Primary LLM provider")
    primary_model: str = Field("qwen/qwen3.8-27b", description="Primary model name")
    fallback_provider: str = Field("ollama", description="Fallback provider")
    fallback_model: str = Field("qwen2.5:7b", description="Fallback model name")
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(900, ge=100, le=4096)


class SearchConfigDraft(BaseModel):
    provider: str = "tavily"
    max_results: int = Field(5, ge=1, le=20)
    search_timeout_seconds: float = Field(10.0, ge=1.0, le=60.0)


class PipelineLimitsDraft(BaseModel):
    max_revisions: int = Field(2, ge=0, le=5)
    min_report_length: int = Field(50, ge=10)
    use_llm_guards: bool = True


class FutureExtensibilityDraft(BaseModel):
    """
    Scaffolding for future platform features: quotas, alerts, retention, deletion requests.
    """
    user_quotas_enabled: bool = False
    max_requests_per_user_day: int = 50
    alert_email_webhook: Optional[str] = None
    audit_retention_days: int = 90
    gdpr_deletion_workflow_enabled: bool = False


class SystemConfigDraft(BaseModel):
    version: str = "1.0.0-draft"
    is_active: bool = False
    notice: str = "This configuration is draft/scaffolding and does not mutate runtime behavior."
    cache: CacheConfigDraft = Field(default_factory=CacheConfigDraft)
    models: ModelRoutingConfigDraft = Field(default_factory=ModelRoutingConfigDraft)
    search: SearchConfigDraft = Field(default_factory=SearchConfigDraft)
    pipeline: PipelineLimitsDraft = Field(default_factory=PipelineLimitsDraft)
    future_features: FutureExtensibilityDraft = Field(default_factory=FutureExtensibilityDraft)
