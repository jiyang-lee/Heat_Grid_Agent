from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def heatgrid_test_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    if "HEATGRID_DATABASE_URL" not in os.environ:
        monkeypatch.setenv(
            "HEATGRID_DATABASE_URL",
            "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops",
        )
    monkeypatch.setenv("HEATGRID_PRIORITY_STALE_AFTER_HOURS", "200000")
