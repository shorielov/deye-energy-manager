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
        """When weather_risk > 0.7 the ECO strategy should bump target_soc."""
        low_risk = strategy.evaluate(_ctx(confidence=0.95))
        high_risk = strategy.evaluate(_ctx(confidence=0.1, degrading=True))
        # At least one slot in high-risk plan should have higher target than equivalent slot
        # in low-risk plan (or equal, but never lower)
        for lr, hr in zip(low_risk.slots, high_risk.slots):
            assert hr.target_soc >= lr.target_soc

    def test_all_slots_valid_soc(self):
        for slot in strategy.evaluate(_ctx()).slots:
            assert 0 <= slot.target_soc <= 100

    def test_target_soc_scales_smoothly_with_risk(self):
        """target_soc bonus increases gradually, not as a step at 0.7."""
        # conf=0.9 → risk≈0.1 → bonus=0 → target=80
        low = strategy.evaluate(_ctx(confidence=0.9)).slots[0].target_soc
        # conf=0.5 → risk≈0.5 → bonus=round((0.5-0.3)*25)=5 → target=85
        mid = strategy.evaluate(_ctx(confidence=0.5)).slots[0].target_soc
        # conf=0.1 → risk≈0.9 → bonus=round((0.9-0.3)*25)=15 → target=95
        high = strategy.evaluate(_ctx(confidence=0.1)).slots[0].target_soc
        assert low == 80
        assert mid == 85
        assert high == 95
        assert low < mid < high
