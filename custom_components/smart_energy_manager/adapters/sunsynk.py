"""Sunsynk / Deye adapter (kellerza/sunsynk integration)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .base import InverterAdapter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..models import Plan

_LOGGER = logging.getLogger(__name__)

# kellerza/sunsynk entity naming:  {prefix}prog{n}_{attribute}
# n = 1..6, attributes: time, capacity, charge
_PROG_COUNT = 6


def _entity_id(prefix: str, n: int, attr: str) -> str:
    """Build entity_id for a Sunsynk TOU slot entity."""
    if prefix:
        return f"{attr}.{prefix}prog{n}_{attr.split('.')[0]}"
    return f"{attr}.prog{n}_{attr.split('.')[0] if '.' in attr else attr}"


def _time_entity(prefix: str, n: int) -> str:
    return f"time.{prefix}prog{n}_time" if prefix else f"time.prog{n}_time"


def _capacity_entity(prefix: str, n: int) -> str:
    return f"number.{prefix}prog{n}_capacity" if prefix else f"number.prog{n}_capacity"


def _charge_entity(prefix: str, n: int) -> str:
    return f"switch.{prefix}prog{n}_charge" if prefix else f"switch.prog{n}_charge"


class SunsynkAdapter(InverterAdapter):
    """Write the Plan to kellerza/sunsynk TOU entities.

    Entity naming convention::

        time.prog{N}_time            → slot start HH:MM
        number.prog{N}_capacity      → target SoC (%)
        switch.prog{N}_charge        → charge from grid on/off

    An optional entity prefix (e.g. ``"inverter_"`` → ``time.inverter_prog1_time``)
    is supported for setups with custom device names.
    """

    name = "sunsynk"

    def __init__(self, entity_prefix: str = "") -> None:
        self._prefix = entity_prefix.rstrip("_") + "_" if entity_prefix else ""

    async def async_apply_plan(self, hass: "HomeAssistant", plan: "Plan") -> None:
        """Write all 6 plan slots to the inverter in parallel."""
        tasks = []
        for i, slot in enumerate(plan.slots[:_PROG_COUNT], start=1):
            tasks.append(self._write_slot(hass, i, slot))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results, start=1):
            if isinstance(result, Exception):
                _LOGGER.error("Failed to write Sunsynk slot %d: %s", i, result)

    async def _write_slot(self, hass: "HomeAssistant", n: int, slot: object) -> None:
        """Write time, capacity, and charge for slot *n*."""
        time_str = slot.start_time.strftime("%H:%M")  # type: ignore[attr-defined]
        capacity = slot.target_soc  # type: ignore[attr-defined]
        charge = slot.charge_from_grid  # type: ignore[attr-defined]

        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": _time_entity(self._prefix, n), "time": time_str},
            blocking=True,
        )
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _capacity_entity(self._prefix, n), "value": str(capacity)},
            blocking=True,
        )
        service = "turn_on" if charge else "turn_off"
        await hass.services.async_call(
            "switch",
            service,
            {"entity_id": _charge_entity(self._prefix, n)},
            blocking=True,
        )

    @classmethod
    def is_available(cls, hass: "HomeAssistant") -> bool:
        """Return True when at least the first prog capacity entity exists."""
        return hass.states.get("number.prog1_capacity") is not None
