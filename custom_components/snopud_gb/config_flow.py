"""Config and options flow for SnoPUD Green Button."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback

from .const import (
    CONF_BACKFILL_DAYS,
    CONF_SCAN_INTERVAL_MIN,
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MAX_BACKFILL_DAYS,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .snopud_client import SnoPUDAuthError, SnoPUDClient, SnoPUDError


async def _validate(hass, email: str, password: str) -> str | None:
    """Return an error key, or None if credentials work."""
    client = SnoPUDClient(email, password)

    def _check() -> None:
        try:
            client.login()
            client.get_settings()
        finally:
            client.logout()
            client.close()

    try:
        await hass.async_add_executor_job(_check)
    except SnoPUDAuthError:
        return "invalid_auth"
    except SnoPUDError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        return "unknown"
    return None


class SnoPUDConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
            self._abort_if_unique_id_configured()

            error = await _validate(
                self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"SnoPUD ({user_input[CONF_EMAIL]})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SnoPUDOptionsFlow(entry)


class SnoPUDOptionsFlow(OptionsFlow):
    """Adjust polling and backfill."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self._entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL_MIN,
                    default=opts.get(CONF_SCAN_INTERVAL_MIN, DEFAULT_SCAN_INTERVAL_MIN),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL_MIN, max=MAX_SCAN_INTERVAL_MIN)),
                vol.Required(
                    CONF_BACKFILL_DAYS,
                    default=opts.get(CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS),
                ): vol.All(int, vol.Range(min=1, max=MAX_BACKFILL_DAYS)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
