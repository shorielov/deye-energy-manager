"""Unit tests for PvBaselineForecaster in pv_baseline.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.smart_energy_manager.pv_baseline import (
    CACHE_TTL_SECONDS,
    MIN_PEAK_SAMPLES,
    PvBaselineForecaster,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)


def _make_forecaster(daily_max_values: list[float]) -> PvBaselineForecaster:
    """Return a PvBaselineForecaster whose _fetch_daily_max is mocked."""
    hass = MagicMock()
    forecaster = PvBaselineForecaster(hass)
    forecaster._fetch_daily_max = AsyncMock(return_value=daily_max_values)  # type: ignore[method-assign]
    return forecaster


# ---------------------------------------------------------------------------
# async_peak_reference_w
# ---------------------------------------------------------------------------


class TestPeakReferenceW:
    @pytest.mark.asyncio
    async def test_no_entity_returns_none(self) -> None:
        hass = MagicMock()
        forecaster = PvBaselineForecaster(hass)
        result, count = await forecaster.async_peak_reference_w(None, NOW)
        assert result is None
        assert count == 0

    @pytest.mark.asyncio
    async def test_fewer_than_min_samples_returns_none(self) -> None:
        values = [3000.0] * (MIN_PEAK_SAMPLES - 1)
        forecaster = _make_forecaster(values)
        result, count = await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        assert result is None
        assert count == len(values)

    @pytest.mark.asyncio
    async def test_exact_min_samples_returns_p90(self) -> None:
        values = [3000.0] * MIN_PEAK_SAMPLES
        forecaster = _make_forecaster(values)
        result, count = await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        assert result is not None
        assert count == MIN_PEAK_SAMPLES

    @pytest.mark.asyncio
    async def test_28_days_p90_correct(self) -> None:
        # 28 values from 1000 to 4000 W in steps; p90 index = int(28*0.9)-1 = 24
        values = [float(1000 + i * 100) for i in range(28)]  # 1000…3700
        forecaster = _make_forecaster(values)
        result, count = await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        sorted_vals = sorted(values)
        expected_p90 = sorted_vals[max(0, int(28 * 0.9) - 1)]
        assert result == pytest.approx(expected_p90, abs=0.1)
        assert count == 28

    @pytest.mark.asyncio
    async def test_zeros_excluded(self) -> None:
        # 10 zeros + 20 real values; zeros should be filtered
        values = [0.0] * 10 + [3500.0] * 20
        forecaster = _make_forecaster(values)
        result, count = await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        assert result is not None
        assert count == 20  # only non-zero

    @pytest.mark.asyncio
    async def test_cache_avoids_second_fetch(self) -> None:
        values = [3000.0] * 10
        forecaster = _make_forecaster(values)
        await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        # _fetch_daily_max should have been called only once
        assert forecaster._fetch_daily_max.call_count == 1  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_cache_invalidated_by_invalidate_cache(self) -> None:
        values = [3000.0] * 10
        forecaster = _make_forecaster(values)
        await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        forecaster.invalidate_cache()
        await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        assert forecaster._fetch_daily_max.call_count == 2  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self) -> None:
        values = [3000.0] * 10
        forecaster = _make_forecaster(values)
        await forecaster.async_peak_reference_w("sensor.peak_today", NOW)
        future = NOW + timedelta(seconds=CACHE_TTL_SECONDS + 1)
        await forecaster.async_peak_reference_w("sensor.peak_today", future)
        assert forecaster._fetch_daily_max.call_count == 2  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# async_baseline_kwh
# ---------------------------------------------------------------------------


class TestBaselineKwh:
    @pytest.mark.asyncio
    async def test_no_entity_returns_none(self) -> None:
        hass = MagicMock()
        forecaster = PvBaselineForecaster(hass)
        result, count = await forecaster.async_baseline_kwh(None, NOW)
        assert result is None
        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_returns_none(self) -> None:
        forecaster = _make_forecaster([])
        result, count = await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        assert result is None
        assert count == 0

    @pytest.mark.asyncio
    async def test_all_zeros_returns_none(self) -> None:
        forecaster = _make_forecaster([0.0] * 5)
        result, count = await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        assert result is None
        assert count == 0

    @pytest.mark.asyncio
    async def test_median_of_top_half(self) -> None:
        # 14 values, sorted: [5,6,7,8,9,10,11,12,13,14,15,16,17,18]
        # top half (7 values): [12,13,14,15,16,17,18], median=15
        values = list(range(5, 19))  # 5..18, 14 values
        forecaster = _make_forecaster(values)
        result, count = await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        assert result is not None
        assert result == pytest.approx(15.0, abs=0.01)
        assert count == 14

    @pytest.mark.asyncio
    async def test_single_value(self) -> None:
        forecaster = _make_forecaster([20.0])
        result, count = await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        assert result == pytest.approx(20.0, abs=0.001)
        assert count == 1

    @pytest.mark.asyncio
    async def test_cache_avoids_second_fetch(self) -> None:
        values = [10.0, 12.0, 11.0]
        forecaster = _make_forecaster(values)
        await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        await forecaster.async_baseline_kwh("sensor.forecast_today", NOW)
        assert forecaster._fetch_daily_max.call_count == 1  # type: ignore[attr-defined]
