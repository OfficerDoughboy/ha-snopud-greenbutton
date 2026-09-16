"""SnoPUD Green Button integration."""

from __future__ import annotations

import datetime as dt

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SCAN_INTERVAL_MIN,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
)
from .coordinator import SnoPUDCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SnoPUD from a config entry."""
    minutes = entry.options.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN)
    coordinator = SnoPUDCoordinator(
        hass,
        entry,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        update_interval=dt.timedelta(minutes=minutes),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
