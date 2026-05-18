"""Tests for the Smart Energy coordinator."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.smart_energy_manager.const import DOMAIN
from custom_components.smart_energy_manager.coordinator import SmartEnergyCoordinator


async def test_coordinator_builds_recommendation(
    hass: HomeAssistant, setup_integration
) -> None:
    """Coordinator should expose placeholder recommendation data."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    assert coordinator.data.recommendation.target_soc == 80
    assert coordinator.data.recommendation.energy_deficit is True
    assert coordinator.data.recommendation.should_charge is True
    assert coordinator.data.forecast.confidence == 1.0