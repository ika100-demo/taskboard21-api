"""Smoke test for spec 002 (AC-002.6): readiness reaches the database, read-only."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.smoke
def test_smoke_ac_002_6_ready_is_200(smoke_base_url: str) -> None:
    response = httpx.get(smoke_base_url + "/ready", timeout=10)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
