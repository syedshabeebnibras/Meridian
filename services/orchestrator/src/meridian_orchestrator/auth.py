"""Internal authentication for backend-only routes.

Meridian's orchestrator is designed to sit **behind** a trusted edge
(the Next.js server in ``apps/web`` in this repo, or any future API
gateway). The edge forwards requests with a shared secret header;
the orchestrator verifies that secret before running the state
machine.

Fail-closed semantics
---------------------
In staging and production, booting without ``ORCH_INTERNAL_KEY`` is a
hard error. A silent default would let anyone with network reachability
call ``/v1/chat`` and burn model budget.

In dev/test/CI the operator can opt into an insecure mode explicitly by
setting **both**:

    MERIDIAN_ENV=dev|test|ci         (default is "staging")
    MERIDIAN_ALLOW_UNAUTH_INTERNAL=true

The two-flag handshake makes it impossible to disable auth in prod by
flipping a single variable.

Routes exempt from the dependency:
    /healthz  — liveness probe (must work without secrets)
    /readyz   — readiness probe
    /metrics  — Prometheus scrape (scrape over a private network)
    /docs     — OpenAPI (disabled in prod via FastAPI config)
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

logger = logging.getLogger("meridian.auth")


class InternalAuthConfigError(RuntimeError):
    """Raised at boot if auth is misconfigured (e.g. prod with no key)."""


# Environments where we allow the dev escape hatch.
_DEV_ENVIRONMENTS = frozenset({"dev", "development", "test", "ci", "local"})


@dataclass(frozen=True)
class InternalAuthConfig:
    """Resolved internal-auth settings for a single app instance.

    Built once at boot via ``InternalAuthConfig.from_env()``; the
    ``require_internal_key`` dependency closes over the resulting object.
    """

    expected_key: str
    environment: str
    # When True, requests without a valid key are accepted with a warning log.
    # Only ever True in dev/test/CI when MERIDIAN_ALLOW_UNAUTH_INTERNAL=true.
    dev_mode: bool

    @classmethod
    def from_env(cls) -> InternalAuthConfig:
        env = os.environ.get("MERIDIAN_ENV", "staging").lower()
        key = os.environ.get("ORCH_INTERNAL_KEY", "")
        allow_unauth = os.environ.get("MERIDIAN_ALLOW_UNAUTH_INTERNAL", "").lower() in (
            "1",
            "true",
            "yes",
        )

        dev_mode = env in _DEV_ENVIRONMENTS and allow_unauth

        if not key and not dev_mode:
            # Fail closed. A prod deploy without a key must not boot.
            raise InternalAuthConfigError(
                "ORCH_INTERNAL_KEY is required in MERIDIAN_ENV="
                f"{env!r}. Set a high-entropy secret, or set "
                "MERIDIAN_ENV to dev/test/ci AND "
                "MERIDIAN_ALLOW_UNAUTH_INTERNAL=true to bypass in local dev."
            )

        if dev_mode and not key:
            logger.warning(
                "Orchestrator booting in INSECURE dev mode "
                "(MERIDIAN_ENV=%s, MERIDIAN_ALLOW_UNAUTH_INTERNAL=true). "
                "Protected routes accept any caller. Never run this in prod.",
                env,
            )

        return cls(expected_key=key, environment=env, dev_mode=dev_mode)


def build_require_internal_key(
    config: InternalAuthConfig,
) -> Callable[[str | None], Awaitable[None]]:
    """Return a FastAPI dependency that enforces ``X-Internal-Key``.

    We build the dependency as a closure over ``config`` so each app
    instance can have its own auth policy (e.g. tests can pass a
    permissive config without mutating env vars).
    """

    async def require_internal_key(
        x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
    ) -> None:
        if config.dev_mode and not config.expected_key:
            # Dev escape hatch. Already logged at boot.
            return

        if x_internal_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Internal-Key header.",
            )

        # Constant-time comparison to avoid timing side channels.
        if not hmac.compare_digest(x_internal_key, config.expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Internal-Key.",
            )

    return require_internal_key
