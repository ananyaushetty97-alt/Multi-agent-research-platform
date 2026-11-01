"""
Master APIRouter for the Admin Backend.

Combines all administrative sub-routers under /admin prefix:
- /admin/auth        Authentication, tokens, identity
- /admin/health      Deep dependency reachability probes
- /admin/metrics     Telemetry, latency percentiles, error rates
- /admin/quality     Evaluation scores, truncation heuristics, human reviews
- /admin/traces      Request traces & agent-step execution details
- /admin/safety      Blocked inputs/outputs & red-team summaries
- /admin/memory      Long-term memory, semantic cache, active session TTLs
- /admin/config      Draft system configurations & future limits
- /admin/export      CSV & JSON score/data exports
- /admin/audit       Audit trails of admin actions

STATUS: AWAITING INTEGRATION.
Do not mount this router in api/main.py until authorized by code review.
"""
from fastapi import APIRouter

from admin_backend.routes.auth_routes import router as auth_router
from admin_backend.routes.health_routes import router as health_router
from admin_backend.routes.metrics_routes import router as metrics_router
from admin_backend.routes.quality_routes import router as quality_router
from admin_backend.routes.trace_routes import router as trace_router
from admin_backend.routes.safety_routes import router as safety_router
from admin_backend.routes.memory_routes import router as memory_router
from admin_backend.routes.config_routes import router as config_router
from admin_backend.routes.export_routes import router as export_router
from admin_backend.routes.audit_routes import router as audit_router

admin_router = APIRouter(prefix="/admin")

# Mount sub-routers
admin_router.include_router(auth_router)
admin_router.include_router(health_router)
admin_router.include_router(metrics_router)
admin_router.include_router(quality_router)
admin_router.include_router(trace_router)
admin_router.include_router(safety_router)
admin_router.include_router(memory_router)
admin_router.include_router(config_router)
admin_router.include_router(export_router)
admin_router.include_router(audit_router)
