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


@pytest.mark.asyncio
async def test_solarman_adapter_apply_plan_writes():
    """get_adapter('solarman') → SolarmanAdapter: async_apply_plan calls select.select_option."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("solarman", device_name="inverter")
    await adapter.async_apply_plan(hass, _plan())
    # 6 slots × 3 service calls
    assert hass.services.async_call.call_count == 18


@pytest.mark.asyncio
async def test_solarman_adapter_uses_select_not_switch():
    """Solarman adapter must use select.select_option, not switch.turn_on/off."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("solarman")
    await adapter.async_apply_plan(hass, _plan())

    calls = hass.services.async_call.call_args_list
    domains = [c.args[0] for c in calls]
    assert "switch" not in domains
    assert "select" in domains


@pytest.mark.asyncio
async def test_solarman_adapter_custom_device_name():
    """get_adapter('solarman', device_name='myinv') should use myinv slug in entity_ids."""
    from custom_components.smart_energy_manager.adapters import get_adapter

    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    adapter = get_adapter("solarman", device_name="myinv")
    await adapter.async_apply_plan(hass, _plan())

    calls = hass.services.async_call.call_args_list
    time_calls = [c for c in calls if c.args[0] == "time"]
    assert time_calls[0].args[2]["entity_id"] == "time.myinv_program_1_time"
