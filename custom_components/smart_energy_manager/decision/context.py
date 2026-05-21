"""DecisionContext: all inputs the decision engine needs, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from ..const import EnergyMode
from ..models import BatteryConfig, ForecastSnapshot, TariffConfig, TelemetrySnapshot


@dataclass(slots=True)
class SunTimes:
    """Approximate sunrise and sunset for the planning day (local time)."""

    sunrise: time
    sunset: time


@dataclass(slots=True)
class DecisionContext:
    """Immutable snapshot of everything the decision engine needs.

    Passed by the coordinator; the engine is pure – no I/O, no hass.
    """

    telemetry: TelemetrySnapshot
    forecast: ForecastSnapshot
    tariff: TariffConfig
    battery: BatteryConfig
    mode: EnergyMode
    now: object  # datetime, typed as object to keep pure module free of tz import
    min_soc: int = 20
    target_soc: int = 80
    sun: SunTimes | None = None
