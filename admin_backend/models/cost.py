"""
Token and cost tracking schemas.
Clearly distinguishes exact provider-reported values from estimates and unavailable figures.
"""
from typing import Optional
from pydantic import BaseModel, Field


class TokenUsageRecord(BaseModel):
    request_id: str
    provider: str
    model: str
    prompt_tokens: Optional[int] = Field(None, description="Reported prompt tokens or None if unavailable")
    completion_tokens: Optional[int] = Field(None, description="Reported completion tokens or None if unavailable")
    total_tokens: Optional[int] = Field(None, description="Sum of tokens or estimate")
    is_exact_provider_usage: bool = Field(
        False,
        description="True only if provider API returned exact token usage; False if estimated or unavailable"
    )
    estimated_cost_usd: Optional[float] = Field(
        None,
        description="Estimated cost in USD based on published rates. Marked None if pricing is unavailable."
    )
    cost_calculation_notice: str = Field(
        "Estimate only: groq/ollama free tiers or local execution may incur $0.00 actual expense.",
        description="Transparent notice regarding cost calculation reliability"
    )
