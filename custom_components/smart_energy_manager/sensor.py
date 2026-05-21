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
    ATTR_CONSUMPTION_SOURCE,
    ATTR_CONSUMPTION_TODAY_KWH,
    ATTR_CONSUMPTION_TOMORROW_KWH,
    ATTR_ESTIMATED_SAVINGS,
    ATTR_EXPECTED_BALANCE,
    ATTR_FORECAST_CONFIDENCE,
    ATTR_REASON_CODES,
    ATTR_SMART_LOAD_TODAY_KWH,
    ATTR_TODAY_LOAD_KWH,
    DOMAIN,
)
from .coordinator import SmartEnergyCoordinator
from .entity import SmartEnergyEntity
from .models import EnergyState


@dataclass(frozen=True, kw_only=True)
class SmartEnergySensorDescription(SensorEntityDescription):
    """Description for Smart Energy sensors."""

    value_fn: Callable[[EnergyState], float | int | str | None]
    extra_attrs_fn: Callable[[EnergyState], dict[str, object]] | None = None


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
    all_descriptions = list(SENSORS) + list(_plan_sensors())
    async_add_entities(SmartEnergySensor(coordinator, description) for description in all_descriptions)


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

        if self.entity_description.extra_attrs_fn is not None:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)

        recommendation = self.coordinator.data.recommendation
        forecast = self.coordinator.data.forecast
        telemetry = self.coordinator.data.telemetry
        return {
            ATTR_ESTIMATED_SAVINGS: recommendation.estimated_savings,
            ATTR_REASON_CODES: [code.value for code in recommendation.reason_codes],
            ATTR_FORECAST_CONFIDENCE: forecast.confidence,
            ATTR_EXPECTED_BALANCE: recommendation.expected_balance_kwh,
            ATTR_ACTIVE_MODE: recommendation.active_mode.value,
            ATTR_CONSUMPTION_TODAY_KWH: forecast.consumption_today_kwh,
            ATTR_CONSUMPTION_TOMORROW_KWH: forecast.consumption_tomorrow_kwh,
            ATTR_CONSUMPTION_CONFIDENCE: forecast.consumption_confidence,
            ATTR_CONSUMPTION_SOURCE: forecast.consumption_source.value,
            ATTR_TODAY_LOAD_KWH: telemetry.today_load_consumption_kwh,
            ATTR_SMART_LOAD_TODAY_KWH: telemetry.smart_load_today_kwh,
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


# ---------------------------------------------------------------------------
# Plan entities
# ---------------------------------------------------------------------------


def _slot_start_value(n: int) -> Callable[[EnergyState], str | None]:
    def fn(state: EnergyState) -> str | None:
        if state.plan is None or len(state.plan.slots) < n:
            return None
        t = state.plan.slots[n - 1].start_time
        return f"{t.hour:02d}:{t.minute:02d}"
    return fn


def _slot_soc_value(n: int) -> Callable[[EnergyState], int | None]:
    def fn(state: EnergyState) -> int | None:
        if state.plan is None or len(state.plan.slots) < n:
            return None
        return state.plan.slots[n - 1].target_soc
    return fn


def _plan_attrs(state: EnergyState) -> dict[str, object]:
    if state.plan is None:
        return {}
    return {
        "slots": [
            {
                "start": f"{s.start_time.hour:02d}:{s.start_time.minute:02d}",
                "target_soc": s.target_soc,
                "charge_from_grid": s.charge_from_grid,
                "max_power_w": s.max_power_w,
                "reason": s.reason,
            }
            for s in state.plan.slots
        ],
        "strategy": state.plan.strategy,
        "generated_at": state.plan.generated_at.isoformat(),
        "estimated_savings_uah": state.plan.estimated_savings_uah,
        "expected_balance_kwh": state.plan.expected_balance_kwh,
        "notes": state.plan.notes,
    }


def _plan_sensors() -> list[SmartEnergySensorDescription]:
    """Return descriptions for plan rollup + 6-slot start/soc sensors."""
    sensors: list[SmartEnergySensorDescription] = [
        SmartEnergySensorDescription(
            key="plan",
            name="Energy Plan",
            value_fn=lambda state: state.plan.strategy if state.plan else None,
            extra_attrs_fn=_plan_attrs,
        )
    ]
    for n in range(1, 7):
        sensors.append(
            SmartEnergySensorDescription(
                key=f"plan_slot_{n}_start",
                name=f"Plan Slot {n} Start",
                value_fn=_slot_start_value(n),
            )
        )
        sensors.append(
            SmartEnergySensorDescription(
                key=f"plan_slot_{n}_target_soc",
                name=f"Plan Slot {n} Target SOC",
                native_unit_of_measurement=PERCENTAGE,
                value_fn=_slot_soc_value(n),
            )
        )
    return sensors