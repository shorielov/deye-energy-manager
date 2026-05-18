"""Number platform for Smart Energy Manager."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MIN_SOC_OVERRIDE,
    CONF_TARGET_SOC_OVERRIDE,
    DEFAULT_MIN_SOC,
    DEFAULT_TARGET_SOC,
    DOMAIN,
)
from .entity import SmartEnergyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy override numbers."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SmartEnergyOverrideNumber(
                coordinator,
                "target_soc",
                "Target SOC Override",
                CONF_TARGET_SOC_OVERRIDE,
                DEFAULT_TARGET_SOC,
            ),
            SmartEnergyOverrideNumber(
                coordinator,
                "min_soc",
                "Minimum SOC Override",
                CONF_MIN_SOC_OVERRIDE,
                DEFAULT_MIN_SOC,
            ),
        ]
    )


class SmartEnergyOverrideNumber(SmartEnergyEntity, NumberEntity):
    """Config-entry-backed numeric override."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = "box"

    def __init__(
        self,
        coordinator,
        key: str,
        name: str,
        option_key: str,
        default_value: int,
    ) -> None:
        """Initialize the number entity."""

        super().__init__(coordinator, key, name)
        self._option_key = option_key
        self._default_value = default_value

    @property
    def native_value(self) -> float:
        """Return the current override value."""

        return float(
            self.coordinator.config_entry.options.get(
                self._option_key,
                self.coordinator.config_entry.data.get(self._option_key, self._default_value),
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the override value."""

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, self._option_key: int(value)},
        )
        await self.coordinator.async_request_refresh()