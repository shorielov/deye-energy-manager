"""Energy history regression tests independent of a live Home Assistant."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import asyncio

import pytest

from custom_components.smart_energy_manager.consumption_forecast import (
    ConsumptionForecaster,
    _daily_totals_from_statistics,
)


def _history(day, days=1):
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Europe/Kyiv"))
    end = start + timedelta(days=days)
    # Recorder's cumulative sum at the end of each hourly bucket.
    rows = [
        {"start": ts, "sum": 100 + i, "max": None}
        for i, ts in enumerate(range(int(start.timestamp()) - 3600, int(end.timestamp()), 3600))
    ]
    return start, end, rows


@pytest.mark.parametrize("day,hours", [
    ("2026-10-16", 24), ("2026-03-29", 23), ("2026-10-25", 25),
])
def test_daily_sum_deltas_respect_local_midnight_and_dst(day, hours):
    start, end, rows = _history(day)
    assert _daily_totals_from_statistics(rows, start, end) == {start.date(): hours}


def test_daily_sensor_state_reset_does_not_reset_cumulative_sum():
    start, end, rows = _history("2026-10-16", 2)
    for i, row in enumerate(rows):
        row["state"] = i % 24
    assert list(_daily_totals_from_statistics(rows, start, end).values()) == [24, 24]


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), -100])
def test_invalid_sum_discards_day_instead_of_underestimating(bad):
    start, end, rows = _history("2026-10-16")
    rows[10]["sum"] = bad
    assert _daily_totals_from_statistics(rows, start, end) == {}


def test_missing_hour_discards_only_affected_day():
    start, end, rows = _history("2026-10-15", 2)
    del rows[10]
    assert _daily_totals_from_statistics(rows, start, end) == {
        (start + timedelta(days=1)).date(): 24,
    }


def test_missing_anchor_discards_first_day():
    start, end, rows = _history("2026-10-15", 2)
    assert _daily_totals_from_statistics(rows[1:], start, end) == {
        (start + timedelta(days=1)).date(): 24,
    }


def test_zero_consumption_hours_are_valid_and_current_day_excluded():
    start, end, rows = _history("2026-10-16")
    for row in rows:
        row["sum"] = 100
    rows.append({"start": end.timestamp(), "sum": 110})
    assert _daily_totals_from_statistics(rows, start, end) == {start.date(): 0}


def test_smart_load_is_aligned_by_date_not_position():
    forecaster = ConsumptionForecaster(SimpleNamespace())
    day = datetime(2026, 10, 1, tzinfo=UTC).date()
    async def fetch(entity_id):
        if entity_id == "total":
            return {day: 10, day + timedelta(days=1): 20}
        return {day + timedelta(days=1): 5}
    forecaster._fetch_daily_totals = fetch
    value, _ = asyncio.run(forecaster.async_estimate("total", "smart"))
    assert value == 15


def test_configured_missing_smart_load_does_not_become_zero():
    forecaster = ConsumptionForecaster(SimpleNamespace())
    async def fetch(entity_id):
        return {datetime(2026, 10, 1).date(): 10} if entity_id == "total" else {}
    forecaster._fetch_daily_totals = fetch
    assert asyncio.run(forecaster.async_estimate("total", "smart")) == (None, 0)
