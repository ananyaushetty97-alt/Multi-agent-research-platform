"""
Admin Backend Module for Multi-Agent Research Platform.

STATUS: INTEGRATED.
This module is connected to the primary FastAPI application in api/main.py.
It exposes administrative endpoints for authentication, system health,
quality scores, request tracing, safety events, and memory/cache management.
"""

from admin_backend.router import admin_router

__version__ = "1.0.0"
__integrated__ = True

__all__ = ["admin_router", "__version__", "__integrated__"]

