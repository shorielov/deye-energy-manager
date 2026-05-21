"""Tests for SunsynkAdapter."""

from __future__ import annotations

from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smart_energy_manager.adapters.sunsynk import SunsynkAdapter
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
    """Each slot → 3 service calls (time, number, switch) = 18 total."""
    hass = _hass()
    adapter = SunsynkAdapter()
    await adapter.async_apply_plan(hass, _plan())
    assert hass.services.async_call.call_count == 18


@pytest.mark.asyncio
async def test_apply_plan_sets_time_entity():
    hass = _hass()
    adapter = SunsynkAdapter()
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    # First call should be a time.set_value for slot 1
    first = calls[0]
    assert first.args[0] == "time"
    assert first.args[1] == "set_value"
    assert first.kwargs.get("blocking") is True


@pytest.mark.asyncio
async def test_apply_plan_charge_off_uses_turn_off():
    hass = _hass()
    adapter = SunsynkAdapter()
    await adapter.async_apply_plan(hass, _plan(charge=False))
    calls = hass.services.async_call.call_args_list
    # Third call per slot should be switch.turn_off
    switch_call = calls[2]
    assert switch_call.args[0] == "switch"
    assert switch_call.args[1] == "turn_off"


@pytest.mark.asyncio
async def test_apply_plan_charge_on_uses_turn_on():
    hass = _hass()
    adapter = SunsynkAdapter()
    await adapter.async_apply_plan(hass, _plan(charge=True))
    calls = hass.services.async_call.call_args_list
    switch_call = calls[2]
    assert switch_call.args[0] == "switch"
    assert switch_call.args[1] == "turn_on"


@pytest.mark.asyncio
async def test_apply_plan_with_prefix():
    hass = _hass()
    adapter = SunsynkAdapter(entity_prefix="inv_")
    await adapter.async_apply_plan(hass, _plan())
    calls = hass.services.async_call.call_args_list
    # time.set_value entity_id should include prefix
    first_kwargs = calls[0].args[2]
    assert "inv_prog1_time" in first_kwargs["entity_id"]


def test_is_available_true_when_entity_exists():
    hass = MagicMock()
    hass.states.get = MagicMock(return_value=MagicMock())
    assert SunsynkAdapter.is_available(hass) is True


def test_is_available_false_when_entity_missing():
    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    assert SunsynkAdapter.is_available(hass) is False


def test_adapter_name():
    assert SunsynkAdapter().name == "sunsynk"
