"""Coordinator for Smart Energy Manager."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
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
    CONF_MIN_SOC_OVERRIDE,
    CONF_MODE,
    CONF_NIGHT_END,
    CONF_NIGHT_RATE,
    CONF_NIGHT_START,
    CONF_PV_GENERATION_TODAY_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SCAN_INTERVAL_SECONDS,
    CONF_TARGET_SOC_OVERRIDE,
    CONF_TARIFF_TYPE,
    DEFAULT_BATTERY_TEMPERATURE_C,
    DEFAULT_MIN_SOC,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TARGET_SOC,
    DOMAIN,
    EnergyMode,
    TariffType,
)
from .models import BatteryConfig, EnergyState, ForecastSnapshot, Recommendation, TariffConfig, TelemetrySnapshot

_LOGGER = logging.getLogger(__name__)


def _float_state(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Read a state and coerce it to float."""

    if not entity_id:
        return None

    state = hass.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable"}:
        return None

    try:
        return float(state.state)
    except ValueError:
        _LOGGER.debug("Unable to parse %s=%s as float", entity_id, state.state)
        return None


class SmartEnergyCoordinator(DataUpdateCoordinator[EnergyState]):
    """Fetch and normalize telemetry for Smart Energy Manager."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""

        self.config_entry = config_entry
        scan_interval_seconds = config_entry.options.get(
            CONF_SCAN_INTERVAL_SECONDS,
            config_entry.data.get(CONF_SCAN_INTERVAL_SECONDS, DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL if scan_interval_seconds == DEFAULT_SCAN_INTERVAL_SECONDS else None,
        )
        if scan_interval_seconds != DEFAULT_SCAN_INTERVAL_SECONDS:
            self.update_interval = DEFAULT_SCAN_INTERVAL.__class__(seconds=scan_interval_seconds)

        self._telemetry_history: deque[TelemetrySnapshot] = deque(maxlen=24 * 60)

    async def _async_update_data(self) -> EnergyState:
        """Fetch states from Home Assistant and build a normalized payload."""

        telemetry = TelemetrySnapshot(
            battery_soc=_float_state(self.hass, self._get_value(CONF_BATTERY_SOC_ENTITY)),
            battery_power_kw=_float_state(self.hass, self._get_value(CONF_BATTERY_POWER_ENTITY)),
            battery_temperature_c=_float_state(self.hass, self._get_value(CONF_BATTERY_TEMPERATURE_ENTITY))
            or DEFAULT_BATTERY_TEMPERATURE_C,
            pv_power_kw=_float_state(self.hass, self._get_value(CONF_PV_POWER_ENTITY)),
            pv_generation_today_kwh=_float_state(self.hass, self._get_value(CONF_PV_GENERATION_TODAY_ENTITY)),
            grid_import_kwh=_float_state(self.hass, self._get_value(CONF_GRID_IMPORT_ENTITY)),
            grid_export_kwh=_float_state(self.hass, self._get_value(CONF_GRID_EXPORT_ENTITY)),
            home_consumption_kw=_float_state(self.hass, self._get_value(CONF_HOME_CONSUMPTION_ENTITY)),
            updated_at=datetime.now(UTC),
        )

        if telemetry.battery_soc is None:
            raise UpdateFailed("Battery SOC entity returned no usable state")

        forecast = ForecastSnapshot(
            today_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_TODAY_ENTITY)),
            tomorrow_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_TOMORROW_ENTITY)),
            remaining_today_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_REMAINING_ENTITY)),
        )
        forecast = replace(
            forecast,
            confidence=self._estimate_forecast_confidence(forecast),
            degrading=self._is_forecast_degrading(forecast),
        )

        self._telemetry_history.append(telemetry)

        recommendation = self._build_placeholder_recommendation(telemetry, forecast)
        return EnergyState(
            telemetry=telemetry,
            forecast=forecast,
            recommendation=recommendation,
            tariff=self._build_tariff_config(),
            battery=self._build_battery_config(),
            last_update_success=True,
        )

    async def async_clear_history(self) -> None:
        """Clear in-memory history."""

        self._telemetry_history.clear()
        await self.async_request_refresh()

    def _get_value(self, key: str) -> Any:
        """Return the merged value from options or data."""

        return self.config_entry.options.get(key, self.config_entry.data.get(key))

    def _build_tariff_config(self) -> TariffConfig:
        """Resolve tariff config from entry data."""

        tariff_type = TariffType(self._get_value(CONF_TARIFF_TYPE) or TariffType.FLAT)
        return TariffConfig(
            tariff_type=tariff_type,
            flat_rate=self._safe_float(self._get_value(CONF_FLAT_RATE)),
            day_rate=self._safe_float(self._get_value(CONF_DAY_RATE)),
            night_rate=self._safe_float(self._get_value(CONF_NIGHT_RATE)),
            night_start=self._get_value(CONF_NIGHT_START),
            night_end=self._get_value(CONF_NIGHT_END),
        )

    def _build_battery_config(self) -> BatteryConfig:
        """Resolve battery configuration from entry data."""

        capacity = self._safe_float(self._get_value(CONF_BATTERY_CAPACITY_KWH))
        if capacity is None:
            raise UpdateFailed("Battery capacity is not configured")

        return BatteryConfig(
            capacity_kwh=capacity,
            min_soc_override=self._safe_int(self._get_value(CONF_MIN_SOC_OVERRIDE)),
            target_soc_override=self._safe_int(self._get_value(CONF_TARGET_SOC_OVERRIDE)),
        )

    def _build_placeholder_recommendation(
        self,
        telemetry: TelemetrySnapshot,
        forecast: ForecastSnapshot,
    ) -> Recommendation:
        """Return a minimal recommendation until the decision engine is implemented."""

        target_soc = self._safe_int(self._get_value(CONF_TARGET_SOC_OVERRIDE)) or DEFAULT_TARGET_SOC
        min_soc = self._safe_int(self._get_value(CONF_MIN_SOC_OVERRIDE)) or DEFAULT_MIN_SOC
        expected_balance = None
        if forecast.tomorrow_kwh is not None and telemetry.home_consumption_kw is not None:
            expected_balance = forecast.tomorrow_kwh - telemetry.home_consumption_kw * 24

        should_charge = bool(
            forecast.tomorrow_kwh is not None
            and expected_balance is not None
            and expected_balance < 0
            and telemetry.battery_soc < target_soc
        )

        return Recommendation(
            charge_from_grid=should_charge,
            target_soc=target_soc,
            min_soc=min_soc,
            expected_balance_kwh=expected_balance,
            estimated_savings=0.0,
            active_mode=EnergyMode(self._get_value(CONF_MODE) or EnergyMode.BALANCED),
            bad_weather_risk=1.0 - (forecast.confidence or 0.5),
            should_charge=should_charge,
            energy_deficit=bool(expected_balance is not None and expected_balance < 0),
            messages=["Decision engine placeholder output"],
        )

    def _estimate_forecast_confidence(self, forecast: ForecastSnapshot) -> float:
        """Estimate confidence from forecast completeness."""

        values = [forecast.today_kwh, forecast.tomorrow_kwh, forecast.remaining_today_kwh]
        available = sum(value is not None for value in values)
        return round(available / len(values), 2)

    def _is_forecast_degrading(self, forecast: ForecastSnapshot) -> bool:
        """Detect a basic degradation trend."""

        if forecast.today_kwh is None or forecast.tomorrow_kwh is None:
            return False
        return forecast.tomorrow_kwh < forecast.today_kwh * 0.75

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Convert an unknown value to float."""

        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        """Convert an unknown value to int."""

        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None