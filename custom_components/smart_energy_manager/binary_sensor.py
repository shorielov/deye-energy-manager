"""Binary sensors for Smart Energy Manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SmartEnergyCoordinator
from .entity import SmartEnergyEntity
from .models import EnergyState


@dataclass(frozen=True, kw_only=True)
class SmartEnergyBinarySensorDescription(BinarySensorEntityDescription):
    """Description for Smart Energy binary sensors."""

    value_fn: Callable[[EnergyState], bool]


BINARY_SENSORS: tuple[SmartEnergyBinarySensorDescription, ...] = (
    SmartEnergyBinarySensorDescription(
        key="should_charge",
        name="Should Charge",
        value_fn=lambda state: state.recommendation.should_charge,
    ),
    SmartEnergyBinarySensorDescription(
        key="bad_weather",
        name="Bad Weather",
        value_fn=lambda state: (state.recommendation.bad_weather_risk or 0) >= 0.65,
    ),
    SmartEnergyBinarySensorDescription(
        key="energy_deficit",
        name="Energy Deficit",
        value_fn=lambda state: state.recommendation.energy_deficit,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy binary sensors."""

    coordinator: SmartEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]
    all_descriptions = list(BINARY_SENSORS) + _plan_slot_charge_sensors()
    async_add_entities(
        SmartEnergyBinarySensor(coordinator, description) for description in all_descriptions
    )


class SmartEnergyBinarySensor(SmartEnergyEntity, BinarySensorEntity):
    """Representation of a Smart Energy binary sensor."""

    entity_description: SmartEnergyBinarySensorDescription

    def __init__(
        self,
        coordinator: SmartEnergyCoordinator,
        description: SmartEnergyBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""

        super().__init__(coordinator, description.key, description.name)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the binary state."""

        return self.entity_description.value_fn(self.coordinator.data)


# ---------------------------------------------------------------------------
# Plan slot charge sensors
# ---------------------------------------------------------------------------


def _slot_charge_value(n: int) -> Callable[[EnergyState], bool]:
    def fn(state: EnergyState) -> bool:
        if state.plan is None or len(state.plan.slots) < n:
            return False
        return state.plan.slots[n - 1].charge_from_grid
    return fn


def _plan_slot_charge_sensors() -> list[SmartEnergyBinarySensorDescription]:
    return [
        SmartEnergyBinarySensorDescription(
            key=f"plan_slot_{n}_charge",
            name=f"Plan Slot {n} Charge",
            value_fn=_slot_charge_value(n),
        )
        for n in range(1, 7)
    ]