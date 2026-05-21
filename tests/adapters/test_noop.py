"""Tests for NoopAdapter."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.smart_energy_manager.adapters.noop import NoopAdapter
from custom_components.smart_energy_manager.const import RecommendationCode
from custom_components.smart_energy_manager.models import Plan, PlanSlot


def _plan() -> Plan:
    return Plan(
        slots=[
            PlanSlot(time(0, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(4, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(8, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(12, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(16, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(20, 0), 80, False, None, RecommendationCode.PV_PRIORITY),
        ],
        generated_at=datetime(2024, 1, 15, 10, 0),
        strategy="balanced",
    )


@pytest.mark.asyncio
async def test_noop_apply_plan_does_not_raise():
    adapter = NoopAdapter()
    hass = MagicMock()
    # Should complete without error
    await adapter.async_apply_plan(hass, _plan())


def test_noop_is_always_available():
    hass = MagicMock()
    assert NoopAdapter.is_available(hass) is True


def test_noop_name():
    assert NoopAdapter().name == "none"
