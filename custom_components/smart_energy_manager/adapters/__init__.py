"""Adapter factory."""

from __future__ import annotations

from .base import InverterAdapter
from .noop import NoopAdapter
from .sunsynk import SunsynkAdapter


def get_adapter(adapter_type: str, entity_prefix: str = "") -> InverterAdapter:
    """Return the adapter instance for *adapter_type*."""
    if adapter_type == "sunsynk":
        return SunsynkAdapter(entity_prefix=entity_prefix)
    return NoopAdapter()
