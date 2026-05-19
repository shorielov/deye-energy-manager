"""Shared pytest fixtures for Smart Energy Manager tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import custom_components
from homeassistant import loader
import pytest
import pytest_socket
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_energy_manager.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_FLAT_RATE,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_TODAY_ENTITY,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_GRID_EXPORT_ENTITY,
    CONF_GRID_IMPORT_ENTITY,
    CONF_HOME_CONSUMPTION_ENTITY,
    CONF_MODE,
    CONF_PV_GENERATION_TODAY_ENTITY,
    CONF_PV_POWER_ENTITY,
    CONF_SMART_LOAD_TODAY_ENTITY,
    CONF_TARIFF_TYPE,
    CONF_TODAY_LOAD_CONSUMPTION_ENTITY,
    DOMAIN,
    EnergyMode,
    TariffType,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def socket_enabled() -> None:
    """Enable sockets for all Home Assistant integration tests."""

    pytest_socket.enable_socket()


@pytest.fixture(autouse=True)
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Enable custom integrations defined in the test dir."""

    custom_components.__path__ = [str(Path(__file__).resolve().parent.parent / "custom_components")]
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)


@pytest.fixture
def event_loop(socket_enabled: None) -> asyncio.AbstractEventLoop:
    """Provide a selector-based loop on Windows for Home Assistant tests."""

    if sys.platform == "win32":
        policy = asyncio.WindowsSelectorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        loop = policy.new_event_loop()
    else:
        loop = asyncio.new_event_loop()

    yield loop
    loop.close()


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a config entry for tests."""

    return MockConfigEntry(
        domain=DOMAIN,
        title="Smart Energy Manager",
        data={
            CONF_BATTERY_SOC_ENTITY: "sensor.battery_soc",
            CONF_BATTERY_POWER_ENTITY: "sensor.battery_power",
            CONF_BATTERY_CAPACITY_KWH: 12.5,
            CONF_PV_POWER_ENTITY: "sensor.pv_power",
            CONF_PV_GENERATION_TODAY_ENTITY: "sensor.pv_generation_today",
            CONF_GRID_IMPORT_ENTITY: "sensor.grid_import",
            CONF_GRID_EXPORT_ENTITY: "sensor.grid_export",
            CONF_HOME_CONSUMPTION_ENTITY: "sensor.home_consumption",
            CONF_TODAY_LOAD_CONSUMPTION_ENTITY: "sensor.today_load_consumption",
            CONF_SMART_LOAD_TODAY_ENTITY: "sensor.smart_load_today",
            CONF_FORECAST_TODAY_ENTITY: "sensor.forecast_today",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.forecast_tomorrow",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.forecast_remaining",
            CONF_TARIFF_TYPE: TariffType.FLAT,
            CONF_FLAT_RATE: 4.5,
            CONF_MODE: EnergyMode.BALANCED,
        },
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the custom integration for tests."""

    mock_config_entry.add_to_hass(hass)

    hass.states.async_set("sensor.battery_soc", 35)
    hass.states.async_set("sensor.battery_power", -1.5)
    hass.states.async_set("sensor.pv_power", 2.8)
    hass.states.async_set("sensor.pv_generation_today", 8.0)
    hass.states.async_set("sensor.grid_import", 6.2)
    hass.states.async_set("sensor.grid_export", 1.1)
    hass.states.async_set("sensor.home_consumption", 0.75)
    hass.states.async_set("sensor.today_load_consumption", 12.5)
    hass.states.async_set("sensor.smart_load_today", 2.5)
    hass.states.async_set("sensor.forecast_today", 7.5)
    hass.states.async_set("sensor.forecast_tomorrow", 4.0)
    hass.states.async_set("sensor.forecast_remaining", 2.5)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry