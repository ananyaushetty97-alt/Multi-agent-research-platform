"""
Gateway module exposing call_llm and request telemetry session controls.
"""
from gateway.llm_gateway import call_llm, start_llm_request_session, get_llm_request_telemetry

__all__ = ["call_llm", "start_llm_request_session", "get_llm_request_telemetry"]
