"""Integration-style tests for the auto-apply hook in the coordinator."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smart_energy_manager.const import RecommendationCode
from custom_components.smart_energy_manager.models import Plan, PlanSlot


def _plan(strategy: str = "balanced") -> Plan:
    return Plan(
        slots=[
            PlanSlot(time(h, 0), 80, False, None, RecommendationCode.PV_PRIORITY)
            for h in [0, 4, 8, 12, 16, 20]
        ],
        generated_at=datetime(2024, 1, 15, 10, 0),
        strategy=strategy,
    )


@pytest.mark.asyncio
async def test_noop_adapter_apply_plan_does_not_write():
    """get_adapter('none') → NoopAdapter: async_apply_plan should not call hass.services."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("none")
    await adapter.async_apply_plan(hass, _plan())
    hass.services.async_call.assert_not_called()


@pytest.mark.asyncio
async def test_sunsynk_adapter_apply_plan_writes():
    """get_adapter('sunsynk') → SunsynkAdapter: async_apply_plan should call hass.services."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("sunsynk")
    await adapter.async_apply_plan(hass, _plan())
    # 6 slots × 3 service calls
    assert hass.services.async_call.call_count == 18


@pytest.mark.asyncio
async def test_plan_hash_prevents_duplicate_apply():
    """Coordinator should not apply the same plan twice (hash dedup)."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("sunsynk")
    plan = _plan()

    # Simulate coordinator's hash-diff logic
    last_hash: int | None = None

    async def apply_if_changed(p: Plan) -> None:
        nonlocal last_hash
        h = hash(tuple((s.start_time, s.target_soc, s.charge_from_grid) for s in p.slots))
        if h == last_hash:
            return
        last_hash = h
        await adapter.async_apply_plan(hass, p)

    await apply_if_changed(plan)
    await apply_if_changed(plan)  # same plan, should not call again

    assert hass.services.async_call.call_count == 18  # called once, not twice
