"""Consumption forecaster using Home Assistant Recorder statistics."""

from __future__ import annotations

import logging
import math
import statistics
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HISTORY_DAYS = 14
MIN_DAYS_FOR_MEDIAN = 3
CACHE_TTL_SECONDS = 3600


def _daily_totals_from_statistics(
    rows: list[dict[str, Any]], start: datetime, end: datetime,
) -> dict[date, float]:
    """Compute complete local days from Recorder's hourly cumulative sums.

    A row's sum is the cumulative value at the END of its hour. Include the
    hour before start as an anchor. Missing/invalid hours invalidate that day;
    do not spread energy across gaps or mistake daily state resets for usage.
    Local midnight boundaries allow 23/25-hour DST days.
    """
    sums: dict[float, float] = {}
    for row in rows:
        timestamp, value = row.get("start"), row.get("sum")
        if timestamp is None or value is None:
            continue
        timestamp, value = float(timestamp), float(value)
        if math.isfinite(timestamp) and math.isfinite(value):
            sums[timestamp] = value

    totals: dict[date, float] = {}
    day = start
    while day < end:
        next_day = day + timedelta(days=1)
        first, stop = day.timestamp(), next_day.timestamp()
        deltas = []
        for timestamp in range(int(first), int(stop), 3600):
            current, previous = sums.get(timestamp), sums.get(timestamp - 3600)
            if current is None or previous is None or current < previous - 1e-6:
                break
            deltas.append(max(current - previous, 0.0))
        else:
            totals[day.date()] = round(sum(deltas), 3)
        day = next_day
    return totals


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
            else None
        )

        # Each sensor may have different missing days. Align by date, not index;
        # an unknown smart-load day must not be silently treated as zero.
        days = sorted(total_series)
        if smart_series is not None:
            days = [day for day in days if day in smart_series]
        baseline = _compute_baseline_series(
            [total_series[day] for day in days],
            [smart_series[day] for day in days] if smart_series is not None else [],
        )
        result = _forecast_from_series(baseline)

        self._cache[cache_key] = (result, now + timedelta(seconds=CACHE_TTL_SECONDS))
        return result

    async def _fetch_daily_totals(self, entity_id: str) -> dict[date, float]:
        """Return complete local-day consumption totals (kWh), keyed by date.

        Energy sensors with state_class total_increasing provide cumulative
        ``sum`` statistics, not ``max``. Differences between adjacent hourly
        sums give consumption, including across daily sensor state resets.

        Returns an empty mapping when the Recorder is unavailable or has no
        data for the entity.
        """

        try:
            from homeassistant.components.recorder import get_instance  # noqa: PLC0415
            from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.debug("Recorder component not available; skipping statistics fetch")
            return {}

        local_tz = ZoneInfo(self._hass.config.time_zone)
        end = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=HISTORY_DAYS)

        def _fetch() -> dict[date, float]:
            stats: dict = statistics_during_period(  # type: ignore[type-arg]
                self._hass,
                start_time=start.astimezone(UTC) - timedelta(hours=1),
                end_time=end.astimezone(UTC),
                statistic_ids={entity_id},
                period="hour",
                units={"energy": "kWh"},
                types={"sum"},
            )
            rows = stats.get(entity_id, [])
            return _daily_totals_from_statistics(rows, start, end)

        try:
            instance = get_instance(self._hass)
            return await instance.async_add_executor_job(_fetch)
        except Exception:
            _LOGGER.exception("Failed to fetch recorder statistics for %s", entity_id)
            return {}
