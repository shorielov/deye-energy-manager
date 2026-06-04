"""Balancing strategy: equalise cell/pack SoC divergence economically.

Decision tree
─────────────
1. No imbalance sensor or imbalance < trigger → idle (return to balanced-like plan).
2. Cooldown not elapsed → idle with cooldown note.
3. Tomorrow's risk-adjusted PV ≥ consumption_tomorrow + kWh-to-full AND risk < 0.4
   → postpone to tomorrow's PV window (no grid charge). Code: BALANCING_POSTPONED_PV.
4. Dual tariff available AND allow_grid → schedule in cheap night window at capped W.
   Code: BALANCING_SCHEDULED_NIGHT.
5. Fallback (flat tariff or no grid allowed) → schedule grid/PV charge in low-load
   overnight window (00:00–06:00) at capped W. Code: BALANCING_ACTIVE.

In all charging cases the balancing slot runs target_soc → CONF_BALANCE_TARGET_SOC
(default 100) with max_power_w = CONF_BALANCE_MAX_CHARGE_W. After the runtime cap
a final slot drops back to user target_soc / min_soc.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from ..base import Strategy
from ..context import DecisionContext
from ..plan import collapse_to_six
from ..signals import expected_deficit_kwh, headroom_battery_kwh, risk_adjusted_pv_kwh, weather_risk
from ...const import RecommendationCode
from ...models import BalanceConfig, Plan, PlanSlot


_DEFAULT_BALANCE = BalanceConfig()


class BalancingStrategy(Strategy):
    """Schedule battery balancing at the lowest-cost time given current forecasts."""

    name = "balancing"

    def evaluate(self, ctx: DecisionContext) -> Plan:  # noqa: D102
        now: datetime = ctx.now  # type: ignore[assignment]
        cfg: BalanceConfig = ctx.balance or _DEFAULT_BALANCE
        sun = ctx.sun
        sunrise = sun.sunrise if sun else time(6, 0)
        sunset = sun.sunset if sun else time(20, 0)
        sunrise_plus1 = time(min(sunrise.hour + 1, 23), sunrise.minute)
        sunset_minus1 = time(max(sunset.hour - 1, 0), sunset.minute)

        # ── 1. No imbalance / below trigger ──────────────────────────────
        imbalance = ctx.balance_imbalance
        if imbalance is None or imbalance < cfg.trigger_threshold:
            return self._idle_plan(
                now, ctx,
                sunrise_plus1, sunset_minus1,
                f"Imbalance {imbalance:.3f} < trigger {cfg.trigger_threshold:.3f}" if imbalance is not None
                else "No imbalance sensor reading available",
                RecommendationCode.BALANCING_IDLE,
            )

        # ── 2. Cooldown ───────────────────────────────────────────────────
        if ctx.balance_last_run is not None:
            last_run: datetime = ctx.balance_last_run  # type: ignore[assignment]
            cooldown_end = last_run + timedelta(days=cfg.cooldown_days)
            if now < cooldown_end:
                days_left = (cooldown_end - now).days
                return self._idle_plan(
                    now, ctx,
                    sunrise_plus1, sunset_minus1,
                    f"Balancing cooldown active; {days_left}d remaining (last run {last_run.date()})",
                    RecommendationCode.BALANCING_COOLDOWN,
                )

        # ── 3. Postpone to tomorrow PV window ────────────────────────────
        adj_pv = risk_adjusted_pv_kwh(ctx.forecast)
        risk = weather_risk(ctx.forecast)
        kwh_to_full = headroom_battery_kwh(ctx.telemetry, ctx.battery, cfg.target_soc)
        consumption_tomorrow = ctx.forecast.consumption_tomorrow_kwh or 0.0

        pv_can_cover = (
            adj_pv is not None
            and adj_pv >= consumption_tomorrow + kwh_to_full
            and risk < 0.4
        )
        if pv_can_cover:
            end_h = min(sunrise.hour + 1 + cfg.max_runtime_h, 23)
            pv_end = time(end_h, 0)
            notes = [
                f"Balancing postponed to tomorrow PV window ({sunrise_plus1.strftime('%H:%M')}–{pv_end.strftime('%H:%M')}): "
                f"adj_pv={adj_pv:.1f} kWh ≥ load {consumption_tomorrow:.1f} + top-up {kwh_to_full:.1f} kWh, risk={risk:.0%}",
                f"Imbalance: {imbalance:.3f} (trigger={cfg.trigger_threshold:.3f})",
            ]
            slots = [
                PlanSlot(time(0, 0), ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunrise_plus1, cfg.target_soc, False, cfg.max_charge_w, RecommendationCode.BALANCING_POSTPONED_PV),
                PlanSlot(pv_end, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
            ]
            return self._make_plan(now, ctx, slots, notes)

        # ── 4. Schedule in cheap night window ────────────────────────────
        from ...const import TariffType  # noqa: PLC0415
        if (
            ctx.tariff.tariff_type == TariffType.DUAL
            and ctx.tariff.night_start is not None
            and ctx.tariff.night_end is not None
            and cfg.allow_grid
        ):
            ns = ctx.tariff.night_start
            ne = ctx.tariff.night_end
            midnight_is_cheap = ns > ne
            end_h = (ne.hour + cfg.max_runtime_h) % 24
            balance_end = time(min(end_h, ne.hour), 0) if end_h >= ne.hour else time(ne.hour, 0)

            notes = [
                f"Balancing scheduled in cheap window {ns.strftime('%H:%M')}–{ne.strftime('%H:%M')} "
                f"at ≤{cfg.max_charge_w} W",
                f"Imbalance: {imbalance:.3f} (trigger={cfg.trigger_threshold:.3f}), risk={risk:.0%}",
            ]
            slots = [
                PlanSlot(
                    time(0, 0),
                    cfg.target_soc if midnight_is_cheap else ctx.target_soc,
                    midnight_is_cheap and cfg.allow_grid,
                    cfg.max_charge_w if midnight_is_cheap else None,
                    RecommendationCode.BALANCING_SCHEDULED_NIGHT if midnight_is_cheap else RecommendationCode.PV_PRIORITY,
                ),
                PlanSlot(ne, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunrise_plus1, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
                PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
            ]
            if not midnight_is_cheap:
                slots.append(
                    PlanSlot(ns, cfg.target_soc, True, cfg.max_charge_w, RecommendationCode.BALANCING_SCHEDULED_NIGHT)
                )
                slots.append(
                    PlanSlot(balance_end if balance_end != ne else time((ne.hour + 1) % 24, 0),
                             ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY)
                )
            return self._make_plan(now, ctx, slots, notes)

        # ── 5. Flat-tariff / no-grid fallback: overnight low-load window ─
        runtime_h = min(cfg.max_runtime_h, 6)
        bal_end = time(runtime_h, 0)
        notes = [
            f"Balancing scheduled 00:00–{bal_end.strftime('%H:%M')} (flat/no-grid fallback) "
            f"at ≤{cfg.max_charge_w} W",
            f"Imbalance: {imbalance:.3f} (trigger={cfg.trigger_threshold:.3f})",
        ]
        slots = [
            PlanSlot(time(0, 0), cfg.target_soc, cfg.allow_grid, cfg.max_charge_w, RecommendationCode.BALANCING_ACTIVE),
            PlanSlot(bal_end, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(sunrise_plus1, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
        ]
        return self._make_plan(now, ctx, slots, notes)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _idle_plan(
        self,
        now: datetime,
        ctx: DecisionContext,
        sunrise_plus1: time,
        sunset_minus1: time,
        reason: str,
        code: RecommendationCode,
    ) -> Plan:
        slots = [
            PlanSlot(time(0, 0), ctx.target_soc, False, None, code),
            PlanSlot(sunrise_plus1, ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(time(12, 0), ctx.target_soc, False, None, RecommendationCode.PV_PRIORITY),
            PlanSlot(sunset_minus1, ctx.min_soc, False, None, RecommendationCode.HIGH_CONSUMPTION),
        ]
        return self._make_plan(now, ctx, slots, [reason])

    def _make_plan(
        self,
        now: datetime,
        ctx: DecisionContext,
        slots: list[PlanSlot],
        notes: list[str],
    ) -> Plan:
        slots.sort(key=lambda s: s.start_time.hour * 60 + s.start_time.minute)
        seen: set[time] = set()
        unique: list[PlanSlot] = []
        for slot in slots:
            if slot.start_time not in seen:
                seen.add(slot.start_time)
                unique.append(slot)
        unique = collapse_to_six(unique)
        return Plan(
            slots=unique,
            generated_at=now,
            strategy=self.name,
            expected_balance_kwh=None,
            notes=notes,
        )
