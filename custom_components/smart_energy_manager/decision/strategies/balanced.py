"""Balanced strategy: cost-aware charging during the cheap tariff window."""

from __future__ import annotations

from datetime import datetime, time

from ..base import Strategy
from ..context import DecisionContext
from ..plan import collapse_to_six, estimate_savings_uah
from ..signals import expected_deficit_kwh, headroom_battery_kwh, risk_adjusted_pv_kwh, weather_risk
from ...const import RecommendationCode, TariffType
from ...models import Plan, PlanSlot


class BalancedStrategy(Strategy):
    """Charge from grid only when dual-tariff savings justify it.

    Slot layout for dual tariff + sufficient deficit:

    00:00 (or night_start when window doesn't span midnight)
          → depending on cheap-window position, either charge or idle
    night_end → idle / let PV do its work
    sunrise+1h → continue PV window
    12:00 → peak PV / hold charge
    sunset-1h → discharge through evening peak
    night_start → start charging again (if wrap-around window)

    For flat tariff, a single no-charge template is used.
    """

    name = "balanced"

    def evaluate(self, ctx: DecisionContext) -> Plan:  # noqa: D102
        now: datetime = ctx.now  # type: ignore[assignment]
        sun = ctx.sun
        sunrise = sun.sunrise if sun else time(6, 0)
        sunset = sun.sunset if sun else time(20, 0)
        sunrise_plus1 = time(min(sunrise.hour + 1, 23), sunrise.minute)
        sunset_minus1 = time(max(sunset.hour - 1, 0), sunset.minute)

        raw_deficit = expected_deficit_kwh(ctx.forecast)
        headroom = headroom_battery_kwh(ctx.telemetry, ctx.battery, ctx.target_soc)
        risk = weather_risk(ctx.forecast)
        adj_pv = risk_adjusted_pv_kwh(ctx.forecast)

        # Risk-adjusted deficit: use adj_pv if available, else raw tomorrow_kwh
        adj_deficit: float | None = None
        if ctx.forecast.consumption_tomorrow_kwh is not None:
            pv_for_deficit = adj_pv if adj_pv is not None else ctx.forecast.tomorrow_kwh
            if pv_for_deficit is not None:
                adj_deficit = round(ctx.forecast.consumption_tomorrow_kwh - pv_for_deficit, 3)

        # Lower grid-charge threshold when weather risk is high
        grid_charge_threshold = 1.0 if risk > 0.5 else 2.0

        use_grid = (
            ctx.tariff.tariff_type == TariffType.DUAL
            and ctx.tariff.night_start is not None
            and ctx.tariff.night_end is not None
            and adj_deficit is not None
            and adj_deficit > grid_charge_threshold
            and headroom > 2.0
        )

        notes: list[str] = []

        if not use_grid:
            if ctx.tariff.tariff_type == TariffType.FLAT:
                notes.append("Flat tariff: no grid charging scheduled")
            elif adj_deficit is None:
                notes.append("Forecast data missing; defaulting to PV-only mode")
            elif adj_deficit <= grid_charge_threshold:
                notes.append(f"Deficit {adj_deficit:.1f} kWh too small; skipping grid charge")
            else:
                notes.append(f"Battery headroom {headroom:.1f} kWh too low; skipping grid charge")

            slots: list[PlanSlot] = [
                PlanSlot(time(0, 0), ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunrise_plus1, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(time(12, 0), ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
            ]
        else:
            night_start = ctx.tariff.night_start  # type: ignore[assignment]
            night_end = ctx.tariff.night_end  # type: ignore[assignment]
            notes.append(
                f"Charging from grid during cheap window {night_start.strftime('%H:%M')}–{night_end.strftime('%H:%M')}"
            )

            # Determine state at 00:00: are we inside the cheap window?
            midnight_is_cheap = night_start > night_end  # e.g. 23:00–07:00

            slots = [
                PlanSlot(
                    time(0, 0),
                    100 if midnight_is_cheap else ctx.target_soc,
                    midnight_is_cheap,
                    None,
                    RecommendationCode.CHEAP_TARIFF if midnight_is_cheap else RecommendationCode.PV_PRIORITY,
                ),
                PlanSlot(night_end, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunrise_plus1, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(time(12, 0), ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
            ]

            if not midnight_is_cheap:
                # Cheap window starts mid-day or evening (unusual but supported)
                slots.append(
                    PlanSlot(night_start, 100, True, None, RecommendationCode.CHEAP_TARIFF)
                )

        # Sort and deduplicate on start_time
        slots.sort(key=lambda s: s.start_time.hour * 60 + s.start_time.minute)
        seen: set[time] = set()
        unique: list[PlanSlot] = []
        for slot in slots:
            if slot.start_time not in seen:
                seen.add(slot.start_time)
                unique.append(slot)

        unique = collapse_to_six(unique)

        if adj_pv is not None and ctx.forecast.tomorrow_kwh is not None and abs(adj_pv - ctx.forecast.tomorrow_kwh) > 1.0:
            notes.append(
                f"Risk-adjusted PV: {adj_pv:.1f} kWh (risk={risk:.0%}, raw={ctx.forecast.tomorrow_kwh:.1f} kWh)"
            )

        plan = Plan(
            slots=unique,
            generated_at=now,
            strategy=self.name,
            expected_balance_kwh=-raw_deficit if raw_deficit is not None else None,
            notes=notes,
        )
        plan.estimated_savings_uah = estimate_savings_uah(plan, ctx.tariff, raw_deficit)
        return plan
