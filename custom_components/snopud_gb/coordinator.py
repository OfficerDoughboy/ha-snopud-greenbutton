"""Daily coordinator: pull all meters, combine hourly, import statistics."""

from __future__ import annotations

import datetime as dt
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import green_button
from .const import (
    CONF_BACKFILL_DAYS,
    DEFAULT_BACKFILL_DAYS,
    DOMAIN,
    PORTAL_LAG_HOURS,
)
from .snopud_client import SnoPUDAuthError, SnoPUDClient, SnoPUDError
from .statistics import async_import_hourly

_LOGGER = logging.getLogger(__name__)


class SnoPUDCoordinator(DataUpdateCoordinator[dict]):
    """Fetches Green Button data for every meter and combines it."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        email: str,
        password: str,
        update_interval: dt.timedelta,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=update_interval
        )
        self._entry = entry
        self._email = email
        self._password = password

    async def _async_update_data(self) -> dict:
        backfill = self._entry.options.get(CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS)
        try:
            combined = await self.hass.async_add_executor_job(
                self._fetch_and_combine, backfill
            )
        except SnoPUDAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except SnoPUDError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected error: {err}") from err

        await async_import_hourly(self.hass, combined)

        total = sum(combined.values())
        return {
            "hours": len(combined),
            "total_kwh": round(total, 3),
            "last_hour": max(combined) if combined else None,
        }

    # -- runs in executor (blocking requests) ----------------------------

    def _fetch_and_combine(self, backfill_days: int) -> dict[dt.datetime, float]:
        """Return {hour_start_utc -> combined kWh across all meters}."""
        end = dt.date.today()
        start = end - dt.timedelta(days=backfill_days)

        client = SnoPUDClient(self._email, self._password)
        combined: dict[dt.datetime, float] = {}
        try:
            client.login()
            token, meters = client.get_settings()
            _LOGGER.debug("Fetching %d meters", len(meters))

            for meter in meters:
                xml = client.download_green_button(
                    token, meters, meter, start, end
                )
                readings = green_button.parse(xml)
                hourly = green_button.to_hourly(readings)
                for r in hourly:
                    combined[r.start] = combined.get(r.start, 0.0) + r.kwh
        finally:
            client.logout()
            client.close()

        # Drop the most-recent, still-settling hours (portal lag).
        cutoff = dt.datetime.now(tz=dt.timezone.utc) - dt.timedelta(
            hours=PORTAL_LAG_HOURS
        )
        return {h: v for h, v in combined.items() if h < cutoff}
