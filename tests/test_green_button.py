#!/usr/bin/env python3
"""Unit tests for the Green Button / ESPI parser. No HA or pytest required."""

import datetime as dt
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "snopud_gb")
)
import green_button as gb  # noqa: E402

BASE = int(dt.datetime(2026, 9, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp())
FAILS = []


def espi(rows, mult=0, uom=72):
    body = "".join(
        f"<IntervalReading><timePeriod><duration>{d}</duration>"
        f"<start>{s}</start></timePeriod><value>{v}</value></IntervalReading>"
        for s, d, v in rows
    )
    return (
        f'<?xml version="1.0"?><feed xmlns:espi="{gb.ESPI_NS}">'
        f'<ReadingType xmlns="{gb.ESPI_NS}"><uom>{uom}</uom>'
        f"<powerOfTenMultiplier>{mult}</powerOfTenMultiplier></ReadingType>"
        f'<IntervalBlock xmlns="{gb.ESPI_NS}">{body}</IntervalBlock></feed>'
    )


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        FAILS.append(name)


def main():
    print("\n-- basic parse --")
    r = gb.parse(espi([(BASE + i * 900, 900, 250) for i in range(8)]))
    check("8 readings", len(r) == 8, f"got {len(r)}")
    check("2.00 kWh total", abs(sum(x.kwh for x in r) - 2.0) < 1e-9)
    check("tz-aware UTC", r[0].start.tzinfo is dt.timezone.utc)
    check("end property", r[0].end == r[0].start + dt.timedelta(seconds=900))

    print("\n-- multiplier scaling --")
    for m, expect in [(0, 2.0), (3, 2000.0), (-3, 0.002)]:
        got = sum(
            x.kwh for x in gb.parse(espi([(BASE + i * 900, 900, 250) for i in range(8)], mult=m))
        )
        check(f"multiplier {m}", abs(got - expect) < 1e-9, f"-> {got} kWh")

    print("\n-- hourly rollup --")
    rows = [(BASE + i * 900, 900, 250) for i in range(8)] + [
        (BASE + 7200 + i * 900, 900, 250) for i in range(2)
    ]
    h = gb.to_hourly(gb.parse(espi(rows)))
    check("drops partial hour", len(h) == 2, f"got {len(h)} hours")
    check("each hour = 1.0 kWh", all(abs(x.kwh - 1.0) < 1e-9 for x in h))
    check("hours aligned to :00", all(x.start.minute == 0 for x in h))

    print("\n-- already-hourly passes through --")
    h2 = gb.to_hourly(gb.parse(espi([(BASE + i * 3600, 3600, 1000) for i in range(3)])))
    check("3 hours kept", len(h2) == 3, f"got {len(h2)}")

    print("\n-- cumulative --")
    c = gb.cumulative(gb.parse(espi([(BASE + i * 3600, 3600, 1000) for i in range(3)])))
    check("monotonic", [round(v, 6) for _, v in c] == [1.0, 2.0, 3.0])

    print("\n-- error handling --")
    for name, xml in [
        ("not xml", "<html>nope"),
        ("no readings", espi([])),
        ("wrong uom", espi([(BASE, 900, 1)], uom=5)),
    ]:
        try:
            gb.parse(xml)
            check(name, False, "no exception raised")
        except gb.GreenButtonError as e:
            check(name, True, f'-> "{str(e)[:44]}"')

    print("\n-- out-of-order input --")
    r = gb.parse(
        espi([(BASE + 3600, 3600, 100), (BASE, 3600, 200), (BASE + 7200, 3600, 300)])
    )
    check("sorted", [x.start for x in r] == sorted(x.start for x in r))

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {', '.join(FAILS)}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
