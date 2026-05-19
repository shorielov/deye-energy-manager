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
from homeassistant.util import dt as dt_util

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
    CONF_SMART_LOAD_TODAY_ENTITY,
    CONF_TARGET_SOC_OVERRIDE,
    CONF_TARIFF_TYPE,
    CONF_TODAY_LOAD_CONSUMPTION_ENTITY,
    ConsumptionSource,
    DEFAULT_BATTERY_TEMPERATURE_C,
    DEFAULT_MIN_SOC,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_TARGET_SOC,
    DOMAIN,
    EnergyMode,
    TariffType,
)
from .consumption_forecast import ConsumptionForecaster
from .models import BatteryConfig, EnergyState, ForecastSnapshot, Recommendation, TariffConfig, TelemetrySnapshot

_LOGGER = logging.getLogger(__name__)

# Unit-conversion scale factors to normalise sensor values to kW or kWh.
_POWER_SCALE: dict[str, float] = {"mW": 1e-6, "W": 1e-3, "kW": 1.0, "MW": 1e3}
_ENERGY_SCALE: dict[str, float] = {"Wh": 1e-3, "kWh": 1.0, "MWh": 1e3}
_UNIT_SCALE: dict[str, dict[str, float]] = {"kW": _POWER_SCALE, "kWh": _ENERGY_SCALE}


def _float_state(
    hass: HomeAssistant,
    entity_id: str | None,
    expected_unit: str | None = None,
) -> float | None:
    """Read a state and coerce it to float, converting units when *expected_unit* is given.

    When *expected_unit* is ``"kW"`` or ``"kWh"``, the entity's
    ``unit_of_measurement`` attribute is read and the value is scaled to the
    expected unit (e.g. ``W → kW``, ``Wh → kWh``).  Entities that report no
    unit, or an unrecognised unit, are returned as-is with a debug log.
    """

    if not entity_id:
        return None

    state = hass.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable"}:
        return None

    try:
        value = float(state.state)
    except ValueError:
        _LOGGER.debug("Unable to parse %s=%s as float", entity_id, state.state)
        return None

    if expected_unit is None:
        return value

    actual_unit: str | None = state.attributes.get("unit_of_measurement")
    if actual_unit is None or actual_unit == expected_unit:
        return value

    scale_map = _UNIT_SCALE.get(expected_unit)
    if scale_map is None:
        return value

    factor = scale_map.get(actual_unit)
    if factor is None:
        _LOGGER.debug(
            "Unknown unit '%s' for %s (expected %s), using raw value",
            actual_unit,
            entity_id,
            expected_unit,
        )
        return value

    return value * factor


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
        self._consumption_forecaster = ConsumptionForecaster(hass)

    async def _async_update_data(self) -> EnergyState:
        """Fetch states from Home Assistant and build a normalized payload."""

        telemetry = TelemetrySnapshot(
            battery_soc=_float_state(self.hass, self._get_value(CONF_BATTERY_SOC_ENTITY)),
            battery_power_kw=_float_state(self.hass, self._get_value(CONF_BATTERY_POWER_ENTITY), "kW"),
            battery_temperature_c=_float_state(self.hass, self._get_value(CONF_BATTERY_TEMPERATURE_ENTITY))
            or DEFAULT_BATTERY_TEMPERATURE_C,
            pv_power_kw=_float_state(self.hass, self._get_value(CONF_PV_POWER_ENTITY), "kW"),
            pv_generation_today_kwh=_float_state(self.hass, self._get_value(CONF_PV_GENERATION_TODAY_ENTITY), "kWh"),
            grid_import_kwh=_float_state(self.hass, self._get_value(CONF_GRID_IMPORT_ENTITY), "kWh"),
            grid_export_kwh=_float_state(self.hass, self._get_value(CONF_GRID_EXPORT_ENTITY), "kWh"),
            home_consumption_kw=_float_state(self.hass, self._get_value(CONF_HOME_CONSUMPTION_ENTITY), "kW"),
            today_load_consumption_kwh=_float_state(self.hass, self._get_value(CONF_TODAY_LOAD_CONSUMPTION_ENTITY), "kWh"),
            smart_load_today_kwh=_float_state(self.hass, self._get_value(CONF_SMART_LOAD_TODAY_ENTITY), "kWh"),
            updated_at=datetime.now(UTC),
        )

        if telemetry.battery_soc is None:
            raise UpdateFailed("Battery SOC entity returned no usable state")

        self._telemetry_history.append(telemetry)

        # --- Consumption forecast: priority chain ---
        # 1) Statistics-based baseline (recorder, survives restarts)
        stats_tomorrow, stats_confidence = await self._consumption_forecaster.async_estimate(
            self._get_value(CONF_TODAY_LOAD_CONSUMPTION_ENTITY),
            self._get_value(CONF_SMART_LOAD_TODAY_ENTITY),
        )

        # 2) Power-history-based fallback
        pw_today, pw_tomorrow, pw_confidence = self._estimate_consumption_forecast()

        # Live baseline for today (ground truth when energy counters are configured)
        if telemetry.today_load_consumption_kwh is not None:
            smart = telemetry.smart_load_today_kwh or 0.0
            live_baseline_today = max(telemetry.today_load_consumption_kwh - smart, 0.0)
        else:
            live_baseline_today = None

        # Resolve tomorrow forecast and source
        if stats_tomorrow is not None:
            consumption_tomorrow = stats_tomorrow
            consumption_confidence = stats_confidence
            consumption_source = ConsumptionSource.STATISTICS
        elif pw_tomorrow is not None:
            consumption_tomorrow = pw_tomorrow
            consumption_confidence = pw_confidence
            consumption_source = ConsumptionSource.POWER_HISTORY
        else:
            consumption_tomorrow = None
            consumption_confidence = None
            consumption_source = ConsumptionSource.NONE

        # Resolve today consumption: live baseline beats power-based estimate
        consumption_today = live_baseline_today if live_baseline_today is not None else pw_today

        forecast = ForecastSnapshot(
            today_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_TODAY_ENTITY), "kWh"),
            tomorrow_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_TOMORROW_ENTITY), "kWh"),
            remaining_today_kwh=_float_state(self.hass, self._get_value(CONF_FORECAST_REMAINING_ENTITY), "kWh"),
            consumption_today_kwh=consumption_today,
            consumption_tomorrow_kwh=consumption_tomorrow,
            consumption_confidence=consumption_confidence,
            consumption_source=consumption_source,
        )
        forecast = replace(
            forecast,
            confidence=self._estimate_forecast_confidence(forecast),
            degrading=self._is_forecast_degrading(forecast),
        )

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
        self._consumption_forecaster.invalidate_cache()
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
        if forecast.tomorrow_kwh is not None:
            consumption_proxy = forecast.consumption_tomorrow_kwh
            if consumption_proxy is None and telemetry.today_load_consumption_kwh is not None:
                smart = telemetry.smart_load_today_kwh or 0.0
                live_today = max(telemetry.today_load_consumption_kwh - smart, 0.0)
                now = dt_util.now()
                hours_elapsed = max(now.hour + now.minute / 60.0, 2.0)
                consumption_proxy = live_today * 24.0 / hours_elapsed
            if consumption_proxy is not None:
                expected_balance = forecast.tomorrow_kwh - consumption_proxy

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

    def _estimate_consumption_forecast(self) -> tuple[float | None, float | None, float | None]:
        """Estimate daily home consumption (kWh) from telemetry history.

        Uses hourly averages from ``_telemetry_history`` when multiple hours
        are available. Falls back to a conservative estimate when history is
        sparse. Returns ``(today_kwh, tomorrow_kwh, confidence)``.
        """

        valid = [
            s
            for s in self._telemetry_history
            if s.home_consumption_kw is not None and s.updated_at is not None
        ]
        if not valid:
            return None, None, None

        hourly: dict[int, list[float]] = {}
        for snap in valid:
            h = snap.updated_at.hour
            if h not in hourly:
                hourly[h] = []
            hourly[h].append(snap.home_consumption_kw)  # type: ignore[arg-type]

        available_hours = len(hourly)
        overall_mean = sum(s.home_consumption_kw for s in valid) / len(valid)  # type: ignore[misc]

        if available_hours < 2:
            # Sparse: conservative estimate capped at 50 % confidence
            daily_kwh = round(overall_mean * 24 * 0.9, 3)
            confidence = round(available_hours / 24 * 0.5, 2)
            return daily_kwh, daily_kwh, confidence

        hourly_means = {h: sum(v) / len(v) for h, v in hourly.items()}
        daily_kwh = round(
            sum(hourly_means.get(h, overall_mean) for h in range(24)), 3
        )
        confidence = round(available_hours / 24, 2)
        return daily_kwh, daily_kwh, confidence

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