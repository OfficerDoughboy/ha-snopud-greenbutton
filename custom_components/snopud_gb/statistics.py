"""Push combined hourly usage into Home Assistant long-term statistics.

We register ONE external statistic (all meters summed) so it appears on the
Energy Dashboard as a single consumption source.
"""

from __future__ import annotations

import datetime as dt
import logging

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# External statistic id: "<source>:<name>" with a colon (not a dot).
STATISTIC_ID = f"{DOMAIN}:total_energy"


async def async_import_hourly(
    hass: HomeAssistant,
    hourly_kwh: dict[dt.datetime, float],
    name: str = "SnoPUD Total Energy",
) -> None:
    """Import combined hourly kWh as a cumulative external statistic.

    hourly_kwh: {hour_start (tz-aware, hour-aligned) -> kWh consumed that hour}.
    """
    if not hourly_kwh:
        _LOGGER.debug("No hourly data to import")
        return

    ordered = sorted(hourly_kwh.items())

    # Continue the running total from whatever HA already stored.
    last = await get_last_statistics_wrapper(hass)
    running = last[0] if last else 0.0
    last_start = last[1] if last else None

    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=STATISTIC_ID,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )

    stats: list[StatisticData] = []
    for hour, kwh in ordered:
        # Skip hours we've already recorded to avoid double-counting.
        if last_start is not None and hour <= last_start:
            continue
        running += kwh
        stats.append(StatisticData(start=hour, sum=running, state=kwh))

    if not stats:
        _LOGGER.debug("All hourly data already imported")
        return

    _LOGGER.info(
        "Importing %d hourly statistics into %s (through %s)",
        len(stats), STATISTIC_ID, stats[-1]["start"],
    )
    async_add_external_statistics(hass, metadata, stats)


async def get_last_statistics_wrapper(
    hass: HomeAssistant,
) -> tuple[float, dt.datetime] | None:
    """Return (last_sum, last_start) for our statistic, or None."""
    result = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, STATISTIC_ID, True, {"sum"}
    )
    rows = result.get(STATISTIC_ID)
    if not rows:
        return None
    row = rows[0]
    last_sum = row.get("sum")
    start = row.get("start")
    if last_sum is None or start is None:
        return None
    # `start` may be a POSIX timestamp (float) depending on HA version.
    if isinstance(start, (int, float)):
        start = dt.datetime.fromtimestamp(start, tz=dt.timezone.utc)
    return float(last_sum), start
