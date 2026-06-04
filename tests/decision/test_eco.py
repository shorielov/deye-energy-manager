"""Tests for the EcoStrategy."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.smart_energy_manager.const import EnergyMode, TariffType
from custom_components.smart_energy_manager.decision.context import DecisionContext, SunTimes
from custom_components.smart_energy_manager.decision.strategies.eco import EcoStrategy
from custom_components.smart_energy_manager.models import (
    BatteryConfig,
    ForecastSnapshot,
    TariffConfig,
    TelemetrySnapshot,
)


def _ctx(
    *,
    confidence: float = 0.8,
    degrading: bool = False,
    battery_soc: float = 50.0,
    target_soc: int = 80,
    min_soc: int = 20,
    sun: SunTimes | None = SunTimes(time(7, 0), time(18, 0)),
    peak_today_w: float | None = None,
    peak_tomorrow_w: float | None = None,
    peak_reference_w: float | None = None,
) -> DecisionContext:
    return DecisionContext(
        telemetry=TelemetrySnapshot(battery_soc=battery_soc),
        forecast=ForecastSnapshot(
            tomorrow_kwh=6.0,
            remaining_today_kwh=2.0,
            confidence=confidence,
            degrading=degrading,
            peak_today_w=peak_today_w,
            peak_tomorrow_w=peak_tomorrow_w,
            peak_reference_w=peak_reference_w,
        ),
        tariff=TariffConfig(tariff_type=TariffType.FLAT, flat_rate=4.32),
        battery=BatteryConfig(capacity_kwh=10.0),
        mode=EnergyMode.ECO,
        now=datetime(2024, 6, 15, 12, 0),
        min_soc=min_soc,
        target_soc=target_soc,
        sun=sun,
    )


strategy = EcoStrategy()


class TestEcoStrategy:
    def test_produces_six_slots(self):
        assert len(strategy.evaluate(_ctx()).slots) == 6

    def test_never_charges_from_grid(self):
        plan = strategy.evaluate(_ctx())
        assert all(not s.charge_from_grid for s in plan.slots)

    def test_strategy_name(self):
        assert strategy.evaluate(_ctx()).strategy == "eco"

    def test_slots_sorted_by_start(self):
        plan = strategy.evaluate(_ctx())
        times = [s.start_time for s in plan.slots]
        assert times == sorted(times)

    def test_high_weather_risk_raises_target_soc(self):
        """High weather risk (bad peak forecast) should bump target_soc vs clear day."""
        # clear day: peak_tomorrow == peak_reference → risk=0 → no bonus
        low_risk = strategy.evaluate(_ctx(peak_tomorrow_w=4000.0, peak_reference_w=4000.0))
        # very cloudy: peak_tomorrow=25% of reference → risk=0.75 → bonus present
        high_risk = strategy.evaluate(_ctx(peak_tomorrow_w=1000.0, peak_reference_w=4000.0))
        for lr, hr in zip(low_risk.slots, high_risk.slots):
            assert hr.target_soc >= lr.target_soc

    def test_all_slots_valid_soc(self):
        for slot in strategy.evaluate(_ctx()).slots:
            assert 0 <= slot.target_soc <= 100

    def test_target_soc_scales_smoothly_with_risk(self):
        """target_soc bonus increases gradually with weather risk (peak-based path)."""
        # clear: clearness=1.0 → risk=0.0 → bonus=0 → target=80
        clear = strategy.evaluate(_ctx(peak_tomorrow_w=4000.0, peak_reference_w=4000.0)).slots[0].target_soc
        # mild cloud: clearness=0.7 → risk=0.3 → bonus=0 (exactly at threshold) → target=80
        mild = strategy.evaluate(_ctx(peak_tomorrow_w=2800.0, peak_reference_w=4000.0)).slots[0].target_soc
        # heavy cloud: clearness=0.5 → risk=0.5 → bonus=round((0.5-0.3)*25)=5 → target=85
        heavy = strategy.evaluate(_ctx(peak_tomorrow_w=2000.0, peak_reference_w=4000.0)).slots[0].target_soc
        assert clear == 80
        assert mild == 80
        assert heavy == 85
        assert heavy > clear
