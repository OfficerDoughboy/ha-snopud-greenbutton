"""Synchronous MySnoPUD portal client.

Ported from the standalone probe after every request was confirmed against
the live my.snopud.com portal. Kept synchronous (requests); Home Assistant
calls it via hass.async_add_executor_job so it never blocks the event loop.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import requests

from .const import (
    BASE_URL,
    PATH_ROOT,
    PATH_LOGIN,
    PATH_DOWNLOAD_SETTINGS,
    PATH_DOWNLOAD,
    PATH_LOGOUT,
    FIELD_TOKEN,
    FIELD_EMAIL,
    FIELD_PASSWORD,
    FORMAT_GREEN_BUTTON,
    SERVICE_ELECTRIC,
    USAGE_CONSUMPTION,
    INTERVAL_15MIN,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

VERSION = "0.1.0"


class SnoPUDAuthError(Exception):
    """Login was rejected (bad credentials or MFA)."""


class SnoPUDError(Exception):
    """Any other portal failure."""


class SnoPUDClient:
    """Talks to the MySnoPUD (MyMeter) member portal."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": USER_AGENT.format(version=VERSION)}
        )

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _token(html: str) -> str | None:
        m = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html
        )
        if not m:
            m = re.search(
                r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', html
            )
        return m.group(1) if m else None

    # -- API -------------------------------------------------------------

    def login(self) -> None:
        r = self._session.get(f"{BASE_URL}{PATH_ROOT}", timeout=30)
        r.raise_for_status()
        token = self._token(r.text)

        payload = {
            FIELD_EMAIL: self._email,
            FIELD_PASSWORD: self._password,
            "RememberMe": "false",
        }
        if token:
            payload[FIELD_TOKEN] = token

        r = self._session.post(
            f"{BASE_URL}{PATH_LOGIN}",
            data=payload,
            timeout=30,
            headers={"Referer": f"{BASE_URL}/", "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        try:
            j = json.loads(r.text)
            err = (j.get("Data") or {}).get("LoginErrorMessage") or ""
        except (ValueError, json.JSONDecodeError):
            err = ""
            if not re.search(r"/User/LogOut", r.text, re.I) and "/Usage" not in r.url:
                err = "Unexpected login response"

        if err.strip():
            raise SnoPUDAuthError(err.strip())
        _LOGGER.debug("MySnoPUD login OK")

    def get_settings(self) -> tuple[str, list[str]]:
        """Return (csrf_token, [meter_id, ...])."""
        r = self._session.get(
            f"{BASE_URL}{PATH_DOWNLOAD_SETTINGS}",
            timeout=30,
            headers={"Referer": f"{BASE_URL}/Usage", "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        html = r.text
        try:
            j = json.loads(r.text)
            html = "".join(a.get("Value", "") for a in j.get("AjaxResults", []))
        except (ValueError, json.JSONDecodeError):
            pass

        token = self._token(html)
        meters = re.findall(
            r'name="Meters\[\d+\]\.Value"[^>]*value="([^"]+)"', html
        )
        if not token:
            raise SnoPUDError("No CSRF token on download-settings page")
        if not meters:
            raise SnoPUDError("No meters found on download-settings page")
        return token, meters

    def download_green_button(
        self,
        token: str,
        meters_all: list[str],
        target: str,
        start: date,
        end: date,
        interval: str = INTERVAL_15MIN,
    ) -> str:
        """POST the full export form; return Green Button ESPI XML for `target`."""
        data: list[tuple[str, str]] = [
            (FIELD_TOKEN, token),
            ("HasMultipleUsageTypes", "True"),
            ("FileFormat", ""),
            ("ThirdPartyPODID", ""),
            ("SelectedFormat", FORMAT_GREEN_BUTTON),
            ("SelectedServiceType", SERVICE_ELECTRIC),
            ("SelectedInterval", interval),
            ("SelectedUsageType", USAGE_CONSUMPTION),
        ]
        for i, mid in enumerate(meters_all):
            data.append((f"Meters[{i}].Value", mid))
            if mid == target:
                data.append((f"Meters[{i}].Selected", "true"))
            data.append((f"Meters[{i}].Selected", "false"))
        data += [("Start", start.strftime("%Y-%m-%d")),
                 ("End", end.strftime("%Y-%m-%d"))]

        cols = ["ReadDate", "AccountNumber", "Name", "Meter", "Location",
                "Address", "VeeEstimatedByUtility", "Consumption", "Dollar"]
        for i, c in enumerate(cols):
            data += [(f"ColumnOptions[{i}].Value", c),
                     (f"ColumnOptions[{i}].Name", c),
                     (f"ColumnOptions[{i}].Checked", "true"),
                     (f"ColumnOptions[{i}].Checked", "false")]
        rows = [("ReadDate", "Read Date"), ("Consumption", "kWh"), ("Dollar", "$")]
        for i, (v, n) in enumerate(rows):
            data += [(f"RowOptions[{i}].Value", v),
                     (f"RowOptions[{i}].Name", n),
                     (f"RowOptions[{i}].Desc", "false")]

        r = self._session.post(
            f"{BASE_URL}{PATH_DOWNLOAD}",
            data=data,
            timeout=120,
            headers={"Referer": f"{BASE_URL}/Usage", "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        head = r.text.lstrip()[:300].lower()
        if not (head.startswith("<?xml") or "<feed" in head or "espi" in head
                or "<intervalblock" in head):
            raise SnoPUDError(
                f"Expected Green Button XML for meter {target}, got "
                f"{r.headers.get('Content-Type', '?')} ({len(r.content)} bytes)"
            )
        return r.text

    def logout(self) -> None:
        try:
            self._session.get(f"{BASE_URL}{PATH_LOGOUT}", timeout=15)
        except requests.RequestException:
            pass

    def close(self) -> None:
        self._session.close()
