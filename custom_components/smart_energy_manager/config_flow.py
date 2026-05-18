"""Config flow for Smart Energy Manager."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_AUTO_APPLY_RECOMMENDATIONS,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_TEMPERATURE_ENTITY,
    CONF_DAY_RATE,
    CONF_FLAT_RATE,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_HOME_CONSUMPTION_ENTITY,
    CONF_MODE,
    CONF_NIGHT_END,
    CONF_NIGHT_RATE,
    CONF_NIGHT_START,
    CONF_PV_GENERATION_TODAY_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_TARIFF_TYPE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    EnergyMode,
    TariffType,
)


def _build_schema(user_input: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build a simple config form schema."""

    user_input = user_input or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_BATTERY_SOC_ENTITY,
                default=user_input.get(CONF_BATTERY_SOC_ENTITY, "sensor.battery_soc"),
            ): str,
            vol.Required(
                CONF_BATTERY_POWER_ENTITY,
                default=user_input.get(CONF_BATTERY_POWER_ENTITY, "sensor.battery_power"),
            ): str,
            vol.Optional(
                CONF_BATTERY_TEMPERATURE_ENTITY,
                default=user_input.get(CONF_BATTERY_TEMPERATURE_ENTITY, ""),
            ): str,
            vol.Required(
                CONF_BATTERY_CAPACITY_KWH,
                default=user_input.get(CONF_BATTERY_CAPACITY_KWH, 10.0),
            ): vol.Coerce(float),
            vol.Required(
                CONF_PV_POWER_ENTITY,
                default=user_input.get(CONF_PV_POWER_ENTITY, "sensor.pv_power"),
            ): str,
            vol.Required(
                CONF_PV_GENERATION_TODAY_ENTITY,
                default=user_input.get(CONF_PV_GENERATION_TODAY_ENTITY, "sensor.pv_generation_today"),
            ): str,
            vol.Required(
                CONF_GRID_IMPORT_ENTITY,
                default=user_input.get(CONF_GRID_IMPORT_ENTITY, "sensor.grid_import"),
            ): str,
            vol.Required(
                CONF_GRID_EXPORT_ENTITY,
                default=user_input.get(CONF_GRID_EXPORT_ENTITY, "sensor.grid_export"),
            ): str,
            vol.Required(
                CONF_HOME_CONSUMPTION_ENTITY,
                default=user_input.get(CONF_HOME_CONSUMPTION_ENTITY, "sensor.home_consumption"),
            ): str,
            vol.Required(
                CONF_FORECAST_TODAY_ENTITY,
                default=user_input.get(CONF_FORECAST_TODAY_ENTITY, "sensor.solar_forecast_today"),
            ): str,
            vol.Required(
                CONF_FORECAST_TOMORROW_ENTITY,
                default=user_input.get(CONF_FORECAST_TOMORROW_ENTITY, "sensor.solar_forecast_tomorrow"),
            ): str,
            vol.Optional(
                CONF_FORECAST_REMAINING_ENTITY,
                default=user_input.get(CONF_FORECAST_REMAINING_ENTITY, "sensor.solar_forecast_remaining"),
            ): str,
            vol.Required(
                CONF_TARIFF_TYPE,
                default=user_input.get(CONF_TARIFF_TYPE, TariffType.FLAT),
            ): vol.In([tariff.value for tariff in TariffType]),
            vol.Optional(
                CONF_FLAT_RATE,
                default=user_input.get(CONF_FLAT_RATE, 0.0),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_DAY_RATE,
                default=user_input.get(CONF_DAY_RATE, 0.0),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_NIGHT_RATE,
                default=user_input.get(CONF_NIGHT_RATE, 0.0),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_NIGHT_START,
                default=user_input.get(CONF_NIGHT_START, "23:00:00"),
            ): str,
            vol.Optional(
                CONF_NIGHT_END,
                default=user_input.get(CONF_NIGHT_END, "07:00:00"),
            ): str,
            vol.Required(
                CONF_MODE,
                default=user_input.get(CONF_MODE, EnergyMode.BALANCED),
            ): vol.In([mode.value for mode in EnergyMode]),
            vol.Required(
                CONF_AUTO_APPLY_RECOMMENDATIONS,
                default=user_input.get(CONF_AUTO_APPLY_RECOMMENDATIONS, False),
            ): bool,
            vol.Required(
                CONF_SCAN_INTERVAL_SECONDS,
                default=user_input.get(CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL_SECONDS),
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
        }
    )


class SmartEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Energy Manager."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        """Handle the initial step."""

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Smart Energy Manager", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_build_schema())

    async def async_step_import(self, import_config: dict[str, Any]) -> config_entries.FlowResult:
        """Import configuration from YAML."""

        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(updates=import_config)
        return self.async_create_entry(title="Smart Energy Manager", data=import_config)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""

        return SmartEnergyOptionsFlow(config_entry)


class SmartEnergyOptionsFlow(config_entries.OptionsFlow):
    """Handle Smart Energy Manager options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""

        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.FlowResult:
        """Manage the integration options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_build_schema(merged))