"""Decision engine dispatcher."""

from __future__ import annotations

from .context import DecisionContext
from .strategies.balanced import BalancedStrategy
from .strategies.backup import BackupStrategy
from .strategies.eco import EcoStrategy
from ..const import EnergyMode
from ..models import Plan


_STRATEGIES = {
    EnergyMode.ECO: EcoStrategy,
    EnergyMode.BACKUP: BackupStrategy,
}


def decide(ctx: DecisionContext) -> Plan:
    """Route *ctx* to the appropriate strategy and return a 6-slot Plan.

    Unknown modes (``winter``, ``autonomous``) fall back to ``balanced``
    with a note appended.
    """
    strategy_cls = _STRATEGIES.get(ctx.mode, BalancedStrategy)
    plan = strategy_cls().evaluate(ctx)

    if ctx.mode not in _STRATEGIES and ctx.mode != EnergyMode.BALANCED:
        plan.notes.append(
            f"Mode '{ctx.mode}' not yet implemented; using balanced strategy as fallback"
        )

    return plan
