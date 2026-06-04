"""Tests for balancing runtime in the coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.smart_energy_manager.const import CONF_MODE, DOMAIN, EnergyMode
from custom_components.smart_energy_manager.coordinator import SmartEnergyCoordinator


async def test_request_balance_sets_flag(
    hass: HomeAssistant, setup_integration
) -> None:
    """request_balance() should set _balance_requested and trigger a refresh."""
    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    assert coordinator._balance_requested is False
    await coordinator.request_balance()
    assert coordinator._balance_requested is True


async def test_cancel_balance_clears_flag(
    hass: HomeAssistant, setup_integration
) -> None:
    """cancel_balance() should clear the flag."""
    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    coordinator._balance_requested = True
    await coordinator.cancel_balance()
    assert coordinator._balance_requested is False


async def test_balancing_mode_plan_strategy(
    hass: HomeAssistant, setup_integration
) -> None:
    """When mode=BALANCING and imbalance is above trigger, plan strategy should be 'balancing'."""
    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    # Switch mode to BALANCING
    hass.config_entries.async_update_entry(
        coordinator.config_entry,
        options={**coordinator.config_entry.options, CONF_MODE: EnergyMode.BALANCING},
    )
    # Provide imbalance above default trigger (0.05)
    hass.states.async_set("sensor.battery_imbalance", "0.10")
    # Override config to point at the imbalance sensor
    hass.config_entries.async_update_entry(
        coordinator.config_entry,
        options={
            **coordinator.config_entry.options,
            CONF_MODE: EnergyMode.BALANCING,
            "balance_imbalance_entity": "sensor.battery_imbalance",
            "balance_trigger_threshold": 0.05,
        },
    )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    plan = coordinator.data.plan
    assert plan is not None
    assert plan.strategy == "balancing"


async def test_stop_condition_clears_requested_flag(
    hass: HomeAssistant, setup_integration
) -> None:
    """When imbalance drops below stop_threshold, _balance_requested should clear."""
    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    # Arm manually and set mode
    coordinator._balance_requested = True
    hass.config_entries.async_update_entry(
        coordinator.config_entry,
        options={
            **coordinator.config_entry.options,
            CONF_MODE: EnergyMode.BALANCING,
            "balance_imbalance_entity": "sensor.battery_imbalance",
            "balance_trigger_threshold": 0.05,
            "balance_stop_threshold": 0.02,
        },
    )
    # Imbalance below stop threshold
    hass.states.async_set("sensor.battery_imbalance", "0.01")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator._balance_requested is False
    assert coordinator._balance_last_run is not None


async def test_balance_state_exposed_on_energy_state(
    hass: HomeAssistant, setup_integration
) -> None:
    """balance_requested and balance_imbalance should appear on EnergyState."""
    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    state = coordinator.data
    assert hasattr(state, "balance_requested")
    assert hasattr(state, "balance_imbalance")
    assert hasattr(state, "balance_last_run")
