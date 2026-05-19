"""Tests for the Smart Energy coordinator."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.smart_energy_manager.const import DOMAIN, ConsumptionSource
from custom_components.smart_energy_manager.coordinator import SmartEnergyCoordinator, _float_state
from custom_components.smart_energy_manager.models import TelemetrySnapshot


async def test_coordinator_builds_recommendation(
    hass: HomeAssistant, setup_integration
) -> None:
    """Coordinator should expose placeholder recommendation data."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    assert coordinator.data.recommendation.target_soc == 80
    assert coordinator.data.recommendation.energy_deficit is True
    assert coordinator.data.recommendation.should_charge is True
    assert coordinator.data.forecast.confidence == 1.0


async def test_consumption_forecast_no_history(
    hass: HomeAssistant, setup_integration
) -> None:
    """Empty history should return None for all consumption forecast values."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    today, tomorrow, confidence = coordinator._estimate_consumption_forecast()

    assert today is None
    assert tomorrow is None
    assert confidence is None


async def test_consumption_forecast_sparse_history(
    hass: HomeAssistant, setup_integration
) -> None:
    """Sparse history (< 2 distinct hours) should return a conservative estimate."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    ts = datetime(2026, 5, 19, 10, 0, 0, tzinfo=UTC)
    coordinator._telemetry_history.append(
        TelemetrySnapshot(home_consumption_kw=1.0, updated_at=ts)
    )

    today, tomorrow, confidence = coordinator._estimate_consumption_forecast()

    # Conservative estimate: 1.0 kW * 24 * 0.9 = 21.6 kWh
    assert today is not None
    assert today == pytest.approx(21.6, rel=0.01)
    assert tomorrow == today
    assert confidence is not None
    assert confidence <= 0.5


async def test_consumption_forecast_sufficient_history(
    hass: HomeAssistant, setup_integration
) -> None:
    """24 distinct hours of history should produce a full-confidence forecast."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    base = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    for h in range(24):
        coordinator._telemetry_history.append(
            TelemetrySnapshot(
                home_consumption_kw=0.5,
                updated_at=base.replace(hour=h),
            )
        )

    today, tomorrow, confidence = coordinator._estimate_consumption_forecast()

    # 24 hours * 0.5 kW = 12.0 kWh/day
    assert today == pytest.approx(12.0, rel=0.01)
    assert tomorrow == today
    assert confidence == 1.0


async def test_consumption_forecast_partial_history(
    hass: HomeAssistant, setup_integration
) -> None:
    """12 distinct hours should produce 0.5 confidence and fill gaps with mean."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    base = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    for h in range(12):
        coordinator._telemetry_history.append(
            TelemetrySnapshot(
                home_consumption_kw=0.5,
                updated_at=base.replace(hour=h),
            )
        )

    today, tomorrow, confidence = coordinator._estimate_consumption_forecast()

    assert today == pytest.approx(12.0, rel=0.01)
    assert confidence == pytest.approx(0.5, rel=0.01)


async def test_recommendation_uses_consumption_forecast(
    hass: HomeAssistant, setup_integration
) -> None:
    """Expected balance should use consumption_tomorrow_kwh when history is available."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    base = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    for h in range(24):
        coordinator._telemetry_history.append(
            TelemetrySnapshot(
                home_consumption_kw=0.5,
                updated_at=base.replace(hour=h),
            )
        )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    recommendation = coordinator.data.recommendation

    assert forecast.consumption_tomorrow_kwh is not None
    # forecast.tomorrow_kwh == 4.0 (set in setup_integration fixture)
    expected = coordinator.data.forecast.tomorrow_kwh - forecast.consumption_tomorrow_kwh
    assert recommendation.expected_balance_kwh == pytest.approx(expected, rel=0.01)


async def test_recommendation_without_consumption_data(
    hass: HomeAssistant, setup_integration
) -> None:
    """When home_consumption entity is unavailable, expected balance should be None."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    # Disable all consumption inputs so every cascade branch returns None
    hass.states.async_set("sensor.home_consumption", "unavailable")
    hass.states.async_set("sensor.today_load_consumption", "unavailable")
    hass.states.async_set("sensor.smart_load_today", "unavailable")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    recommendation = coordinator.data.recommendation

    assert forecast.consumption_tomorrow_kwh is None
    # All consumption sources are None, so balance cannot be calculated
    assert recommendation.expected_balance_kwh is None


# ---------------------------------------------------------------------------
# Statistics-based priority chain
# ---------------------------------------------------------------------------


