"""Solarman adapter (davidrapan/ha-solarman integration)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .base import InverterAdapter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..models import Plan

_LOGGER = logging.getLogger(__name__)

# davidrapan/ha-solarman entity naming (Deye deye_p3.yaml profile):
#   {platform}.{device_slug}_program_{n}_{attr}
# n = 1..6, device_slug defaults to "inverter"
_PROG_COUNT = 6


def _time_entity(slug: str, n: int) -> str:
    return f"time.{slug}_program_{n}_time"


def _soc_entity(slug: str, n: int) -> str:
    return f"number.{slug}_program_{n}_soc"


def _charging_entity(slug: str, n: int) -> str:
    return f"select.{slug}_program_{n}_charging"


def _charge_current_entity(slug: str, n: int) -> str:
    return f"number.{slug}_program_{n}_charge_current"


class SolarmanAdapter(InverterAdapter):
    """Write the Plan to davidrapan/ha-solarman TOU entities.

    Entity naming convention (Deye deye_p3.yaml profile)::

        time.{slug}_program_{N}_time        → slot start HH:MM
        number.{slug}_program_{N}_soc       → target SoC (%)
        select.{slug}_program_{N}_charging  → "Grid" | "Disabled"

    *device_name* must match the device name configured in the Solarman
    integration entry (default ``"inverter"``).
    """

    name = "solarman"

    def __init__(self, device_name: str = "inverter") -> None:
        self._slug = device_name.strip().lower().replace(" ", "_") if device_name else "inverter"
        self._voltage_v: float = 51.2

    async def async_apply_plan(self, hass: "HomeAssistant", plan: "Plan") -> None:
        """Write all 6 plan slots to the inverter in parallel."""
        tasks = []
        for i, slot in enumerate(plan.slots[:_PROG_COUNT], start=1):
            tasks.append(self._write_slot(hass, i, slot))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results, start=1):
            if isinstance(result, Exception):
                _LOGGER.error("Failed to write Solarman slot %d: %s", i, result)

    async def _write_slot(self, hass: "HomeAssistant", n: int, slot: object) -> None:
        """Write time, SoC, charging-mode, and optionally charge current for slot *n*."""
        time_str = slot.start_time.strftime("%H:%M")  # type: ignore[attr-defined]
        soc = slot.target_soc  # type: ignore[attr-defined]
        charge = slot.charge_from_grid  # type: ignore[attr-defined]
        max_power_w: int | None = slot.max_power_w  # type: ignore[attr-defined]

        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": _time_entity(self._slug, n), "time": time_str},
            blocking=True,
        )
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": _soc_entity(self._slug, n), "value": str(soc)},
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": _charging_entity(self._slug, n), "option": "Grid" if charge else "Disabled"},
            blocking=True,
        )

        # Best-effort: write charge current when the inverter exposes the entity
        if max_power_w is not None:
            current_entity = _charge_current_entity(self._slug, n)
            if hass.states.get(current_entity) is not None:
                try:
                    # Default battery voltage 51.2 V; W → A rounded to 1 decimal
                    voltage_v: float = getattr(self, "_voltage_v", 51.2)
                    amps = round(max_power_w / voltage_v, 1)
                    await hass.services.async_call(
                        "number",
                        "set_value",
                        {"entity_id": current_entity, "value": str(amps)},
                        blocking=True,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.debug("Could not set charge current for slot %d", n)

    @classmethod
    def is_available(cls, hass: "HomeAssistant") -> bool:
        """Return True when at least the first program charging entity exists."""
        return hass.states.get("select.inverter_program_1_charging") is not None
