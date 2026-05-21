"""Tests for the BackupStrategy."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.smart_energy_manager.const import EnergyMode, TariffType
from custom_components.smart_energy_manager.decision.context import DecisionContext
from custom_components.smart_energy_manager.decision.strategies.backup import BackupStrategy
from custom_components.smart_energy_manager.models import (
    BatteryConfig,
    ForecastSnapshot,
    TariffConfig,
    TelemetrySnapshot,
)


def _ctx(
    *,
    tariff_type: TariffType = TariffType.FLAT,
    battery_soc: float = 50.0,
    target_soc: int = 80,
    min_soc: int = 20,
) -> DecisionContext:
    dual_kwargs: dict = {}
    if tariff_type == TariffType.DUAL:
        dual_kwargs = {
            "day_rate": 4.32,
            "night_rate": 1.68,
            "night_start": time(23, 0),
            "night_end": time(7, 0),
        }
    tariff = TariffConfig(
        tariff_type=tariff_type,
        flat_rate=4.32 if tariff_type == TariffType.FLAT else None,
        **dual_kwargs,
    )
    return DecisionContext(
        telemetry=TelemetrySnapshot(battery_soc=battery_soc),
        forecast=ForecastSnapshot(tomorrow_kwh=5.0, confidence=0.8),
        tariff=tariff,
        battery=BatteryConfig(capacity_kwh=10.0),
        mode=EnergyMode.BACKUP,
        now=datetime(2024, 1, 15, 10, 0),
        min_soc=min_soc,
        target_soc=target_soc,
    )


strategy = BackupStrategy()


class TestBackupFlatTariff:
    def test_exactly_six_slots(self):
        assert len(strategy.evaluate(_ctx()).slots) == 6

    def test_all_slots_charge_true(self):
        plan = strategy.evaluate(_ctx())
        assert all(s.charge_from_grid for s in plan.slots)

    def test_high_target_soc(self):
        plan = strategy.evaluate(_ctx())
        # Backup on flat should keep a high SoC (≥90%)
        assert all(s.target_soc >= 90 for s in plan.slots)

    def test_strategy_name(self):
        assert strategy.evaluate(_ctx()).strategy == "backup"


class TestBackupDualTariff:
    def test_exactly_six_slots(self):
        assert len(strategy.evaluate(_ctx(tariff_type=TariffType.DUAL)).slots) == 6

    def test_slots_sorted_by_start(self):
        plan = strategy.evaluate(_ctx(tariff_type=TariffType.DUAL))
        times = [s.start_time for s in plan.slots]
        assert times == sorted(times)

    def test_night_slots_charge_true(self):
        """Cheap-window slots should have charge=True."""
        plan = strategy.evaluate(_ctx(tariff_type=TariffType.DUAL))
        # Slot at 23:00 should be charge=True
        night_slots = [s for s in plan.slots if s.start_time >= time(23, 0) or s.start_time < time(7, 0)]
        assert any(s.charge_from_grid for s in night_slots)
