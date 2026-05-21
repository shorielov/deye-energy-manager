"""Tests for decision.plan helpers (collapse_to_six, snap_to_tou_boundaries)."""

from __future__ import annotations

from datetime import datetime, time

from custom_components.smart_energy_manager.const import RecommendationCode, TariffType
from custom_components.smart_energy_manager.decision.plan import collapse_to_six, snap_to_tou_boundaries
from custom_components.smart_energy_manager.models import Plan, PlanSlot, TariffConfig


def _slot(hour: int, soc: int = 80, charge: bool = False) -> PlanSlot:
    return PlanSlot(
        start_time=time(hour, 0),
        target_soc=soc,
        charge_from_grid=charge,
        reason=RecommendationCode.PV_PRIORITY,
    )


def _flat_tariff() -> TariffConfig:
    return TariffConfig(tariff_type=TariffType.FLAT, flat_rate=4.32)


def _dual_tariff() -> TariffConfig:
    return TariffConfig(
        tariff_type=TariffType.DUAL,
        day_rate=4.32,
        night_rate=1.68,
        night_start=time(23, 0),
        night_end=time(7, 0),
    )


class TestCollapseToSix:
    def test_already_six_unchanged(self):
        slots = [_slot(h) for h in [0, 4, 8, 12, 16, 20]]
        result = collapse_to_six(slots)
        assert len(result) == 6

    def test_pads_fewer_than_six(self):
        slots = [_slot(0), _slot(12)]
        result = collapse_to_six(slots)
        assert len(result) == 6

    def test_collapses_more_than_six(self):
        # 8 identical slots → should merge to ≤6
        slots = [_slot(h, soc=80, charge=False) for h in range(8)]
        result = collapse_to_six(slots)
        assert len(result) == 6

    def test_result_sorted_by_start(self):
        slots = [_slot(h) for h in [0, 12]]
        result = collapse_to_six(slots)
        times = [s.start_time for s in result]
        assert times == sorted(times)

    def test_no_duplicate_start_hours(self):
        slots = [_slot(h) for h in [0, 4, 8, 12, 16, 20]]
        result = collapse_to_six(slots)
        hours = [s.start_time.hour for s in result]
        assert len(hours) == len(set(hours))

    def test_padding_uses_last_slot_values(self):
        last = _slot(0, soc=70, charge=True)
        result = collapse_to_six([last])
        # Padded slots should copy soc and charge from last slot
        for s in result[1:]:
            assert s.target_soc == 70
            assert s.charge_from_grid is True


class TestSnapToTouBoundaries:
    def test_flat_no_extra_times(self):
        times = [time(8, 0), time(14, 0)]
        result = snap_to_tou_boundaries(times, _flat_tariff())
        assert result == sorted(times)

    def test_dual_injects_boundaries(self):
        times = [time(8, 0), time(14, 0)]
        result = snap_to_tou_boundaries(times, _dual_tariff())
        result_set = set(result)
        assert time(23, 0) in result_set
        assert time(7, 0) in result_set

    def test_sorted_output(self):
        times = [time(14, 0), time(8, 0)]
        result = snap_to_tou_boundaries(times, _flat_tariff())
        assert result == sorted(result, key=lambda t: t.hour * 60 + t.minute)
