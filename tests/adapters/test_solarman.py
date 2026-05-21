"""Tests for SolarmanAdapter."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smart_energy_manager.adapters.solarman import SolarmanAdapter
from custom_components.smart_energy_manager.const import RecommendationCode
from custom_components.smart_energy_manager.models import Plan, PlanSlot


def _plan(charge: bool = False) -> Plan:
    return Plan(
        slots=[
            PlanSlot(time(h, 0), 80, charge, None, RecommendationCode.PV_PRIORITY)
            for h in [0, 4, 8, 12, 16, 20]
        ],
        generated_at=datetime(2024, 1, 15, 10, 0),
        strategy="balanced",
    )


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=MagicMock())  # entity exists
    return hass


@pytest.mark.asyncio
async def test_apply_plan_calls_correct_number_of_services():
    """Each slot → 3 service calls (time, number, select) = 18 total."""
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan())
    assert hass.services.async_call.call_count == 18


@pytest.mark.asyncio
async def test_apply_plan_sets_time_entity():
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    # First call should be time.set_value for slot 1
    first = calls[0]
    assert first.args[0] == "time"
    assert first.args[1] == "set_value"
    assert first.args[2]["entity_id"] == "time.inverter_program_1_time"
    assert first.kwargs.get("blocking") is True


@pytest.mark.asyncio
async def test_apply_plan_sets_soc_entity():
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    # Second call per slot should be number.set_value
    second = calls[1]
    assert second.args[0] == "number"
    assert second.args[1] == "set_value"
    assert second.args[2]["entity_id"] == "number.inverter_program_1_soc"


@pytest.mark.asyncio
async def test_apply_plan_charge_off_uses_disabled():
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan(charge=False))
    calls = hass.services.async_call.call_args_list
    # Third call per slot should be select.select_option with "Disabled"
    third = calls[2]
    assert third.args[0] == "select"
    assert third.args[1] == "select_option"
    assert third.args[2]["option"] == "Disabled"
    assert third.args[2]["entity_id"] == "select.inverter_program_1_charging"


@pytest.mark.asyncio
async def test_apply_plan_charge_on_uses_grid():
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan(charge=True))
    calls = hass.services.async_call.call_args_list
    third = calls[2]
    assert third.args[0] == "select"
    assert third.args[1] == "select_option"
    assert third.args[2]["option"] == "Grid"


@pytest.mark.asyncio
async def test_apply_plan_with_custom_device_name():
    hass = _hass()
    adapter = SolarmanAdapter(device_name="myinv")
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    first_kwargs = calls[0].args[2]
    assert "myinv_program_1_time" in first_kwargs["entity_id"]


@pytest.mark.asyncio
async def test_apply_plan_writes_all_six_slots():
    hass = _hass()
    adapter = SolarmanAdapter()
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    # Check time entity_ids for all 6 slots
    time_calls = [c for c in calls if c.args[0] == "time"]
    assert len(time_calls) == 6
    for n, call in enumerate(time_calls, start=1):
        assert call.args[2]["entity_id"] == f"time.inverter_program_{n}_time"


def test_is_available_true_when_entity_exists():
    hass = MagicMock()
    hass.states.get = MagicMock(return_value=MagicMock())
    assert SolarmanAdapter.is_available(hass) is True


def test_is_available_false_when_entity_missing():
    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    assert SolarmanAdapter.is_available(hass) is False


def test_adapter_name():
    assert SolarmanAdapter().name == "solarman"


def test_default_device_name_slug():
    adapter = SolarmanAdapter()
    assert adapter._slug == "inverter"


def test_custom_device_name_slug():
    adapter = SolarmanAdapter(device_name="Deye SG04")
    assert adapter._slug == "deye_sg04"
