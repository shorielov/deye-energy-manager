"""Tests for the Smart Energy coordinator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from homeassistant.core import HomeAssistant

from custom_components.smart_energy_manager.const import DOMAIN
from custom_components.smart_energy_manager.coordinator import SmartEnergyCoordinator
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

    # Make home_consumption entity unavailable so no valid history and kw=None
    hass.states.async_set("sensor.home_consumption", "unavailable")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    forecast = coordinator.data.forecast
    recommendation = coordinator.data.recommendation

    assert forecast.consumption_tomorrow_kwh is None
    # Both consumption sources are None, so balance cannot be calculated
    assert recommendation.expected_balance_kwh is None