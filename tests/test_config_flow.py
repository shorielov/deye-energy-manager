"""Tests for the Smart Energy config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.smart_energy_manager.const import DOMAIN


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The initial config flow should create a config entry."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "battery_soc_entity": "sensor.battery_soc",
            "battery_power_entity": "sensor.battery_power",
            "battery_capacity_kwh": 12.5,
            "pv_power_entity": "sensor.pv_power",
            "pv_generation_today_entity": "sensor.pv_generation_today",
            "grid_import_entity": "sensor.grid_import",
            "grid_export_entity": "sensor.grid_export",
            "home_consumption_entity": "sensor.home_consumption",
            "forecast_today_entity": "sensor.forecast_today",
            "forecast_tomorrow_entity": "sensor.forecast_tomorrow",
            "forecast_remaining_entity": "sensor.forecast_remaining",
            "tariff_type": "flat",
            "flat_rate": 4.5,
            "day_rate": 0.0,
            "night_rate": 0.0,
            "night_start": "23:00:00",
            "night_end": "07:00:00",
            "mode": "balanced",
            "auto_apply_recommendations": False,
            "scan_interval_seconds": 60,
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Smart Energy Manager"