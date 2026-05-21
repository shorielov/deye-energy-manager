"""PV output baseline and peak reference estimation from Recorder statistics."""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PEAK_HISTORY_DAYS = 28
BASELINE_HISTORY_DAYS = 14
CACHE_TTL_SECONDS = 3600
MIN_PEAK_SAMPLES = 3


class PvBaselineForecaster:
    """Estimate PV clear-sky peak reference and daily kWh baseline from Recorder stats.

    Peak reference: 90th percentile of daily-max values over 28 days.
    Baseline kWh: median of the top-50 % of daily totals over 14 days.
    Both are cached for :data:`CACHE_TTL_SECONDS` seconds.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        # cache: key → (result, expires_at)
        self._cache: dict[str, tuple[tuple[float | None, int], datetime]] = {}

    def invalidate_cache(self) -> None:
        """Drop all cached results."""
        self._cache.clear()

    async def async_peak_reference_w(
        self,
        entity_id: str | None,
        now: datetime,
    ) -> tuple[float | None, int]:
        """Return ``(p90_peak_w, sample_count)`` from 28 days of daily-max stats.

        Returns ``(None, count)`` when fewer than :data:`MIN_PEAK_SAMPLES` valid
        days are available.
        """
        if not entity_id:
            return None, 0

        cache_key = f"peak:{entity_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            result, expires_at = cached
            if expires_at > now:
                return result

        values = await self._fetch_daily_max(entity_id, PEAK_HISTORY_DAYS, units="W")
        valid = [v for v in values if v > 0]

        if len(valid) < MIN_PEAK_SAMPLES:
            result = (None, len(valid))
        else:
            sorted_vals = sorted(valid)
            # 90th-percentile index (0-based, rounding down)
            p90_idx = max(0, int(len(sorted_vals) * 0.9) - 1)
            p90 = sorted_vals[p90_idx]
            result = (round(p90, 1), len(valid))

        self._cache[cache_key] = (result, now + timedelta(seconds=CACHE_TTL_SECONDS))
        return result

    async def async_baseline_kwh(
        self,
        entity_id: str | None,
        now: datetime,
    ) -> tuple[float | None, int]:
        """Return ``(median_of_top_50pct_daily_kwh, sample_count)`` from 14 days.

        Returns ``(None, 0)`` when no data is available.
        """
        if not entity_id:
            return None, 0

        cache_key = f"baseline:{entity_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            result, expires_at = cached
            if expires_at > now:
                return result

        values = await self._fetch_daily_max(entity_id, BASELINE_HISTORY_DAYS, units="kWh")
        valid = [v for v in values if v > 0]

        if not valid:
            result = (None, 0)
        else:
            sorted_vals = sorted(valid)
            top_half = sorted_vals[len(sorted_vals) // 2 :]
            baseline = round(statistics.median(top_half), 3)
            result = (baseline, len(valid))

        self._cache[cache_key] = (result, now + timedelta(seconds=CACHE_TTL_SECONDS))
        return result

    async def _fetch_daily_max(
        self,
        entity_id: str,
        history_days: int,
        units: str,
    ) -> list[float]:
        """Return list of daily max values from Recorder statistics.

        *units* should be ``"W"`` for power sensors or ``"kWh"`` for energy sensors.
        """
        try:
            from homeassistant.components.recorder import get_instance  # noqa: PLC0415
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.debug("Recorder not available; skipping PV baseline fetch")
            return []

        end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=history_days)

        unit_map: dict[str, dict[str, str]] = {
            "W": {"power": "W"},
            "kWh": {"energy": "kWh"},
        }
        stat_units = unit_map.get(units, {})

        def _fetch() -> list[float]:
            stats: dict = statistics_during_period(  # type: ignore[type-arg]
                self._hass,
                start_time=start,
                end_time=end,
                statistic_ids={entity_id},
                period="day",
                units=stat_units,
                types={"max"},
            )
            rows = stats.get(entity_id, [])
            result: list[float] = []
            for row in rows:
                val = row.get("max")
                if val is not None and val >= 0:
                    result.append(round(float(val), 3))
            return result

        try:
            instance = get_instance(self._hass)
            return await instance.async_add_executor_job(_fetch)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to fetch PV stats for %s", entity_id)
            return []
