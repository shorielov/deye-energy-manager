"""Abstract base for inverter adapter implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..models import Plan


class InverterAdapter(ABC):
    """Write a Plan's 6 slots to the inverter via Home Assistant services."""

    name: str

    @abstractmethod
    async def async_apply_plan(self, hass: "HomeAssistant", plan: "Plan") -> None:
        """Apply *plan* to the inverter."""

    @classmethod
    @abstractmethod
    def is_available(cls, hass: "HomeAssistant") -> bool:
        """Return True if required inverter entities are registered in *hass*."""
