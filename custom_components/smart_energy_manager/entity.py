"""Shared entity helpers for Smart Energy Manager."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartEnergyCoordinator


class SmartEnergyEntity(CoordinatorEntity[SmartEnergyCoordinator]):
    """Base entity for Smart Energy Manager."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartEnergyCoordinator, key: str, name: str) -> None:
        """Initialize the entity."""

        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
            "name": "Smart Energy Manager",
            "manufacturer": "Custom Integration",
            "entry_type": "service",
        }