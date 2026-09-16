#!/usr/bin/env python3
"""
snopud_probe.py - standalone probe for MySnoPUD Green Button export.

Goal: prove we can (1) log in, (2) find the meters, (3) pull the Green Button
ESPI XML, and (4) parse it into usable readings -- all before writing a single
line of Home Assistant code.

Your password is NEVER hardcoded and never leaves your machine. Supply it via
the SNOPUD_PASSWORD environment variable, or let the script prompt you.

    export SNOPUD_EMAIL='you@example.com'
    python3 snopud_probe.py --days 7

Requires: pip install requests
"""

import argparse
import datetime as dt
import getpass
import os
import re
import sys
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests")

BASE = "https://my.snopud.com"
UA = "snopud-probe/0.1 (personal Home Assistant project)"

# ESPI / Green Button XML namespaces
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "espi": "http://naesb.org/espi",
}

# ESPI unit-of-measure codes we care about
UOM = {72: "Wh", 38: "W", 5: "A", 29: "V"}


def log(msg):
    print(f"[probe] {msg}", flush=True)


class SnoPUDClient:
    """Minimal client for the MySnoPUD member portal."""

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})

    # ---- internals -------------------------------------------------

    @staticmethod
    def _verification_token(html):
        """Pull the ASP.NET anti-forgery token out of a page."""
        m = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html
        )
        if not m:
            # attribute order varies between views
            m = re.search(
                r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', html
            )
        return m.group(1) if m else None

    def _dump(self, name, text):
        """Save a response we didn't understand, so we can look at it."""
        path = f"debug_{name}.html"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        log(f"wrote {path} ({len(text)} bytes) for inspection")

    # ---- public ----------------------------------------------------

    def login(self):
        log("warming session / fetching anti-forgery cookie")
        r = self.s.get(f"{BASE}/", timeout=30)
        r.raise_for_status()

        token = self._verification_token(r.text)
        log(f"verification token: {'found' if token else 'NOT FOUND'}")

        payload = {
            "LoginEmail": self.email,
            "LoginPassword": self.password,
            "RememberMe": "false",
        }
        if token:
            payload["__RequestVerificationToken"] = token

        log("posting credentials to /Home/Login")
        r = self.s.post(
            f"{BASE}/Home/Login",
            data=payload,
            timeout=30,
            allow_redirects=True,
            headers={"Referer": f"{BASE}/", "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        # MySnoPUD answers login with JSON: a non-empty Data.LoginErrorMessage
        # means failure; otherwise success.
        import json
        try:
            j = json.loads(r.text)
            err = (j.get("Data") or {}).get("LoginErrorMessage") or ""
            if err.strip():
                if "two" in err.lower() or "verification code" in err.lower():
                    raise SystemExit(f"Login failed: {err} (looks like MFA -- unsupported).")
                raise SystemExit(f"Login failed: {err}")
            log("login OK (portal returned no error message)")
            return True
        except SystemExit:
            raise
        except (ValueError, json.JSONDecodeError):
            pass  # not JSON -- fall back to HTML heuristics below

        body = r.text
        signals = {
            "logout link": bool(re.search(r"/User/LogOut", body, re.I)),
            "dashboard redirect": "/Usage" in r.url or "Dashboard" in r.url,
        }
        for k, v in signals.items():
            log(f"  success signal - {k}: {v}")
        if not any(signals.values()):
            self._dump("login", body)
            raise SystemExit(
                "Login appears to have failed. Check debug_login.html."
            )
        log("login OK")
        return True

    def download_settings(self):
        """Fetch the usage-download page.

        MySnoPUD returns this as a JSON envelope ({"AjaxResults":[{"Value": "...html..."}]})
        rather than a plain HTML page, so we unwrap it first.
        """
        import json
        log("fetching /Usage/InitializeDownloadSettings")
        r = self.s.get(
            f"{BASE}/Usage/InitializeDownloadSettings",
            timeout=30,
            headers={"Referer": f"{BASE}/Usage", "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        html = r.text
        try:
            j = json.loads(r.text)
            html = "".join(a.get("Value", "") for a in j.get("AjaxResults", []))
            log("unwrapped AJAX JSON envelope")
        except Exception:
            log("response was not JSON; treating as raw HTML")

        token = self._verification_token(html)

        # Meters appear as Meters[N].Value hidden inputs.
        meters = re.findall(r'name="Meters\[\d+\]\.Value"[^>]*value="([^"]+)"', html)
        meters = [(m, f"Meter {m}") for m in meters]

        if not meters:
            self._dump("download_settings", html)
            log("no meters parsed -- see debug_download_settings.html")

        log(f"token: {'found' if token else 'NOT FOUND'}; meters: {len(meters)}")
        for v, lbl in meters:
            log(f"  meter {v!r} -> {lbl!r}")
        return token, meters

    def download_xml(self, token, meters_all, start, end,
                     interval="3", fmt="1", target=None):
        """POST the FULL export form and get Green Button XML back.

        MySnoPUD 500s on a partial form, so we replicate every field the
        rendered page submits: hidden fields, all meters, and the
        ColumnOptions/RowOptions arrays. ASP.NET renders each checkbox with a
        paired hidden "false" field; a checked box therefore posts both
        "true" and "false" (binder takes the first), an unchecked box only
        "false". We reproduce that with duplicate keys via a list of tuples.

        target: meter id to select (default: first). Others are sent but
        left unselected.
        """
        if target is None:
            target = meters_all[0]

        data = [
            ("__RequestVerificationToken", token),
            ("HasMultipleUsageTypes", "True"),
            ("FileFormat", ""),
            ("ThirdPartyPODID", ""),
            ("SelectedFormat", fmt),        # 1=Green Button
            ("SelectedServiceType", "1"),   # Electric
            ("SelectedInterval", interval), # 3=15min 5=hourly
            ("SelectedUsageType", "1"),     # kWh
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

        log(f"requesting {start:%Y-%m-%d} .. {end:%Y-%m-%d} for meter {target} "
            f"(interval={interval}, fmt={fmt}); {len(data)} form fields")
        r = self.s.post(
            f"{BASE}/Usage/Download",
            data=data,
            timeout=120,
            headers={"Referer": f"{BASE}/Usage",
                     "X-Requested-With": "XMLHttpRequest"},
        )
        r.raise_for_status()

        ct = r.headers.get("Content-Type", "")
        head = r.text.lstrip()[:300].lower()
        log(f"response Content-Type: {ct!r}; {len(r.content)} bytes")
        if not (head.startswith("<?xml") or "<feed" in head or "espi" in head
                or "<intervalblock" in head):
            self._dump("download", r.text)
            raise SystemExit(
                "Expected Green Button XML, got something else. "
                "See debug_download.html to inspect what came back."
            )
        log("got Green Button XML")
        return r.text

    def logout(self):
        try:
            self.s.get(f"{BASE}/User/LogOut", timeout=15)
            log("logged out")
        except Exception as e:
            log(f"logout failed (harmless): {e}")


def parse_green_button(xml_text):
    """ESPI XML -> list of (start_datetime_utc, duration_s, value_wh)."""
    root = ET.fromstring(xml_text)

    # Scale factor lives in ReadingType, not on the readings themselves.
    multiplier = 0
    uom_code = None
    for rt in root.iter(f"{{{NS['espi']}}}ReadingType"):
        p = rt.find(f"{{{NS['espi']}}}powerOfTenMultiplier")
        u = rt.find(f"{{{NS['espi']}}}uom")
        if p is not None and p.text:
            multiplier = int(p.text)
        if u is not None and u.text:
            uom_code = int(u.text)

    scale = 10 ** multiplier
    log(f"ReadingType: uom={uom_code} ({UOM.get(uom_code, '?')}), "
        f"powerOfTenMultiplier={multiplier} (scale x{scale})")

    readings = []
    for ir in root.iter(f"{{{NS['espi']}}}IntervalReading"):
        tp = ir.find(f"{{{NS['espi']}}}timePeriod")
        val = ir.find(f"{{{NS['espi']}}}value")
        if tp is None or val is None:
            continue
        start_el = tp.find(f"{{{NS['espi']}}}start")
        dur_el = tp.find(f"{{{NS['espi']}}}duration")
        if start_el is None or start_el.text is None:
            continue
        start = dt.datetime.fromtimestamp(
            int(start_el.text), tz=dt.timezone.utc
        )
        duration = int(dur_el.text) if dur_el is not None and dur_el.text else 0
        readings.append((start, duration, int(val.text) * scale))

    readings.sort(key=lambda r: r[0])
    return readings


def summarize(readings):
    if not readings:
        log("NO READINGS PARSED -- the XML came back but had no IntervalReading "
            "elements. Check snopud_raw.xml.")
        return

    durations = sorted({r[1] for r in readings})
    total_wh = sum(r[2] for r in readings)

    print()
    print("=" * 62)
    print(f"  readings parsed : {len(readings)}")
    print(f"  interval sizes  : {[f'{d}s ({d//60}min)' for d in durations]}")
    print(f"  first reading   : {readings[0][0]:%Y-%m-%d %H:%M} UTC")
    print(f"  last reading    : {readings[-1][0]:%Y-%m-%d %H:%M} UTC")
    print(f"  total usage     : {total_wh/1000:.2f} kWh")
    print("=" * 62)
    print()
    print("  first 8 readings:")
    for start, dur, wh in readings[:8]:
        local = start.astimezone()
        print(f"    {local:%Y-%m-%d %H:%M %Z}  {dur//60:>3}min  {wh/1000:8.3f} kWh")
    print()


def main():
    ap = argparse.ArgumentParser(description="Probe the MySnoPUD Green Button export.")
    ap.add_argument("--days", type=int, default=7, help="how many days back (default 7)")
    ap.add_argument("--email", default=os.environ.get("SNOPUD_EMAIL"))
    ap.add_argument("--meter", help="meter id (default: first one found)")
    ap.add_argument("--xml", help="skip the network, parse this saved XML file")
    args = ap.parse_args()

    # Offline mode: re-parse a previously saved file.
    if args.xml:
        log(f"parsing {args.xml} (offline)")
        with open(args.xml, encoding="utf-8") as fh:
            summarize(parse_green_button(fh.read()))
        return

    email = args.email or input("SnoPUD email: ").strip()
    password = os.environ.get("SNOPUD_PASSWORD") or getpass.getpass(
        "SnoPUD password (not echoed, stays on this machine): "
    )

    end = dt.date.today()
    start = end - dt.timedelta(days=args.days)

    client = SnoPUDClient(email, password)
    try:
        client.login()
        token, meters = client.download_settings()
        if not token:
            raise SystemExit("No CSRF token on the download page -- cannot continue.")
        if not meters and not args.meter:
            raise SystemExit("No meters found -- pass one explicitly with --meter.")

        meters_all = [m[0] for m in meters]
        target = args.meter or meters_all[0]
        xml_text = client.download_xml(token, meters_all, start, end, target=target)

        with open("snopud_raw.xml", "w", encoding="utf-8") as fh:
            fh.write(xml_text)
        log("saved snopud_raw.xml")

        summarize(parse_green_button(xml_text))
    finally:
        client.logout()


if __name__ == "__main__":
    main()