async def test_statistics_path_sets_source_and_tomorrow(
    hass: HomeAssistant, setup_integration
) -> None:
    """When the statistics forecaster returns a value it should be preferred."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]

    # Patch the forecaster to return a known statistics result
    coordinator._consumption_forecaster.async_estimate = AsyncMock(
        return_value=(13.5, 0.9)
    )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    assert forecast.consumption_tomorrow_kwh == pytest.approx(13.5, abs=0.01)
    assert forecast.consumption_confidence == pytest.approx(0.9, abs=0.01)
    assert forecast.consumption_source == ConsumptionSource.STATISTICS


async def test_power_history_fallback_when_stats_empty(
    hass: HomeAssistant, setup_integration
) -> None:
    """Power-history path should be used when statistics returns (None, 0.0)."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()

    # Statistics return nothing
    coordinator._consumption_forecaster.async_estimate = AsyncMock(
        return_value=(None, 0.0)
    )

    # Build 24 h of power history so _estimate_consumption_forecast has data
    base = datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    for h in range(24):
        coordinator._telemetry_history.append(
            TelemetrySnapshot(home_consumption_kw=0.5, updated_at=base.replace(hour=h))
        )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    assert forecast.consumption_tomorrow_kwh is not None
    assert forecast.consumption_source == ConsumptionSource.POWER_HISTORY


async def test_live_baseline_overrides_today_estimate(
    hass: HomeAssistant, setup_integration
) -> None:
    """Live energy counters (total − smart) should override today's power-based estimate."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._consumption_forecaster.async_estimate = AsyncMock(
        return_value=(None, 0.0)
    )

    # setup_integration sets today_load=12.5 kWh, smart_load=2.5 kWh → baseline=10.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Live baseline = 12.5 - 2.5 = 10.0
    assert coordinator.data.forecast.consumption_today_kwh == pytest.approx(10.0, abs=0.01)
    assert coordinator.data.telemetry.today_load_consumption_kwh == pytest.approx(12.5, abs=0.01)
    assert coordinator.data.telemetry.smart_load_today_kwh == pytest.approx(2.5, abs=0.01)


async def test_no_stats_no_history_source_is_none(
    hass: HomeAssistant, setup_integration
) -> None:
    """When both statistics and power history are empty, source should be NONE."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()
    coordinator._consumption_forecaster.async_estimate = AsyncMock(
        return_value=(None, 0.0)
    )

    hass.states.async_set("sensor.home_consumption", "unavailable")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    assert forecast.consumption_tomorrow_kwh is None
    assert forecast.consumption_source == ConsumptionSource.NONE


# ---------------------------------------------------------------------------
# Balance fallback: live-counter extrapolation
# ---------------------------------------------------------------------------


async def test_recommendation_uses_live_counter_extrapolation(
    hass: HomeAssistant, setup_integration
) -> None:
    """When no consumption estimate is available, extrapolate from today\'s live counter."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][setup_integration.entry_id]
    coordinator._telemetry_history.clear()
    coordinator._consumption_forecaster.async_estimate = AsyncMock(return_value=(None, 0.0))

    # No power sensor → no power-history path
    hass.states.async_set("sensor.home_consumption", "unavailable")
    # Set partial-day counters: live_today = 6.0 - 1.0 = 5.0 kWh at noon
    hass.states.async_set("sensor.today_load_consumption", "6.0")
    hass.states.async_set("sensor.smart_load_today", "1.0")

    # Freeze local time at noon: hours_elapsed = 12 → proxy = 5.0 * 24 / 12 = 10.0
    # forecast.tomorrow_kwh = 4.0 (fixture) → expected_balance = 4.0 - 10.0 = -6.0
    noon = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    with patch("homeassistant.util.dt.now", return_value=noon):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert coordinator.data.recommendation.expected_balance_kwh == pytest.approx(-6.0, abs=0.01)


# ---------------------------------------------------------------------------
# Unit conversion in _float_state
# ---------------------------------------------------------------------------


async def test_float_state_normalizes_w_to_kw(
    hass: HomeAssistant, setup_integration
) -> None:
    """_float_state should convert a W sensor to kW when expected_unit='kW'."""

    hass.states.async_set("sensor.test_power", "1500", {"unit_of_measurement": "W"})
    result = _float_state(hass, "sensor.test_power", expected_unit="kW")
    assert result == pytest.approx(1.5, abs=1e-6)


async def test_float_state_normalizes_wh_to_kwh(
    hass: HomeAssistant, setup_integration
) -> None:
    """_float_state should convert a Wh sensor to kWh when expected_unit='kWh'."""

    hass.states.async_set("sensor.test_energy", "8500", {"unit_of_measurement": "Wh"})
    result = _float_state(hass, "sensor.test_energy", expected_unit="kWh")
    assert result == pytest.approx(8.5, abs=1e-6)


async def test_float_state_no_unit_passthrough(
    hass: HomeAssistant, setup_integration
) -> None:
    """_float_state should return raw value when entity has no unit_of_measurement."""

    hass.states.async_set("sensor.test_unitless", "42.5")
    result = _float_state(hass, "sensor.test_unitless", expected_unit="kW")
    assert result == pytest.approx(42.5, abs=1e-6)