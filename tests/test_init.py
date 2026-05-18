"""Tests for integration setup."""

from __future__ import annotations

from homeassistant.core import HomeAssistant


async def test_setup_entry_creates_entities(hass: HomeAssistant, setup_integration) -> None:
    """Ensure the config entry sets up the core entities."""

    assert hass.states.get("sensor.smart_energy_manager_target_soc") is not None
    assert hass.states.get("binary_sensor.smart_energy_manager_should_charge") is not None
    assert hass.states.get("switch.smart_energy_manager_eco_mode") is not None
    assert hass.states.get("number.smart_energy_manager_target_soc_override") is not None