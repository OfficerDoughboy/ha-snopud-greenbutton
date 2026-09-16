# Snohomish County PUD — Green Button (Home Assistant)

Pulls electricity usage from the MySnoPUD portal's Green Button export into
Home Assistant's Energy Dashboard.

**Unofficial.** Not affiliated with or endorsed by Snohomish County PUD.

## Status

Work in progress.

| Piece | State |
|---|---|
| Green Button / ESPI parser | done, unit-tested |
| Portal client | endpoints known, **form field names unverified** |
| HA statistics push | not yet written |
| Config flow / coordinator | not yet written |

## How it works

SnoPUD's member portal offers a Green Button (ESPI XML) export of interval
usage. This integration signs in with your portal credentials, requests that
export on a schedule, and writes the readings into Home Assistant as
long-term statistics so they appear on the Energy Dashboard.

Four endpoints are involved:

| Endpoint | Purpose |
|---|---|
| `GET /` | establish session, collect anti-forgery cookie |
| `POST /Home/Login` | authenticate |
| `GET /Usage/InitializeDownloadSettings` | CSRF token + meter list |
| `POST /Usage/Download` | the ESPI XML itself |

## Before installing: run the probe

Don't install this into Home Assistant until the probe works. It confirms
login and the XML parse without touching your HA instance.

```bash
pip install requests
export SNOPUD_EMAIL='you@example.com'
python3 tools/snopud_probe.py --days 7
```

It prompts for your password (not echoed). Your password is never written to
disk and never leaves your machine.

If it fails, it writes `debug_*.html` — open it, find the real `<form>`, and
correct the field names in `custom_components/snopud_gb/const.py`. That file
is the only place they appear.

## Known limitations

- **No MFA support.** Login is email + password only.
- **Data lags 5–8 hours** behind real time. This is for historical analysis,
  not live power. For real-time, use a clamp meter (Emporia Vue, Shelly EM).
- **Credentials are stored by HA in plaintext** in `.storage`, like all HA
  config entries. Use a unique password and keep your config on an
  encrypted disk.
- **It screen-scrapes.** A portal redesign will break it.

## Running the tests

```bash
python3 tests/test_green_button.py
```

## License

MIT — see [LICENSE](LICENSE).
