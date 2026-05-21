"""Pure derived metrics from DecisionContext inputs."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..const import TariffType
from ..models import BatteryConfig, ForecastSnapshot, TariffConfig, TelemetrySnapshot


# ---------------------------------------------------------------------------
# Tariff-window helpers
# ---------------------------------------------------------------------------


def _minutes_of(h: int, m: int) -> int:
    return h * 60 + m


def _minutes_until(now_m: int, target_m: int) -> int:
    """Positive minutes from *now_m* to *target_m*, wrapping overnight."""
    delta = target_m - now_m
    if delta <= 0:
        delta += 24 * 60
    return delta


def is_cheap_window(now: datetime, tariff: TariffConfig) -> bool:
    """Return True when *now* falls inside the dual-tariff night window."""
    if tariff.tariff_type != TariffType.DUAL:
        return False
    if tariff.night_start is None or tariff.night_end is None:
        return False

    now_t = now.time().replace(second=0, microsecond=0)
    ns = tariff.night_start
    ne = tariff.night_end

    # Overnight wrap (e.g. 23:00–07:00): start > end
    if ns > ne:
        return now_t >= ns or now_t < ne
    return ns <= now_t < ne


def time_until_cheap_window(now: datetime, tariff: TariffConfig) -> timedelta | None:
    """Timedelta until the cheap window starts, or ``timedelta(0)`` if already in it."""
    if tariff.tariff_type != TariffType.DUAL or tariff.night_start is None:
        return None
    if is_cheap_window(now, tariff):
        return timedelta(0)
    now_m = _minutes_of(now.hour, now.minute)
    target_m = _minutes_of(tariff.night_start.hour, tariff.night_start.minute)
    return timedelta(minutes=_minutes_until(now_m, target_m))


def time_until_expensive_window(now: datetime, tariff: TariffConfig) -> timedelta | None:
    """Timedelta until the cheap window ends. ``None`` if not currently in it."""
    if tariff.tariff_type != TariffType.DUAL or tariff.night_end is None:
        return None
    if not is_cheap_window(now, tariff):
        return None
    now_m = _minutes_of(now.hour, now.minute)
    target_m = _minutes_of(tariff.night_end.hour, tariff.night_end.minute)
    return timedelta(minutes=_minutes_until(now_m, target_m))


# ---------------------------------------------------------------------------
# Energy balance helpers
# ---------------------------------------------------------------------------


def expected_deficit_kwh(forecast: ForecastSnapshot) -> float | None:
    """Estimated tomorrow deficit (kWh): positive means consumption > PV."""
    if forecast.tomorrow_kwh is None or forecast.consumption_tomorrow_kwh is None:
        return None
    return round(forecast.consumption_tomorrow_kwh - forecast.tomorrow_kwh, 3)


def remaining_today_deficit_kwh(
    forecast: ForecastSnapshot,
    telemetry: TelemetrySnapshot,
) -> float | None:
    """Remaining deficit today (kWh): positive means need grid/battery."""
    if forecast.remaining_today_kwh is None or forecast.consumption_today_kwh is None:
        return None
    return round(forecast.consumption_today_kwh - forecast.remaining_today_kwh, 3)


def available_battery_kwh(
    telemetry: TelemetrySnapshot,
    battery: BatteryConfig,
    min_soc: int,
) -> float:
    """kWh the battery can discharge above *min_soc*."""
    if telemetry.battery_soc is None:
        return 0.0
    usable_pct = max(telemetry.battery_soc - min_soc, 0.0)
    return round(usable_pct / 100.0 * battery.capacity_kwh, 3)


def headroom_battery_kwh(
    telemetry: TelemetrySnapshot,
    battery: BatteryConfig,
    target_soc: int,
) -> float:
    """kWh the battery can still absorb up to *target_soc*."""
    if telemetry.battery_soc is None:
        return battery.capacity_kwh
    empty_pct = max(target_soc - telemetry.battery_soc, 0.0)
    return round(empty_pct / 100.0 * battery.capacity_kwh, 3)


# ---------------------------------------------------------------------------
# Forecast quality helpers
# ---------------------------------------------------------------------------


def weather_risk(forecast: ForecastSnapshot) -> float:
    """0–1 risk score where 1 = very risky / uncertain."""
    base = 1.0 - (forecast.confidence or 0.5)
    if forecast.degrading:
        base = min(base + 0.2, 1.0)
    return round(base, 2)


# ---------------------------------------------------------------------------
# Tariff helpers
# ---------------------------------------------------------------------------


def rate_delta(tariff: TariffConfig) -> float | None:
    """Day rate minus night rate. Positive = day is more expensive. ``None`` for flat."""
    if tariff.tariff_type != TariffType.DUAL:
        return None
    if tariff.day_rate is None or tariff.night_rate is None:
        return None
    return round(tariff.day_rate - tariff.night_rate, 4)
