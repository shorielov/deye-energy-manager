"""Unit tests for ConsumptionForecaster and helpers in consumption_forecast.py."""

from __future__ import annotations

import pytest

from custom_components.smart_energy_manager.consumption_forecast import (
    ConsumptionForecaster,
    _compute_baseline_series,
    _forecast_from_series,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestComputeBaselineSeries:
    def test_no_smart_series_returns_total(self) -> None:
        totals = [10.0, 12.0, 11.5]
        assert _compute_baseline_series(totals, []) == [10.0, 12.0, 11.5]

    def test_subtracts_smart_from_total(self) -> None:
        totals = [15.0, 14.0, 16.0]
        smart = [3.0, 2.0, 4.0]
        assert _compute_baseline_series(totals, smart) == [12.0, 12.0, 12.0]

    def test_clamps_negative_baseline_to_zero(self) -> None:
        totals = [5.0]
        smart = [8.0]  # smart > total → clamp
        result = _compute_baseline_series(totals, smart)
        assert result == [0.0]

    def test_short_smart_series_treats_missing_as_zero(self) -> None:
        totals = [10.0, 12.0, 11.0]
        smart = [2.0]  # only covers first day
        result = _compute_baseline_series(totals, smart)
        assert result == [8.0, 12.0, 11.0]


class TestForecastFromSeries:
    def test_empty_series_returns_none(self) -> None:
        tomorrow, confidence = _forecast_from_series([])
        assert tomorrow is None
        assert confidence == 0.0

    def test_all_zero_returns_none(self) -> None:
        tomorrow, confidence = _forecast_from_series([0.0, 0.0, 0.0])
        assert tomorrow is None
        assert confidence == 0.0

    def test_single_day_uses_mean(self) -> None:
        tomorrow, confidence = _forecast_from_series([12.0])
        assert tomorrow == pytest.approx(12.0, abs=0.01)
        assert confidence < 1.0

    def test_three_days_uses_median(self) -> None:
        # series [10, 11, 12] → median 11
        tomorrow, confidence = _forecast_from_series([10.0, 11.0, 12.0])
        assert tomorrow == pytest.approx(11.0, abs=0.01)
        assert confidence == pytest.approx(3 / 7, abs=0.01)

    def test_seven_days_full_confidence(self) -> None:
        series = [12.0, 13.0, 11.0, 14.0, 12.5, 11.5, 12.0]
        tomorrow, confidence = _forecast_from_series(series)
        assert confidence == pytest.approx(1.0, abs=0.01)
        assert tomorrow is not None

    def test_more_than_seven_uses_last_seven(self) -> None:
        # First 7 are high, last 7 are low → should use low ones
        high = [30.0] * 7
        low = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        _, confidence_all = _forecast_from_series(high + low)
        # Should take last 7 which are all 10
        tomorrow, _ = _forecast_from_series(high + low)
        assert tomorrow == pytest.approx(10.0, abs=0.01)
        assert confidence_all == pytest.approx(1.0, abs=0.01)

    def test_zeros_are_excluded_from_recent(self) -> None:
        # 5 zeros then 2 non-zero → recent = [8.0, 9.0]
        series = [0.0, 0.0, 0.0, 0.0, 0.0, 8.0, 9.0]
        tomorrow, confidence = _forecast_from_series(series)
        assert tomorrow == pytest.approx(8.5, abs=0.01)  # mean([8, 9])
        assert confidence == pytest.approx(2 / 7, abs=0.01)


# ---------------------------------------------------------------------------
# ConsumptionForecaster
# ---------------------------------------------------------------------------


@pytest.fixture
def forecaster(hass):
    return ConsumptionForecaster(hass)


class TestConsumptionForecaster:
    @pytest.mark.asyncio
    async def test_no_entity_returns_none_zero(self, forecaster) -> None:
        tomorrow, confidence = await forecaster.async_estimate(None, None)
        assert tomorrow is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_empty_totals_returns_none_zero(
        self, forecaster, monkeypatch
    ) -> None:
        async def mock_fetch(entity_id: str) -> list[float]:
            return []

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)
        tomorrow, confidence = await forecaster.async_estimate(
            "sensor.total_load", None
        )
        assert tomorrow is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_sufficient_history_uses_median(
        self, forecaster, monkeypatch
    ) -> None:
        total = [15.0, 14.0, 16.0, 15.5, 14.5, 15.2, 15.8]
        smart = [3.0, 2.0, 4.0, 3.5, 2.5, 3.2, 3.8]
        # baseline per day = [12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0]

        async def mock_fetch(entity_id: str) -> list[float]:
            return total if "total" in entity_id else smart

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)
        tomorrow, confidence = await forecaster.async_estimate(
            "sensor.total_load", "sensor.smart_load"
        )
        assert confidence == pytest.approx(1.0, abs=0.01)
        assert tomorrow == pytest.approx(12.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_sparse_history_uses_mean(self, forecaster, monkeypatch) -> None:
        total = [14.0, 16.0]  # only 2 days
        smart = [2.0, 4.0]
        # baseline = [12.0, 12.0]

        async def mock_fetch(entity_id: str) -> list[float]:
            return total if "total" in entity_id else smart

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)
        tomorrow, confidence = await forecaster.async_estimate(
            "sensor.total_load", "sensor.smart_load"
        )
        assert tomorrow == pytest.approx(12.0, abs=0.01)
        assert confidence == pytest.approx(2 / 7, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_smart_entity_baseline_equals_total(
        self, forecaster, monkeypatch
    ) -> None:
        total = [12.0, 13.0, 11.0, 14.0, 12.5, 11.5, 12.0]

        async def mock_fetch(entity_id: str) -> list[float]:
            return total

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)
        tomorrow, confidence = await forecaster.async_estimate(
            "sensor.total_load", None
        )
        # No smart entity → baseline = total
        assert confidence == pytest.approx(1.0, abs=0.01)
        assert tomorrow is not None

    @pytest.mark.asyncio
    async def test_smart_exceeds_total_clamped_to_zero(
        self, forecaster, monkeypatch
    ) -> None:
        total = [10.0, 10.0, 10.0]
        smart = [15.0, 15.0, 15.0]  # smart > total every day → baseline = 0

        async def mock_fetch(entity_id: str) -> list[float]:
            return total if "total" in entity_id else smart

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)
        tomorrow, confidence = await forecaster.async_estimate(
            "sensor.total_load", "sensor.smart_load"
        )
        # All baseline values are 0 → excluded → returns None
        assert tomorrow is None
        assert confidence == 0.0

    @pytest.mark.asyncio
    async def test_cache_avoids_second_fetch(self, forecaster, monkeypatch) -> None:
        call_count = 0

        async def mock_fetch(entity_id: str) -> list[float]:
            nonlocal call_count
            call_count += 1
            return [12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.0]

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)

        result1 = await forecaster.async_estimate("sensor.total", None)
        result2 = await forecaster.async_estimate("sensor.total", None)

        # _fetch_daily_totals called once (for first estimate only)
        assert call_count == 1
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_invalidate_cache_forces_refetch(
        self, forecaster, monkeypatch
    ) -> None:
        call_count = 0

        async def mock_fetch(entity_id: str) -> list[float]:
            nonlocal call_count
            call_count += 1
            return [12.0] * 7

        monkeypatch.setattr(forecaster, "_fetch_daily_totals", mock_fetch)

        await forecaster.async_estimate("sensor.total", None)
        forecaster.invalidate_cache()
        await forecaster.async_estimate("sensor.total", None)

        assert call_count == 2
