"""Parse Green Button / ESPI XML into interval readings.

Pure functions, no Home Assistant imports -- so this module is testable
standalone and reusable by the command-line probe.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ESPI_NS = "http://naesb.org/espi"

# ESPI unit-of-measure codes.
UOM_WH = 72
UOM_W = 38

UOM_NAMES = {72: "Wh", 38: "W", 5: "A", 29: "V"}


class GreenButtonError(Exception):
    """Raised when the XML is not usable."""


@dataclass(frozen=True, slots=True)
class Reading:
    """One metering interval."""

    start: dt.datetime  # timezone-aware, UTC
    duration: int  # seconds
    watt_hours: float

    @property
    def end(self) -> dt.datetime:
        return self.start + dt.timedelta(seconds=self.duration)

    @property
    def kwh(self) -> float:
        return self.watt_hours / 1000.0


def _tag(name: str) -> str:
    return f"{{{ESPI_NS}}}{name}"


def parse_reading_type(root: ET.Element) -> tuple[int, int]:
    """Return (uom_code, power_of_ten_multiplier).

    The scale factor lives in ReadingType, not on individual readings. Missing
    it -- or applying it twice -- is the classic way to end up 1000x off.
    """
    uom = UOM_WH
    multiplier = 0
    for rt in root.iter(_tag("ReadingType")):
        u = rt.find(_tag("uom"))
        p = rt.find(_tag("powerOfTenMultiplier"))
        if u is not None and u.text:
            uom = int(u.text)
        if p is not None and p.text:
            multiplier = int(p.text)
    return uom, multiplier


def parse(xml_text: str) -> list[Reading]:
    """Parse an ESPI feed into chronologically sorted readings."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise GreenButtonError(f"not valid XML: {err}") from err

    uom, multiplier = parse_reading_type(root)
    if uom not in (UOM_WH, UOM_W):
        raise GreenButtonError(
            f"unexpected unit of measure {uom} "
            f"({UOM_NAMES.get(uom, 'unknown')}); expected Wh"
        )
    scale = 10.0**multiplier

    readings: list[Reading] = []
    for ir in root.iter(_tag("IntervalReading")):
        period = ir.find(_tag("timePeriod"))
        value = ir.find(_tag("value"))
        if period is None or value is None or not value.text:
            continue

        start_el = period.find(_tag("start"))
        dur_el = period.find(_tag("duration"))
        if start_el is None or not start_el.text:
            continue

        readings.append(
            Reading(
                start=dt.datetime.fromtimestamp(
                    int(start_el.text), tz=dt.timezone.utc
                ),
                duration=int(dur_el.text) if dur_el is not None and dur_el.text else 0,
                watt_hours=int(value.text) * scale,
            )
        )

    if not readings:
        raise GreenButtonError("XML contained no IntervalReading elements")

    readings.sort(key=lambda r: r.start)
    return readings


def to_hourly(readings: list[Reading]) -> list[Reading]:
    """Collapse sub-hourly readings into whole hours.

    Home Assistant's long-term statistics are hourly. Only complete hours are
    emitted -- a partial trailing hour would show up as an artificial dip.
    """
    buckets: dict[dt.datetime, list[Reading]] = {}
    for r in readings:
        buckets.setdefault(r.start.replace(minute=0, second=0, microsecond=0), []).append(r)

    hourly: list[Reading] = []
    for hour, group in sorted(buckets.items()):
        covered = sum(g.duration for g in group)
        if covered < 3600:
            continue  # incomplete hour
        hourly.append(
            Reading(
                start=hour,
                duration=3600,
                watt_hours=sum(g.watt_hours for g in group),
            )
        )
    return hourly


def cumulative(readings: list[Reading]) -> list[tuple[dt.datetime, float]]:
    """Running total in kWh -- the shape HA statistics wants for `sum`."""
    total = 0.0
    out: list[tuple[dt.datetime, float]] = []
    for r in readings:
        total += r.kwh
        out.append((r.start, total))
    return out
