"""Tests for the Smart Energy config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_energy_manager.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_FLAT_RATE,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_HOME_CONSUMPTION_ENTITY,
    CONF_MODE,
    CONF_PV_GENERATION_TODAY_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_TARIFF_TYPE,
    DOMAIN,
    EnergyMode,
    TariffType,
)


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


_FULL_CONFIG = {
    CONF_BATTERY_SOC_ENTITY: "sensor.battery_soc",
    CONF_BATTERY_POWER_ENTITY: "sensor.battery_power",
    CONF_BATTERY_CAPACITY_KWH: 12.5,
    CONF_PV_POWER_ENTITY: "sensor.pv_power",
    CONF_PV_GENERATION_TODAY_ENTITY: "sensor.pv_generation_today",
    CONF_GRID_IMPORT_ENTITY: "sensor.grid_import",
    CONF_GRID_EXPORT_ENTITY: "sensor.grid_export",
    CONF_HOME_CONSUMPTION_ENTITY: "sensor.home_consumption",
    CONF_FORECAST_TODAY_ENTITY: "sensor.forecast_today",
    CONF_FORECAST_TOMORROW_ENTITY: "sensor.forecast_tomorrow",
    CONF_FORECAST_REMAINING_ENTITY: "sensor.forecast_remaining",
    CONF_TARIFF_TYPE: TariffType.FLAT.value,
    CONF_FLAT_RATE: 4.5,
    "day_rate": 0.0,
    "night_rate": 0.0,
    "night_start": "23:00:00",
    "night_end": "07:00:00",
    CONF_MODE: EnergyMode.BALANCED.value,
    "auto_apply_recommendations": False,
    CONF_SCAN_INTERVAL_SECONDS: 60,
}


async def test_options_flow_opens_form(hass: HomeAssistant) -> None:
    """Options flow should open the init form without raising 500."""

    entry = MockConfigEntry(domain=DOMAIN, title="Smart Energy Manager", data=_FULL_CONFIG)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"


async def test_options_flow_saves_changes(hass: HomeAssistant) -> None:
    """Submitting options flow should persist updated values in entry.options."""

    entry = MockConfigEntry(domain=DOMAIN, title="Smart Energy Manager", data=_FULL_CONFIG)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    updated = dict(_FULL_CONFIG)
    updated[CONF_BATTERY_CAPACITY_KWH] = 20.0
    updated[CONF_MODE] = EnergyMode.ECO.value

    result = await hass.config_entries.options.async_configure(result["flow_id"], updated)

    assert result["type"] == "create_entry"
    assert entry.options[CONF_BATTERY_CAPACITY_KWH] == 20.0
    assert entry.options[CONF_MODE] == EnergyMode.ECO.value