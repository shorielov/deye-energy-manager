"""Tests for BalancingStrategy."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest

from custom_components.smart_energy_manager.const import EnergyMode, RecommendationCode, TariffType
from custom_components.smart_energy_manager.decision.context import DecisionContext, SunTimes
from custom_components.smart_energy_manager.decision.strategies.balancing import BalancingStrategy
from custom_components.smart_energy_manager.models import (
    BalanceConfig,
    BatteryConfig,
    ForecastSnapshot,
    TariffConfig,
    TelemetrySnapshot,
)


_SUN = SunTimes(time(6, 30), time(20, 0))
_NOW = datetime(2024, 6, 15, 10, 0)


def _cfg(**kwargs) -> BalanceConfig:
    defaults = dict(
        trigger_threshold=0.05,
        stop_threshold=0.02,
        max_charge_w=2000,
        target_soc=100,
        allow_grid=True,
        max_runtime_h=6,
        cooldown_days=14,
        voltage_v=51.2,
    )
    defaults.update(kwargs)
    return BalanceConfig(**defaults)


def _ctx(
    *,
    imbalance: float | None = None,
    last_run: datetime | None = None,
    balance_requested: bool = True,
    tariff_type: TariffType = TariffType.FLAT,
    tomorrow_kwh: float | None = 15.0,
    consumption_tomorrow: float | None = 8.0,
    battery_soc: float = 60.0,
    capacity_kwh: float = 10.0,
    peak_today_w: float | None = None,
    peak_tomorrow_w: float | None = None,
    peak_reference_w: float | None = None,
    balance: BalanceConfig | None = None,
) -> DecisionContext:
    tariff = TariffConfig(
        tariff_type=tariff_type,
        flat_rate=4.32 if tariff_type == TariffType.FLAT else None,
        day_rate=4.32 if tariff_type == TariffType.DUAL else None,
        night_rate=1.68 if tariff_type == TariffType.DUAL else None,
        night_start=time(23, 0) if tariff_type == TariffType.DUAL else None,
        night_end=time(7, 0) if tariff_type == TariffType.DUAL else None,
    )
    return DecisionContext(
        telemetry=TelemetrySnapshot(battery_soc=battery_soc),
        forecast=ForecastSnapshot(
            tomorrow_kwh=tomorrow_kwh,
            consumption_tomorrow_kwh=consumption_tomorrow,
            peak_today_w=peak_today_w,
            peak_tomorrow_w=peak_tomorrow_w,
            peak_reference_w=peak_reference_w,
        ),
        tariff=tariff,
        battery=BatteryConfig(capacity_kwh=capacity_kwh),
        mode=EnergyMode.BALANCING,
        now=_NOW,
        min_soc=20,
        target_soc=80,
        sun=_SUN,
        balance=balance or _cfg(),
        balance_requested=balance_requested,
        balance_imbalance=imbalance,
        balance_last_run=last_run,
    )


strategy = BalancingStrategy()


class TestBalancingIdle:
    def test_no_imbalance_entity_returns_idle(self):
        plan = strategy.evaluate(_ctx(imbalance=None))
        assert plan.strategy == "balancing"
        assert len(plan.slots) == 6
        assert all(not s.charge_from_grid for s in plan.slots)
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_IDLE in codes

    def test_below_trigger_returns_idle(self):
        plan = strategy.evaluate(_ctx(imbalance=0.01))  # trigger=0.05
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_IDLE in codes
        assert all(not s.charge_from_grid for s in plan.slots)

    def test_idle_note_mentions_imbalance(self):
        plan = strategy.evaluate(_ctx(imbalance=0.01))
        assert any("0.01" in n or "trigger" in n.lower() for n in plan.notes)


class TestBalancingCooldown:
    def test_cooldown_not_elapsed_returns_idle(self):
        last_run = _NOW - timedelta(days=3)  # cooldown=14d, only 3d elapsed
        plan = strategy.evaluate(_ctx(imbalance=0.10, last_run=last_run))
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_COOLDOWN in codes
        assert all(not s.charge_from_grid for s in plan.slots)

    def test_cooldown_elapsed_proceeds(self):
        last_run = _NOW - timedelta(days=15)  # 15d > cooldown=14d
        plan = strategy.evaluate(_ctx(imbalance=0.10, last_run=last_run))
        codes = [s.reason for s in plan.slots]
        # Should NOT be cooldown
        assert RecommendationCode.BALANCING_COOLDOWN not in codes


class TestBalancingPostponeToPV:
    """When tomorrow PV can fully cover load + top-up AND risk is low, postpone to PV window."""

    def _pv_ctx(self) -> DecisionContext:
        # tomorrow=15 kWh, consumption=8 kWh, soc=60% of 10kWh → kwh_to_full=(100-60)/100*10=4
        # need 8+4=12 ≤ 15 ✓, clear sky (peak=ref) → risk≈0
        return _ctx(
            imbalance=0.10,
            battery_soc=60.0,
            capacity_kwh=10.0,
            tomorrow_kwh=15.0,
            consumption_tomorrow=8.0,
            peak_today_w=4000.0,
            peak_tomorrow_w=4000.0,
            peak_reference_w=4000.0,
        )

    def test_postponed_pv_code_present(self):
        plan = strategy.evaluate(self._pv_ctx())
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_POSTPONED_PV in codes

    def test_postponed_slots_no_grid_charge(self):
        plan = strategy.evaluate(self._pv_ctx())
        assert all(not s.charge_from_grid for s in plan.slots)

    def test_postponed_slot_has_max_power_w(self):
        plan = strategy.evaluate(self._pv_ctx())
        pv_slot = next(s for s in plan.slots if s.reason == RecommendationCode.BALANCING_POSTPONED_PV)
        assert pv_slot.max_power_w == 2000

    def test_postponed_slot_has_full_soc_target(self):
        plan = strategy.evaluate(self._pv_ctx())
        pv_slot = next(s for s in plan.slots if s.reason == RecommendationCode.BALANCING_POSTPONED_PV)
        assert pv_slot.target_soc == 100

    def test_postponed_note_mentions_pv(self):
        plan = strategy.evaluate(self._pv_ctx())
        assert any("pv" in n.lower() or "postponed" in n.lower() or "adj_pv" in n.lower() for n in plan.notes)


class TestBalancingNightSchedule:
    """When PV is insufficient or risky, schedule in cheap night window (dual tariff)."""

    def _night_ctx(self) -> DecisionContext:
        # tomorrow PV=3 kWh cloudy, consumption=8 → not enough for PV postpone
        return _ctx(
            imbalance=0.10,
            battery_soc=60.0,
            capacity_kwh=10.0,
            tomorrow_kwh=3.0,
            consumption_tomorrow=8.0,
            tariff_type=TariffType.DUAL,
        )

    def test_night_code_present(self):
        plan = strategy.evaluate(self._night_ctx())
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_SCHEDULED_NIGHT in codes

    def test_night_slot_charges_from_grid(self):
        plan = strategy.evaluate(self._night_ctx())
        night_slot = next(s for s in plan.slots if s.reason == RecommendationCode.BALANCING_SCHEDULED_NIGHT)
        assert night_slot.charge_from_grid is True

    def test_night_slot_has_max_power_w(self):
        plan = strategy.evaluate(self._night_ctx())
        night_slot = next(s for s in plan.slots if s.reason == RecommendationCode.BALANCING_SCHEDULED_NIGHT)
        assert night_slot.max_power_w == 2000

    def test_exactly_six_slots(self):
        plan = strategy.evaluate(self._night_ctx())
        assert len(plan.slots) == 6

    def test_slots_sorted(self):
        plan = strategy.evaluate(self._night_ctx())
        times = [s.start_time for s in plan.slots]
        assert times == sorted(times)


class TestBalancingFlatFallback:
    """Flat tariff → schedule in overnight window 00:00–max_runtime_h."""

    def _flat_ctx(self) -> DecisionContext:
        return _ctx(
            imbalance=0.10,
            battery_soc=60.0,
            capacity_kwh=10.0,
            tomorrow_kwh=3.0,
            consumption_tomorrow=8.0,
            tariff_type=TariffType.FLAT,
        )

    def test_active_code_present(self):
        plan = strategy.evaluate(self._flat_ctx())
        codes = [s.reason for s in plan.slots]
        assert RecommendationCode.BALANCING_ACTIVE in codes

    def test_first_slot_at_midnight(self):
        plan = strategy.evaluate(self._flat_ctx())
        assert plan.slots[0].start_time == time(0, 0)

    def test_first_slot_max_power_set(self):
        plan = strategy.evaluate(self._flat_ctx())
        first = plan.slots[0]
        assert first.max_power_w == 2000

    def test_exactly_six_slots(self):
        plan = strategy.evaluate(self._flat_ctx())
        assert len(plan.slots) == 6


class TestBalancingNoGridFallback:
    """When allow_grid=False, flat fallback slot should not charge from grid."""

    def test_no_grid_charge_when_disallowed(self):
        plan = strategy.evaluate(
            _ctx(
                imbalance=0.10,
                tomorrow_kwh=3.0,
                consumption_tomorrow=8.0,
                tariff_type=TariffType.FLAT,
                balance=_cfg(allow_grid=False),
            )
        )
        assert all(not s.charge_from_grid for s in plan.slots)


class TestBalancingSlotInvariants:
    def test_all_slots_valid_soc(self):
        plan = strategy.evaluate(_ctx(imbalance=0.10))
        for s in plan.slots:
            assert 0 <= s.target_soc <= 100

    def test_all_slots_have_reason_code(self):
        plan = strategy.evaluate(_ctx(imbalance=0.10))
        for s in plan.slots:
            assert isinstance(s.reason, RecommendationCode)
