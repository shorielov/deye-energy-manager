"""Plan slot helpers: boundary snapping, collapse-to-six, savings estimate."""

from __future__ import annotations

from datetime import time

from ..models import Plan, PlanSlot, TariffConfig


def _slot_minutes(s: PlanSlot) -> int:
    return s.start_time.hour * 60 + s.start_time.minute


def snap_to_tou_boundaries(times: list[time], tariff: TariffConfig) -> list[time]:
    """Return sorted list of *times* with TOU boundaries inserted when dual tariff."""
    result: set[time] = set(times)
    if tariff.night_start is not None:
        result.add(tariff.night_start)
    if tariff.night_end is not None:
        result.add(tariff.night_end)
    return sorted(result, key=lambda t: t.hour * 60 + t.minute)


def collapse_to_six(slots: list[PlanSlot]) -> list[PlanSlot]:
    """Merge adjacent identical slots until len ≤ 6, then pad to exactly 6."""
    merged = list(slots)

    # ---- merge ----
    while len(merged) > 6:
        merged_any = False
        for i in range(len(merged) - 1):
            a, b = merged[i], merged[i + 1]
            if a.target_soc == b.target_soc and a.charge_from_grid == b.charge_from_grid:
                merged[i] = PlanSlot(
                    start_time=a.start_time,
                    target_soc=a.target_soc,
                    charge_from_grid=a.charge_from_grid,
                    max_power_w=a.max_power_w or b.max_power_w,
                    reason=a.reason,
                )
                merged.pop(i + 1)
                merged_any = True
                break
        if not merged_any:
            # Cannot reduce by equality; just keep first 6
            merged = merged[:6]
            break

    # ---- pad ----
    if len(merged) < 6:
        used_hours = {s.start_time.hour for s in merged}
        last = merged[-1]
        # Distribute padding evenly: try 0, 4, 8, 12, 16, 20 first, then hours 2..23
        candidates = [0, 4, 8, 12, 16, 20, 2, 6, 10, 14, 18, 22, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23]
        for h in candidates:
            if len(merged) >= 6:
                break
            if h not in used_hours:
                used_hours.add(h)
                merged.append(
                    PlanSlot(
                        start_time=time(h, 0),
                        target_soc=last.target_soc,
                        charge_from_grid=last.charge_from_grid,
                        max_power_w=last.max_power_w,
                        reason=last.reason,
                    )
                )
        merged.sort(key=_slot_minutes)

    return merged


def estimate_savings_uah(
    plan: Plan,
    tariff: TariffConfig,
    expected_deficit: float | None,
) -> float:
    """Simple savings estimate: rate_delta × kWh covered from cheap-window charge."""
    if expected_deficit is None or expected_deficit <= 0:
        return 0.0
    if tariff.day_rate is None or tariff.night_rate is None:
        return 0.0
    delta = tariff.day_rate - tariff.night_rate
    if delta <= 0:
        return 0.0
    if not any(s.charge_from_grid for s in plan.slots):
        return 0.0
    return round(delta * min(expected_deficit, 20.0), 2)
