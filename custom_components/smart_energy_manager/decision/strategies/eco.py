"""ECO strategy: maximise PV self-consumption, never charge from grid."""

from __future__ import annotations

from datetime import datetime, time

from ..base import Strategy
from ..context import DecisionContext
from ..plan import collapse_to_six
from ..signals import weather_risk
from ...const import RecommendationCode
from ...models import Plan, PlanSlot


class EcoStrategy(Strategy):
    """Never charge from grid; raise target SoC when weather risk is high."""

    name = "eco"

    def evaluate(self, ctx: DecisionContext) -> Plan:  # noqa: D102
        now: datetime = ctx.now  # type: ignore[assignment]
        sun = ctx.sun
        sunrise = sun.sunrise if sun else time(6, 0)
        sunset = sun.sunset if sun else time(20, 0)
        sunrise_plus1 = time(min(sunrise.hour + 1, 23), sunrise.minute)
        sunset_minus1 = time(max(sunset.hour - 1, 0), sunset.minute)

        risk = weather_risk(ctx.forecast)
        # Smooth SoC bonus: risk 0.3 → +0, risk 0.5 → +5, risk 0.7 → +10, risk 0.9 → +15
        bonus = round(max(0.0, risk - 0.3) * 25)
        target = min(ctx.target_soc + bonus, 100)

        notes: list[str] = ["ECO mode: grid charging disabled"]
        if bonus > 0:
            notes.append(f"Weather risk {risk:.0%}: target SoC raised by {bonus}% to {target}%")

        slots: list[PlanSlot] = [
            PlanSlot(time(0, 0), target, False, None, RecommendationCode.NO_GRID_CHARGE),
            PlanSlot(sunrise_plus1, target, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(12, 0), target, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
        ]

        slots = collapse_to_six(slots)

        return Plan(
            slots=slots,
            generated_at=now,
            strategy=self.name,
            estimated_savings_uah=0.0,
            expected_balance_kwh=None,
            notes=notes,
        )
