"""Tests for decision.signals pure functions."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from custom_components.smart_energy_manager.const import TariffType
from custom_components.smart_energy_manager.decision.signals import (
    available_battery_kwh,
    headroom_battery_kwh,
    is_cheap_window,
    rate_delta,
    risk_adjusted_pv_kwh,
    time_until_cheap_window,
    time_until_expensive_window,
    weather_risk,
)
from custom_components.smart_energy_manager.models import (
    BatteryConfig,
    ForecastSnapshot,
    TariffConfig,
    TelemetrySnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tariff_flat(rate: float = 4.32) -> TariffConfig:
    return TariffConfig(tariff_type=TariffType.FLAT, flat_rate=rate)


def _tariff_dual(night_start: time = time(23, 0), night_end: time = time(7, 0)) -> TariffConfig:
    return TariffConfig(
        tariff_type=TariffType.DUAL,
        day_rate=4.32,
        night_rate=1.68,
        night_start=night_start,
        night_end=night_end,
    )


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 15, hour, minute)


def _telemetry(soc: float = 60.0) -> TelemetrySnapshot:
    return TelemetrySnapshot(battery_soc=soc)


def _battery(capacity: float = 10.0, min_soc: int | None = None, target: int | None = None) -> BatteryConfig:
    return BatteryConfig(capacity_kwh=capacity, min_soc_override=min_soc, target_soc_override=target)


def _forecast(**kwargs) -> ForecastSnapshot:
    return ForecastSnapshot(**kwargs)


# ---------------------------------------------------------------------------
# is_cheap_window
# ---------------------------------------------------------------------------


class TestIsCheapWindow:
    def test_flat_tariff_always_false(self):
        assert is_cheap_window(_at(2), _tariff_flat()) is False

    def test_dual_during_night(self):
        # 23:00–07:00 window, check 01:00
        assert is_cheap_window(_at(1), _tariff_dual()) is True

    def test_dual_outside_night(self):
        assert is_cheap_window(_at(12), _tariff_dual()) is False

    def test_dual_at_boundary_start(self):
        assert is_cheap_window(_at(23), _tariff_dual()) is True

    def test_dual_at_boundary_end_exclusive(self):
        # 07:00 is the start of the expensive window
        assert is_cheap_window(_at(7), _tariff_dual()) is False

    def test_dual_non_overnight(self):
        # e.g. 01:00–05:00 same day (start < end)
        tariff = _tariff_dual(night_start=time(1, 0), night_end=time(5, 0))
        assert is_cheap_window(_at(3), tariff) is True
        assert is_cheap_window(_at(0), tariff) is False
        assert is_cheap_window(_at(6), tariff) is False


# ---------------------------------------------------------------------------
# time_until_cheap_window / time_until_expensive_window
# ---------------------------------------------------------------------------


class TestTimeUntilWindows:
    def test_flat_returns_none(self):
        assert time_until_cheap_window(_at(10), _tariff_flat()) is None

    def test_already_in_cheap_window_returns_zero(self):
        td = time_until_cheap_window(_at(2), _tariff_dual())
        assert td is not None and td.total_seconds() == 0

    def test_returns_correct_minutes_to_cheap(self):
        # Now=12:00, cheap starts at 23:00 → 11 h = 660 min
        td = time_until_cheap_window(_at(12), _tariff_dual())
        assert td is not None and td.total_seconds() == 660 * 60

    def test_time_until_expensive_outside_window(self):
        assert time_until_expensive_window(_at(12), _tariff_dual()) is None

    def test_time_until_expensive_inside_window(self):
        # In window at 01:00, window ends at 07:00 → 6 h = 360 min
        td = time_until_expensive_window(_at(1), _tariff_dual())
        assert td is not None and td.total_seconds() == 360 * 60


# ---------------------------------------------------------------------------
# available_battery_kwh
# ---------------------------------------------------------------------------


class TestAvailableBatteryKwh:
    def test_basic(self):
        tel = _telemetry(soc=60.0)
        bat = _battery(capacity=10.0)
        # available = (60 - 20) / 100 * 10 = 4.0
        val = available_battery_kwh(tel, bat, min_soc=20)
        assert abs(val - 4.0) < 0.01

    def test_below_min_soc(self):
        tel = _telemetry(soc=15.0)
        bat = _battery(capacity=10.0)
        val = available_battery_kwh(tel, bat, min_soc=20)
        assert val <= 0.0

    def test_missing_soc_returns_zero(self):
        tel = TelemetrySnapshot()
        bat = _battery()
        assert available_battery_kwh(tel, bat, min_soc=20) == 0.0


# ---------------------------------------------------------------------------
# headroom_battery_kwh
# ---------------------------------------------------------------------------


class TestHeadroomBatteryKwh:
    def test_basic(self):
        tel = _telemetry(soc=60.0)
        bat = _battery(capacity=10.0)
        # headroom = (80 - 60) / 100 * 10 = 2.0
        val = headroom_battery_kwh(tel, bat, target_soc=80)
        assert abs(val - 2.0) < 0.01

    def test_already_at_target(self):
        tel = _telemetry(soc=80.0)
        bat = _battery(capacity=10.0)
        assert headroom_battery_kwh(tel, bat, target_soc=80) <= 0.0


# ---------------------------------------------------------------------------
# weather_risk
# ---------------------------------------------------------------------------


class TestWeatherRisk:
    def test_high_confidence_low_risk(self):
        assert weather_risk(_forecast(confidence=0.95)) < 0.2

    def test_low_confidence_high_risk(self):
        assert weather_risk(_forecast(confidence=0.2)) > 0.6

    def test_degrading_increases_risk(self):
        base = weather_risk(_forecast(confidence=0.8, degrading=False))
        with_deg = weather_risk(_forecast(confidence=0.8, degrading=True))
        assert with_deg > base

    def test_none_confidence_returns_mid_range(self):
        r = weather_risk(_forecast(confidence=None))
        assert 0.0 <= r <= 1.0

    def test_peak_path_clear_day(self):
        f = _forecast(peak_today_w=4000.0, peak_tomorrow_w=4000.0, peak_reference_w=4000.0)
        assert weather_risk(f) < 0.1

    def test_peak_path_cloudy(self):
        f = _forecast(peak_today_w=4000.0, peak_tomorrow_w=2000.0, peak_reference_w=4000.0)
        assert weather_risk(f) > 0.5

    def test_peak_path_today_drop_adds_bonus(self):
        no_drop = _forecast(peak_today_w=4000.0, peak_tomorrow_w=3000.0, peak_reference_w=4000.0)
        with_drop = _forecast(peak_today_w=4000.0, peak_tomorrow_w=2000.0, peak_reference_w=4000.0)
        assert weather_risk(with_drop) > weather_risk(no_drop)

    def test_fallback_kwh_path(self):
        f = _forecast(tomorrow_kwh=10.0, baseline_kwh=20.0, baseline_samples=7)
        assert weather_risk(f) > 0.5

    def test_baseline_small_sample_adds_penalty(self):
        f_many = _forecast(tomorrow_kwh=15.0, baseline_kwh=20.0, baseline_samples=7)
        f_few = _forecast(tomorrow_kwh=15.0, baseline_kwh=20.0, baseline_samples=3)
        assert weather_risk(f_few) > weather_risk(f_many)


# ---------------------------------------------------------------------------
# risk_adjusted_pv_kwh
# ---------------------------------------------------------------------------


class TestRiskAdjustedPvKwh:
    def test_returns_none_when_no_tomorrow(self):
        assert risk_adjusted_pv_kwh(_forecast()) is None

    def test_peak_based_strong_derate(self):
        # peak_tomorrow=2000, ref=4000 → cloudy, risk>0.5 → strong derate
        f = _forecast(
            tomorrow_kwh=20.0,
            peak_today_w=4000.0,
            peak_tomorrow_w=2000.0,
            peak_reference_w=4000.0,
        )
        adj = risk_adjusted_pv_kwh(f)
        assert adj is not None and adj < 20.0
        assert adj > 0

    def test_clear_day_minimal_derate(self):
        f = _forecast(tomorrow_kwh=20.0, peak_tomorrow_w=4000.0, peak_reference_w=4000.0)
        adj = risk_adjusted_pv_kwh(f)
        assert adj is not None and adj > 18.0

    def test_cold_start_mild_derate(self):
        f = _forecast(tomorrow_kwh=20.0, confidence=0.5)
        adj = risk_adjusted_pv_kwh(f)
        assert adj is not None and 0 < adj <= 20.0


# ---------------------------------------------------------------------------
# rate_delta
# ---------------------------------------------------------------------------


class TestRateDelta:
    def test_flat_tariff_returns_none(self):
        assert rate_delta(_tariff_flat()) is None

    def test_dual_correct_delta(self):
        tariff = _tariff_dual()  # day=4.32, night=1.68
        assert abs(rate_delta(tariff) - (4.32 - 1.68)) < 0.001
