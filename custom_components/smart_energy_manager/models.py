"""Data models for Smart Energy Manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from .const import ConsumptionSource, EnergyMode, RecommendationCode, TariffType


@dataclass(slots=True)
class PlanSlot:
    """A single TOU inverter slot."""

    start_time: time
    target_soc: int
    charge_from_grid: bool
    max_power_w: int | None = None
    reason: RecommendationCode = RecommendationCode.MISSING_DATA


@dataclass(slots=True)
class Plan:
    """Full 6-slot daily plan produced by a strategy."""

    slots: list[PlanSlot]
    generated_at: datetime
    strategy: str
    estimated_savings_uah: float = 0.0
    expected_balance_kwh: float | None = None
    notes: list[str] = field(default_factory=list)

@dataclass(slots=True)
class TariffConfig:
    """Resolved tariff configuration."""

    tariff_type: TariffType = TariffType.FLAT
    flat_rate: float | None = None
    day_rate: float | None = None
    night_rate: float | None = None
    night_start: time | None = None
    night_end: time | None = None


@dataclass(slots=True)
class BatteryConfig:
    """Battery configuration provided by the user."""

    capacity_kwh: float
    min_soc_override: int | None = None
    target_soc_override: int | None = None


@dataclass(slots=True)
class TelemetrySnapshot:
    """Normalized telemetry values from Home Assistant entities."""

    battery_soc: float | None = None
    battery_power_kw: float | None = None
    battery_temperature_c: float | None = None
    pv_power_kw: float | None = None
    pv_generation_today_kwh: float | None = None
    grid_import_kwh: float | None = None
    grid_export_kwh: float | None = None
    home_consumption_kw: float | None = None
    today_load_consumption_kwh: float | None = None
    smart_load_today_kwh: float | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class ForecastSnapshot:
    """Forecast values and metadata."""

    today_kwh: float | None = None
    tomorrow_kwh: float | None = None
    remaining_today_kwh: float | None = None
    confidence: float | None = None
    degrading: bool = False
    consumption_today_kwh: float | None = None
    consumption_tomorrow_kwh: float | None = None
    consumption_confidence: float | None = None
    consumption_source: ConsumptionSource = ConsumptionSource.NONE


@dataclass(slots=True)
class Recommendation:
    """Decision engine output."""

    charge_from_grid: bool = False
    target_soc: int | None = None
    min_soc: int | None = None
    expected_balance_kwh: float | None = None
    estimated_savings: float | None = None
    active_mode: EnergyMode = EnergyMode.BALANCED
    reason_codes: list[RecommendationCode] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    bad_weather_risk: float | None = None
    should_charge: bool = False
    energy_deficit: bool = False


@dataclass(slots=True)
class EnergyState:
    """Coordinator payload shared by all platforms."""

    telemetry: TelemetrySnapshot
    forecast: ForecastSnapshot
    recommendation: Recommendation
    tariff: TariffConfig
    battery: BatteryConfig
    last_update_success: bool = True
    plan: Plan | None = None