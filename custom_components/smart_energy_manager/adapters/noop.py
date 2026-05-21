"""No-op adapter: logs the plan, writes nothing to the inverter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import InverterAdapter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..models import Plan

_LOGGER = logging.getLogger(__name__)


class NoopAdapter(InverterAdapter):
    """Default adapter for users who wire automations manually."""

    name = "none"

    async def async_apply_plan(self, hass: "HomeAssistant", plan: "Plan") -> None:
        """Log the plan slots; perform no writes."""
        _LOGGER.debug(
            "NoopAdapter: plan '%s' generated at %s with %d slots (no writes performed)",
            plan.strategy,
            plan.generated_at.isoformat(),
            len(plan.slots),
        )
        for i, slot in enumerate(plan.slots, start=1):
            _LOGGER.debug(
                "  Slot %d: %s  SoC=%d%%  charge=%s  reason=%s",
                i,
                slot.start_time.strftime("%H:%M"),
                slot.target_soc,
                slot.charge_from_grid,
                slot.reason,
            )

    @classmethod
    def is_available(cls, hass: "HomeAssistant") -> bool:
        return True
