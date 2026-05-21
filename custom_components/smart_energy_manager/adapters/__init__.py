"""Adapter factory."""

from __future__ import annotations

from .base import InverterAdapter
from .noop import NoopAdapter
from .solarman import SolarmanAdapter
from .sunsynk import SunsynkAdapter


def get_adapter(adapter_type: str, entity_prefix: str = "", device_name: str = "inverter") -> InverterAdapter:
    """Return the adapter instance for *adapter_type*."""
    if adapter_type == "sunsynk":
        return SunsynkAdapter(entity_prefix=entity_prefix)
    if adapter_type == "solarman":
        return SolarmanAdapter(device_name=device_name)
    return NoopAdapter()
