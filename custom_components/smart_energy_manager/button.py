"""Button platform for Smart Energy Manager."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SmartEnergyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Energy buttons."""

    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SmartEnergyBalanceButton(coordinator),
            SmartEnergyBalanceCancelButton(coordinator),
        ]
    )


class SmartEnergyBalanceButton(SmartEnergyEntity, ButtonEntity):
    """Button that requests a battery balancing run."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "start_balance", "Start Battery Balancing")

    async def async_press(self) -> None:
        """Handle button press — arm balancing and refresh."""
        await self.coordinator.request_balance()


class SmartEnergyBalanceCancelButton(SmartEnergyEntity, ButtonEntity):
    """Button that cancels an active battery balancing request."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cancel_balance", "Cancel Battery Balancing")

    async def async_press(self) -> None:
        """Handle button press — disarm balancing and refresh."""
        await self.coordinator.cancel_balance()
