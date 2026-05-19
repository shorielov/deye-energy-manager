"""Sensor platform for Smart Energy Manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_ACTIVE_MODE,
    ATTR_CONSUMPTION_CONFIDENCE,
    ATTR_CONSUMPTION_TODAY_KWH,
    ATTR_CONSUMPTION_TOMORROW_KWH,
    ATTR_ESTIMATED_SAVINGS,
    ATTR_EXPECTED_BALANCE,
    ATTR_FORECAST_CONFIDENCE,
    ATTR_REASON_CODES,
    DOMAIN,
)
from .coordinator import SmartEnergyCoordinator
from .entity import SmartEnergyEntity
from .models import EnergyState


@dataclass(frozen=True, kw_only=True)
class SmartEnergySensorDescription(SensorEntityDescription):
    """Description for Smart Energy sensors."""

    value_fn: Callable[[EnergyState], float | int | str | None]


SENSORS: tuple[SmartEnergySensorDescription, ...] = (
    SmartEnergySensorDescription(
        key="target_soc",
        name="Target SOC",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: state.recommendation.target_soc,
    ),
    SmartEnergySensorDescription(
        key="forecast_balance",
        name="Forecast Balance",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.recommendation.expected_balance_kwh,
    ),
    SmartEnergySensorDescription(
        key="bad_weather_risk",
        name="Bad Weather Risk",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: round((state.recommendation.bad_weather_risk or 0) * 100, 1),
    ),
    SmartEnergySensorDescription(
        key="recommended_pv",
        name="Recommended PV Expansion",
        native_unit_of_measurement="kW",
        value_fn=lambda state: None,
    ),
    SmartEnergySensorDescription(
        key="grid_dependency",
        name="Grid Dependency",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: _grid_dependency(state),
    ),
    SmartEnergySensorDescription(
        key="energy_score",
        name="Energy Score",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda state: _energy_score(state),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy sensors from a config entry."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(SmartEnergySensor(coordinator, description) for description in SENSORS)


class SmartEnergySensor(SmartEnergyEntity, SensorEntity):
    """Representation of a Smart Energy sensor."""

    entity_description: SmartEnergySensorDescription

    def __init__(
        self,
        coordinator: SmartEnergyCoordinator,
        description: SmartEnergySensorDescription,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator, description.key, description.name)
        self.entity_description = description
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> float | int | str | None:
        """Return the entity state."""

        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return extra attributes for debugging and UI."""

        recommendation = self.coordinator.data.recommendation
        forecast = self.coordinator.data.forecast
        return {
            ATTR_ESTIMATED_SAVINGS: recommendation.estimated_savings,
            ATTR_REASON_CODES: [code.value for code in recommendation.reason_codes],
            ATTR_FORECAST_CONFIDENCE: forecast.confidence,
            ATTR_EXPECTED_BALANCE: recommendation.expected_balance_kwh,
            ATTR_ACTIVE_MODE: recommendation.active_mode.value,
            ATTR_CONSUMPTION_TODAY_KWH: forecast.consumption_today_kwh,
            ATTR_CONSUMPTION_TOMORROW_KWH: forecast.consumption_tomorrow_kwh,
            ATTR_CONSUMPTION_CONFIDENCE: forecast.consumption_confidence,
        }


def _grid_dependency(state: EnergyState) -> float | None:
    """Compute a simple dependency score from imported energy vs usage."""

    imported = state.telemetry.grid_import_kwh
    generated = state.forecast.today_kwh
    if imported is None or generated is None:
        return None
    total = imported + max(generated, 0)
    if total <= 0:
        return 0.0
    return round(imported / total * 100, 1)


def _energy_score(state: EnergyState) -> float | None:
    """Compute a simple energy independence score."""

    dependency = _grid_dependency(state)
    if dependency is None:
        return None
    return round(100 - dependency, 1)