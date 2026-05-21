"""Constants for the Smart Energy Manager integration."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

DOMAIN = "smart_energy_manager"
PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "number"]

CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_BATTERY_POWER_ENTITY = "battery_power_entity"
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_BATTERY_TEMPERATURE_ENTITY = "battery_temperature_entity"

CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_PV_GENERATION_TODAY_ENTITY = "pv_generation_today_entity"

CONF_GRID_IMPORT_ENTITY = "grid_import_entity"
CONF_GRID_EXPORT_ENTITY = "grid_export_entity"

CONF_HOME_CONSUMPTION_ENTITY = "home_consumption_entity"
CONF_TODAY_LOAD_CONSUMPTION_ENTITY = "today_load_consumption_entity"
CONF_SMART_LOAD_TODAY_ENTITY = "smart_load_today_entity"

CONF_FORECAST_TODAY_ENTITY = "forecast_today_entity"
CONF_FORECAST_TOMORROW_ENTITY = "forecast_tomorrow_entity"
CONF_FORECAST_REMAINING_ENTITY = "forecast_remaining_entity"

CONF_FLAT_RATE = "flat_rate"
CONF_DAY_RATE = "day_rate"
CONF_NIGHT_RATE = "night_rate"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"
CONF_TARIFF_TYPE = "tariff_type"

CONF_MODE = "mode"
CONF_AUTO_APPLY_RECOMMENDATIONS = "auto_apply_recommendations"
CONF_MIN_SOC_OVERRIDE = "min_soc_override"
CONF_TARGET_SOC_OVERRIDE = "target_soc_override"
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"
CONF_INVERTER_ADAPTER = "inverter_adapter"
CONF_SUNSYNK_ENTITY_PREFIX = "sunsynk_entity_prefix"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
DEFAULT_MIN_SOC = 20
DEFAULT_TARGET_SOC = 80
DEFAULT_BATTERY_TEMPERATURE_C = 20.0
DEFAULT_TARIFF_TYPE = "flat"
DEFAULT_SCAN_INTERVAL_SECONDS = 60
DEFAULT_BAD_WEATHER_THRESHOLD = 0.35

ATTR_ESTIMATED_SAVINGS = "estimated_savings"
ATTR_REASON_CODES = "reason_codes"
ATTR_FORECAST_CONFIDENCE = "forecast_confidence"
ATTR_EXPECTED_BALANCE = "expected_balance"
ATTR_ACTIVE_MODE = "active_mode"
ATTR_CONSUMPTION_TODAY_KWH = "consumption_today_kwh"
ATTR_CONSUMPTION_TOMORROW_KWH = "consumption_tomorrow_kwh"
ATTR_CONSUMPTION_CONFIDENCE = "consumption_confidence"
ATTR_CONSUMPTION_SOURCE = "consumption_source"
ATTR_TODAY_LOAD_KWH = "today_load_kwh"
ATTR_SMART_LOAD_TODAY_KWH = "smart_load_today_kwh"

SERVICE_RECOMPUTE = "recompute"
SERVICE_CLEAR_HISTORY = "clear_history"
SERVICE_SET_MODE = "set_mode"


class EnergyMode(StrEnum):
    """Supported strategy modes."""

    ECO = "eco"
    WINTER = "winter"
    AUTONOMOUS = "autonomous"
    BACKUP = "backup"
    BALANCED = "balanced"


class TariffType(StrEnum):
    """Supported tariff types."""

    FLAT = "flat"
    DUAL = "dual"


class ConsumptionSource(StrEnum):
    """Which data path produced the consumption forecast."""

    STATISTICS = "statistics"
    POWER_HISTORY = "power_history"
    FALLBACK = "fallback"
    NONE = "none"


class InverterAdapterType(StrEnum):
    """Supported inverter adapter integrations."""

    NONE = "none"
    SUNSYNK = "sunsynk"


class RecommendationCode(StrEnum):
    """Decision rationale codes."""

    LOW_FORECAST = "low_forecast"
    HIGH_CONSUMPTION = "high_consumption"
    CHEAP_TARIFF = "cheap_tariff"
    WINTER_GUARD = "winter_guard"
    BATTERY_PROTECTION = "battery_protection"
    MISSING_DATA = "missing_data"
    PV_PRIORITY = "pv_priority"
    NO_GRID_CHARGE = "no_grid_charge"
    BACKUP_MODE = "backup_mode"
    INSUFFICIENT_DEFICIT = "insufficient_deficit"