"""Backup strategy: keep battery charged as a priority."""

from __future__ import annotations

from datetime import datetime, time

from ..base import Strategy
from ..context import DecisionContext
from ..plan import collapse_to_six, estimate_savings_uah
from ..signals import expected_deficit_kwh
from ...const import RecommendationCode, TariffType
from ...models import Plan, PlanSlot


_BACKUP_TARGET_SOC = 90


class BackupStrategy(Strategy):
    """Keep battery at *backup* level at all times.

    * Flat tariff: charge from grid 24/7, SoC=90.
    * Dual tariff: aggressively top-up during cheap window (SoC=100),
      maintain SoC=90 during expensive window without grid charging.
    """

    name = "backup"

    def evaluate(self, ctx: DecisionContext) -> Plan:  # noqa: D102
        now: datetime = ctx.now  # type: ignore[assignment]
        target = min(max(ctx.target_soc, _BACKUP_TARGET_SOC), 100)
        notes: list[str] = [f"Backup mode: maintaining SoC ≥ {target}%"]

        deficit = expected_deficit_kwh(ctx.forecast)

        if (
            ctx.tariff.tariff_type == TariffType.DUAL
            and ctx.tariff.night_start is not None
            and ctx.tariff.night_end is not None
        ):
            night_start = ctx.tariff.night_start  # type: ignore[assignment]
            night_end = ctx.tariff.night_end  # type: ignore[assignment]
            midnight_is_cheap = night_start > night_end

            notes.append(
                f"Dual tariff: charging at 100% during {night_start.strftime('%H:%M')}–{night_end.strftime('%H:%M')}"
            )

            slots: list[PlanSlot] = [
                PlanSlot(
                    time(0, 0),
                    100 if midnight_is_cheap else target,
                    midnight_is_cheap,
                    None,
                    RecommendationCode.BACKUP_MODE,
                ),
                PlanSlot(night_end, target, False, None, RecommendationCode.BACKUP_MODE),
            ]

            if not midnight_is_cheap:
                slots.append(PlanSlot(night_start, 100, True, None, RecommendationCode.BACKUP_MODE))
        else:
            # Flat tariff: charge 24/7
            slots = [PlanSlot(time(0, 0), target, True, None, RecommendationCode.BACKUP_MODE)]

        slots = collapse_to_six(slots)

        plan = Plan(
            slots=slots,
            generated_at=now,
            strategy=self.name,
            expected_balance_kwh=-deficit if deficit is not None else None,
            notes=notes,
        )
        plan.estimated_savings_uah = estimate_savings_uah(plan, ctx.tariff, deficit)
        return plan
