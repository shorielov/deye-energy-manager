"""Consumption forecaster using Home Assistant Recorder statistics."""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HISTORY_DAYS = 14
MIN_DAYS_FOR_MEDIAN = 3
CACHE_TTL_SECONDS = 3600


def _compute_baseline_series(
    total_series: list[float],
    smart_series: list[float],
) -> list[float]:
    """Subtract smart load from total for each day, clamping to 0.

    If ``smart_series`` is shorter than ``total_series`` the missing
    values are treated as 0 (i.e. no smart load recorded for that day).
    """

    result: list[float] = []
    for i, total in enumerate(total_series):
        smart = smart_series[i] if i < len(smart_series) else 0.0
        if smart > total:
            _LOGGER.warning(
                "Smart load (%.2f kWh) exceeds total load (%.2f kWh) for day index %d; "
                "clamping baseline to 0",
                smart,
                total,
                i,
            )
        result.append(max(total - smart, 0.0))
    return result


def _forecast_from_series(series: list[float]) -> tuple[float | None, float]:
    """Return ``(tomorrow_kwh, confidence)`` from a daily baseline series.

    Uses the median of the last 7 non-zero days when enough data is
    available; falls back to mean for sparse history.  Returns
    ``(None, 0.0)`` when no valid data exists.
    """

    recent = [v for v in series if v > 0][-7:]
    if not recent:
        return None, 0.0

    confidence = round(min(len(recent) / 7, 1.0), 2)
    if len(recent) >= MIN_DAYS_FOR_MEDIAN:
        tomorrow_kwh = round(statistics.median(recent), 3)
    else:
        tomorrow_kwh = round(statistics.mean(recent), 3)

    return tomorrow_kwh, confidence


class ConsumptionForecaster:
    """Fetch historical daily load totals and produce a consumption forecast.

    Statistics are fetched from the Home Assistant Recorder and cached
    for :data:`CACHE_TTL_SECONDS` seconds to avoid querying the DB on
    every coordinator update cycle.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise the forecaster."""

        self._hass = hass
        # cache: key → ((tomorrow_kwh, confidence), expires_at)
        self._cache: dict[
            tuple[str | None, str | None],
            tuple[tuple[float | None, float], datetime],
        ] = {}

    def invalidate_cache(self) -> None:
        """Drop all cached statistics results."""

        self._cache.clear()

    async def async_estimate(
        self,
        today_load_entity: str | None,
        smart_load_entity: str | None,
    ) -> tuple[float | None, float]:
        """Return ``(tomorrow_kwh, confidence)`` from recorder statistics.

        Returns ``(None, 0.0)`` when no entity is configured or when no
        statistics are available yet.
        """

        if not today_load_entity:
            return None, 0.0

        cache_key = (today_load_entity, smart_load_entity)
        now = datetime.now(UTC)

        cached = self._cache.get(cache_key)
        if cached is not None:
            result, expires_at = cached
            if expires_at > now:
                return result

        total_series = await self._fetch_daily_totals(today_load_entity)
        smart_series = (
            await self._fetch_daily_totals(smart_load_entity)
            if smart_load_entity
            else []
        )

        baseline = _compute_baseline_series(total_series, smart_series)
        result = _forecast_from_series(baseline)

        self._cache[cache_key] = (result, now + timedelta(seconds=CACHE_TTL_SECONDS))
        return result

    async def _fetch_daily_totals(self, entity_id: str) -> list[float]:
        """Return a list of daily consumption totals (kWh) via Recorder statistics.

        Uses the ``max`` statistic for each day, which equals the end-of-day
        accumulated value for daily-reset energy sensors (e.g. Deye
        *Today Load Consumption*).

        Returns an empty list when the Recorder is unavailable or has no
        data for the entity.
        """

        try:
            from homeassistant.components.recorder import get_instance  # noqa: PLC0415
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.debug("Recorder component not available; skipping statistics fetch")
            return []

        end = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=HISTORY_DAYS)

        def _fetch() -> list[float]:
            stats: dict = statistics_during_period(  # type: ignore[type-arg]
                self._hass,
                start_time=start,
                end_time=end,
                statistic_ids={entity_id},
                period="day",
                units={"energy": "kWh"},
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
        except Exception:
            _LOGGER.exception("Failed to fetch recorder statistics for %s", entity_id)
            return []
