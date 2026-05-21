"""Strategy abstract base class."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .context import DecisionContext
from ..models import Plan


class Strategy(ABC):
    """Base class for all decision strategies."""

    name: str

    @abstractmethod
    def evaluate(self, ctx: DecisionContext) -> Plan:
        """Produce a 6-slot Plan from the given context."""
