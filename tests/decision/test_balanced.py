"""Tests for the BalancedStrategy."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.smart_energy_manager.const import EnergyMode, RecommendationCode, TariffType
from custom_components.smart_energy_manager.decision.context import DecisionContext, SunTimes
from custom_components.smart_energy_manager.decision.strategies.balanced import BalancedStrategy
from custom_components.smart_energy_manager.models import (
    BatteryConfig,
    ForecastSnapshot,
    TariffConfig,
    TelemetrySnapshot,
)


def _ctx(
    *,
    tariff_type: TariffType = TariffType.FLAT,
    flat_rate: float = 4.32,
    day_rate: float = 4.32,
    night_rate: float = 1.68,
    night_start: time = time(23, 0),
    night_end: time = time(7, 0),
    tomorrow_kwh: float | None = 8.0,
    remaining_today: float | None = 2.0,
    battery_soc: float = 50.0,
    capacity_kwh: float = 10.0,
    target_soc: int = 80,
    min_soc: int = 20,
    now: datetime = datetime(2024, 1, 15, 10, 0),
    sun: SunTimes | None = SunTimes(time(7, 30), time(17, 30)),
    consumption_tomorrow: float | None = 12.0,
    peak_today_w: float | None = None,
    peak_tomorrow_w: float | None = None,
    peak_reference_w: float | None = None,
) -> DecisionContext:
    tariff = TariffConfig(
        tariff_type=tariff_type,
        flat_rate=flat_rate if tariff_type == TariffType.FLAT else None,
        day_rate=day_rate if tariff_type == TariffType.DUAL else None,
        night_rate=night_rate if tariff_type == TariffType.DUAL else None,
        night_start=night_start if tariff_type == TariffType.DUAL else None,
        night_end=night_end if tariff_type == TariffType.DUAL else None,
    )
    return DecisionContext(
        telemetry=TelemetrySnapshot(battery_soc=battery_soc),
        forecast=ForecastSnapshot(
            tomorrow_kwh=tomorrow_kwh,
            remaining_today_kwh=remaining_today,
            confidence=0.8,
            consumption_tomorrow_kwh=consumption_tomorrow,
            peak_today_w=peak_today_w,
            peak_tomorrow_w=peak_tomorrow_w,
            peak_reference_w=peak_reference_w,
        ),
        tariff=tariff,
        battery=BatteryConfig(capacity_kwh=capacity_kwh),
        mode=EnergyMode.BALANCED,
        now=now,
        min_soc=min_soc,
        target_soc=target_soc,
        sun=sun,
    )


strategy = BalancedStrategy()


class TestBalancedFlat:
    def test_produces_six_slots(self):
        plan = strategy.evaluate(_ctx())
        assert len(plan.slots) == 6

    def test_no_grid_charge_on_flat_tariff(self):
        plan = strategy.evaluate(_ctx())
        assert all(not s.charge_from_grid for s in plan.slots)

    def test_strategy_name(self):
        assert strategy.evaluate(_ctx()).strategy == "balanced"

    def test_notes_mention_flat(self):
        plan = strategy.evaluate(_ctx())
        assert any("flat" in n.lower() or "pv" in n.lower() or "no grid" in n.lower() for n in plan.notes)


class TestBalancedDualSmallDeficit:
    """Deficit ≤ 2 kWh → no grid charge even on dual tariff."""

    def test_no_charge_when_small_deficit(self):
        # tomorrow=4 kWh forecast, consumption=3 kWh → deficit=−1 (surplus) → no charge needed
        plan = strategy.evaluate(
            _ctx(tariff_type=TariffType.DUAL, tomorrow_kwh=4.0, consumption_tomorrow=3.0)
        )
        assert all(not s.charge_from_grid for s in plan.slots)


class TestBalancedDualLargeDeficit:
    """Large deficit on dual tariff triggers grid charging."""

    def _dual_large(self) -> DecisionContext:
        # tomorrow=3 kWh, consumption=10 kWh → deficit=-7, battery 50% on 10 kWh → headroom=3
        return _ctx(
            tariff_type=TariffType.DUAL,
            tomorrow_kwh=3.0,
            consumption_tomorrow=10.0,
            battery_soc=50.0,
            capacity_kwh=10.0,
        )

    def test_grid_charge_slots_present(self):
        plan = strategy.evaluate(self._dual_large())
        assert any(s.charge_from_grid for s in plan.slots)

    def test_exactly_six_slots(self):
        plan = strategy.evaluate(self._dual_large())
        assert len(plan.slots) == 6

    def test_slots_sorted_by_start(self):
        plan = strategy.evaluate(self._dual_large())
        times = [s.start_time for s in plan.slots]
        assert times == sorted(times)


class TestBalancedSlotContents:
    def test_all_slots_have_valid_soc(self):
        plan = strategy.evaluate(_ctx())
        for slot in plan.slots:
            assert 0 <= slot.target_soc <= 100

    def test_all_slots_have_reason_code(self):
        plan = strategy.evaluate(_ctx())
        for slot in plan.slots:
            assert isinstance(slot.reason, RecommendationCode)


class TestBalancedWeatherRisk:
    def test_grid_charge_triggered_by_bad_weather(self):
        """tomorrow=15 kWh PV, consumption=16 → raw_deficit=1 (normally < 2.0 threshold),
        but peak_tomorrow=2000 vs ref=4000 → risk≈0.80, adj_pv is derated ≈7.8 kWh,
        adj_deficit≈8.2 > threshold 1.0 → should trigger grid charge.
        """
        plan = strategy.evaluate(
            _ctx(
                tariff_type=TariffType.DUAL,
                tomorrow_kwh=15.0,
                consumption_tomorrow=16.0,
                battery_soc=50.0,
                capacity_kwh=10.0,
                peak_today_w=4000.0,
                peak_tomorrow_w=2000.0,
                peak_reference_w=4000.0,
            )
        )
        assert any(s.charge_from_grid for s in plan.slots)

    def test_no_grid_charge_when_sunny_and_small_deficit(self):
        """tomorrow=14 kWh PV, consumption=15 → raw_deficit=1, clear sky → adj_pv≈14 kWh,
        adj_deficit≈1 < 2.0 threshold → no grid charge.
        """
        plan = strategy.evaluate(
            _ctx(
                tariff_type=TariffType.DUAL,
                tomorrow_kwh=14.0,
                consumption_tomorrow=15.0,
                peak_today_w=4000.0,
                peak_tomorrow_w=4000.0,
                peak_reference_w=4000.0,
            )
        )
        assert all(not s.charge_from_grid for s in plan.slots)
