"""Switch platform for Smart Energy Manager."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_AUTO_APPLY_RECOMMENDATIONS, CONF_MODE, DOMAIN, EnergyMode
from .entity import SmartEnergyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy switches."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SmartEnergyModeSwitch(coordinator, "eco_mode", "ECO Mode", EnergyMode.ECO),
            SmartEnergyModeSwitch(coordinator, "winter_mode", "Winter Mode", EnergyMode.WINTER),
            SmartEnergyOptionSwitch(
                coordinator,
                "auto_apply",
                "Auto Apply Recommendations",
                CONF_AUTO_APPLY_RECOMMENDATIONS,
            ),
        ]
    )


class SmartEnergyModeSwitch(SmartEnergyEntity, SwitchEntity):
    """Switch that maps to a strategy mode."""

    def __init__(self, coordinator, key: str, name: str, mode: EnergyMode) -> None:
        """Initialize the switch."""

        super().__init__(coordinator, key, name)
        self._mode = mode

    @property
    def is_on(self) -> bool:
        """Return whether this mode is active."""

        return self.coordinator.config_entry.options.get(
            CONF_MODE,
            self.coordinator.config_entry.data.get(CONF_MODE, EnergyMode.BALANCED),
        ) == self._mode

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the mode."""

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, CONF_MODE: self._mode},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Return to balanced mode when the switch is turned off."""

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, CONF_MODE: EnergyMode.BALANCED},
        )
        await self.coordinator.async_request_refresh()


class SmartEnergyOptionSwitch(SmartEnergyEntity, SwitchEntity):
    """Switch that toggles a boolean option."""

    def __init__(self, coordinator, key: str, name: str, option_key: str) -> None:
        """Initialize the switch."""

        super().__init__(coordinator, key, name)
        self._option_key = option_key

    @property
    def is_on(self) -> bool:
        """Return the option state."""

        return bool(
            self.coordinator.config_entry.options.get(
                self._option_key,
                self.coordinator.config_entry.data.get(self._option_key, False),
            )
        )

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the option on."""

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, self._option_key: True},
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the option off."""

        self.hass.config_entries.async_update_entry(
            self.coordinator.config_entry,
            options={**self.coordinator.config_entry.options, self._option_key: False},
        )
        await self.coordinator.async_request_refresh()