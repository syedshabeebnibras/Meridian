"""Shared test fixtures.

Sets ``MERIDIAN_ENV=test`` and enables the dev auth bypass so tests that
build the FastAPI app don't have to pass an explicit ``auth_config``.
Tests that specifically exercise internal-auth behaviour construct their
own ``InternalAuthConfig`` and pass it to ``build_app``.
"""

from __future__ import annotations

import os

# Pytest imports this module before collection — setting env here ensures
# InternalAuthConfig.from_env() in fixtures/helpers evaluates correctly.
os.environ.setdefault("MERIDIAN_ENV", "test")
os.environ.setdefault("MERIDIAN_ALLOW_UNAUTH_INTERNAL", "true")
