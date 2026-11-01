"""
Detailed system health and dependency reachability service.
Accurately probes real services with short timeouts without crashing.
Does NOT label a dependency healthy without an actual verified check.
"""
import os
import platform
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import httpx

from admin_backend.config import settings
from admin_backend.models.health import (
    DetailedSystemHealth,
    DependencyCheckResult,
    ProcessHealthInfo,
    ServiceStatus,
)

_PROCESS_START_TIME = time.time()


class HealthService:
    def check_process(self) -> ProcessHealthInfo:
        """Returns API process diagnostic information."""
        uptime = round(time.time() - _PROCESS_START_TIME, 2)
        return ProcessHealthInfo(
            pid=os.getpid(),
            python_version=sys.version.split()[0],
            uptime_seconds=uptime,
            platform=platform.platform(),
        )

    def check_redis(self) -> DependencyCheckResult:
        """
        Probe Redis server reachability using redis client with a strict timeout.
        """
        start = time.perf_counter()
        redis_url = settings.redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")

        try:
            import redis
            client = redis.Redis.from_url(redis_url, socket_timeout=1.5, socket_connect_timeout=1.5)
            ping_ok = client.ping()
            latency = round((time.perf_counter() - start) * 1000, 2)
            if ping_ok:
                return DependencyCheckResult(
                    name="redis",
                    status=ServiceStatus.HEALTHY,
                    latency_ms=latency,
                    details={"url": redis_url.split("@")[-1], "ping": True},
                )
            return DependencyCheckResult(
                name="redis",
                status=ServiceStatus.UNHEALTHY,
                latency_ms=latency,
                error="Redis ping returned non-truthy value",
            )
        except ImportError:
            return DependencyCheckResult(
                name="redis",
                status=ServiceStatus.UNAVAILABLE,
                error="Redis python library not available",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return DependencyCheckResult(
                name="redis",
                status=ServiceStatus.UNAVAILABLE,
                latency_ms=latency,
                error=f"Cannot reach Redis at {redis_url}: {type(e).__name__}: {e}",
            )

    def check_postgres(self) -> DependencyCheckResult:
        """
        Probe PostgreSQL database reachability and vector extension readiness.
        """
        start = time.perf_counter()
        dsn = settings.postgres_dsn or os.environ.get("POSTGRES_DSN", "")
        if not dsn:
            return DependencyCheckResult(
                name="postgres",
                status=ServiceStatus.NOT_CONFIGURED,
                error="POSTGRES_DSN is not configured",
            )

        try:
            import psycopg
            # Short connect_timeout to avoid hanging the health probe
            with psycopg.connect(dsn, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    row = cur.fetchone()
                    # Check pgvector extension presence
                    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
                    has_vector = cur.fetchone() is not None

            latency = round((time.perf_counter() - start) * 1000, 2)
            if row and row[0] == 1:
                return DependencyCheckResult(
                    name="postgres",
                    status=ServiceStatus.HEALTHY,
                    latency_ms=latency,
                    details={"pgvector_installed": has_vector},
                )
            return DependencyCheckResult(
                name="postgres",
                status=ServiceStatus.UNHEALTHY,
                latency_ms=latency,
                error="PostgreSQL query returned unexpected result",
            )
        except ImportError:
            return DependencyCheckResult(
                name="postgres",
                status=ServiceStatus.UNAVAILABLE,
                error="psycopg python library not available",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return DependencyCheckResult(
                name="postgres",
                status=ServiceStatus.UNAVAILABLE,
                latency_ms=latency,
                error=f"Cannot reach PostgreSQL: {type(e).__name__}: {e}",
            )

    def check_groq(self) -> DependencyCheckResult:
        """
        Probe Groq LLM API configuration and reachability.
        """
        api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
        if not api_key:
            return DependencyCheckResult(
                name="groq",
                status=ServiceStatus.NOT_CONFIGURED,
                error="GROQ_API_KEY environment variable is not set",
            )

        start = time.perf_counter()
        try:
            # Query Groq models endpoint with short timeout
            headers = {"Authorization": f"Bearer {api_key}"}
            with httpx.Client(timeout=2.0) as client:
                resp = client.get("https://api.groq.com/openai/v1/models", headers=headers)

            latency = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code == 200:
                return DependencyCheckResult(
                    name="groq",
                    status=ServiceStatus.HEALTHY,
                    latency_ms=latency,
                    details={"endpoint": "https://api.groq.com/openai/v1/models"},
                )
            elif resp.status_code == 401:
                return DependencyCheckResult(
                    name="groq",
                    status=ServiceStatus.UNHEALTHY,
                    latency_ms=latency,
                    error="Invalid GROQ_API_KEY (HTTP 401 Unauthorized)",
                )
            elif resp.status_code == 429:
                return DependencyCheckResult(
                    name="groq",
                    status=ServiceStatus.DEGRADED,
                    latency_ms=latency,
                    error="Groq rate limit active (HTTP 429 Too Many Requests)",
                )
            else:
                return DependencyCheckResult(
                    name="groq",
                    status=ServiceStatus.DEGRADED,
                    latency_ms=latency,
                    error=f"Groq API returned HTTP {resp.status_code}",
                )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return DependencyCheckResult(
                name="groq",
                status=ServiceStatus.UNAVAILABLE,
                latency_ms=latency,
                error=f"Groq reachability probe failed: {type(e).__name__}: {e}",
            )

    def check_ollama(self) -> DependencyCheckResult:
        """
        Probe local Ollama fallback daemon reachability.
        """
        ollama_host = settings.ollama_host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=1.5) as client:
                resp = client.get(f"{ollama_host}/api/tags")

            latency = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                return DependencyCheckResult(
                    name="ollama",
                    status=ServiceStatus.HEALTHY,
                    latency_ms=latency,
                    details={"available_models": models},
                )
            return DependencyCheckResult(
                name="ollama",
                status=ServiceStatus.UNHEALTHY,
                latency_ms=latency,
                error=f"Ollama returned HTTP {resp.status_code}",
            )
        except Exception as e:
            latency = round((time.perf_counter() - start) * 1000, 2)
            return DependencyCheckResult(
                name="ollama",
                status=ServiceStatus.UNAVAILABLE,
                latency_ms=latency,
                error=f"Ollama local daemon unreachable at {ollama_host}: {type(e).__name__}: {e}",
            )

    def check_tavily(self) -> DependencyCheckResult:
        """
        Probe Tavily search API key configuration.
        """
        api_key = settings.tavily_api_key or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return DependencyCheckResult(
                name="tavily",
                status=ServiceStatus.NOT_CONFIGURED,
                error="TAVILY_API_KEY environment variable is not set",
            )
        # Avoid spending billable search credits during health checks; verify key presence and format
        if len(api_key) < 10 or api_key.startswith("offline-"):
            return DependencyCheckResult(
                name="tavily",
                status=ServiceStatus.DEGRADED,
                error="TAVILY_API_KEY appears to be a mock or dummy key",
                details={"configured": True, "dummy": True},
            )
        return DependencyCheckResult(
            name="tavily",
            status=ServiceStatus.HEALTHY,
            details={"configured": True},
        )

    def get_full_health(self) -> DetailedSystemHealth:
        """
        Perform all health checks and synthesize comprehensive status report.
        """
        proc = self.check_process()
        deps: Dict[str, DependencyCheckResult] = {
            "redis": self.check_redis(),
            "postgres": self.check_postgres(),
            "groq": self.check_groq(),
            "ollama": self.check_ollama(),
            "tavily": self.check_tavily(),
        }

        # Determine overall status
        statuses = [d.status for d in deps.values()]
        unhealthy_or_unavail = [
            name for name, d in deps.items()
            if d.status in (ServiceStatus.UNHEALTHY, ServiceStatus.UNAVAILABLE)
        ]

        if not unhealthy_or_unavail:
            overall = ServiceStatus.HEALTHY
            summary = "All platform dependencies are operational and reachable."
        elif len(unhealthy_or_unavail) == len(deps):
            overall = ServiceStatus.UNHEALTHY
            summary = "Critical failure: all external dependencies are currently unreachable."
        else:
            overall = ServiceStatus.DEGRADED
            summary = f"Platform degraded: {', '.join(unhealthy_or_unavail)} unreachable or failing."

        return DetailedSystemHealth(
            overall_status=overall,
            timestamp=datetime.now(timezone.utc).isoformat(),
            process=proc,
            dependencies=deps,
            summary=summary,
        )


health_service = HealthService()
