"""ASGI entrypoint for uvicorn.

The Dockerfile's CMD points at this module; uvicorn imports ``app`` and
serves it. Every dependency is constructed in ``wiring.py`` — this file
is intentionally thin so the production wiring is reviewable in one
place.

For tests, use ``meridian_orchestrator.api.build_app`` directly with a
hand-built ``Orchestrator``.
"""

from __future__ import annotations

from fastapi import FastAPI

from meridian_orchestrator.wiring import build_app_from_env

app: FastAPI
app, _capabilities = build_app_from_env()
