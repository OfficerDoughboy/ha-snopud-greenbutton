# Snohomish County PUD — Green Button (Home Assistant)

Pulls electricity usage from the **MySnoPUD** member portal into Home
Assistant's Energy Dashboard, using the portal's Green Button (ESPI XML)
export.

**Unofficial.** Not affiliated with or endorsed by Snohomish County PUD.

Built by reverse-engineering the portal, so it may help anyone whose utility
runs on the same **MyMeter** platform (by Accelerated Innovations) — the
approach transfers even if the exact field values differ.

## Status

**Working.** Every request below was confirmed against the live
`my.snopud.com` portal, and the integration is running on a real
Home Assistant OS instance (2026.9) feeding the Energy Dashboard.

| Piece | State |
|---|---|
| Green Button / ESPI parser | done, unit-tested (16 cases) |
| Portal client (login, meter list, download) | confirmed against live portal |
| Combine all meters → hourly statistic | verified on real data |
| HA long-term statistics (Energy Dashboard) | working |
| Config flow + options | working |

## What it does

Once a day (configurable), it logs into MySnoPUD, downloads the Green Button
export for **every meter on the account**, sums them per hour, and writes the
result into Home Assistant as a single long-term statistic
(`snopud_gb:total_energy`) that appears on the Energy Dashboard.

Default behaviour: all meters combined into one total, hourly, polled once a
day. Change the polling interval and history depth in the integration's
**Options**.

## How it works

MySnoPUD runs on the MyMeter platform. The relevant endpoints (all on
`https://my.snopud.com`):

| Endpoint | Purpose |
|---|---|
| `GET /` | establish session, collect anti-forgery cookie |
| `POST /Home/Login` | authenticate (fields `LoginEmail` / `LoginPassword`) |
| `GET /Usage/InitializeDownloadSettings` | returns a JSON envelope whose `AjaxResults[].Value` holds the settings HTML — CSRF token + meter list |
| `POST /Usage/Download` | the export; `SelectedFormat=1` for Green Button, meters as an indexed `Meters[i]` array, dates as `YYYY-MM-DD` |

Two gotchas that cost the most time, documented here so the next person
doesn't repeat them:

1. The download-settings response is **JSON with the form HTML nested inside**
   (escaped), not raw HTML — you have to unwrap `AjaxResults[].Value` first.
2. `POST /Usage/Download` returns HTTP 500 unless you submit the **complete**
   form — every hidden field, all meters, and the `ColumnOptions` /
   `RowOptions` arrays (ASP.NET checkbox pairs and all). A partial form
   dereferences null server-side.

The ESPI parser applies the `powerOfTenMultiplier` from `ReadingType` (getting
this wrong is a silent 1000× error) and rolls 15-minute intervals up to whole
hours for the Energy Dashboard.

## Install

No HACS required — it's a plain custom component.

1. Copy `custom_components/snopud_gb/` into your HA `config/custom_components/`.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration →** "Snohomish County PUD
   (Green Button)" → enter your MySnoPUD email and password.
4. **Settings → Dashboards → Energy → Add consumption →** "SnoPUD Total
   Energy".

## Try it first (optional but recommended)

`tools/snopud_probe.py` runs the whole login → download → parse chain from the
command line, without touching Home Assistant. Good for confirming your
account works (or adapting field values for a different MyMeter utility):

```bash
pip install requests
export SNOPUD_EMAIL='you@example.com'
python3 tools/snopud_probe.py --days 7
```

It prompts for your password (not echoed). Your password is never written to
disk and never leaves your machine. On failure it saves `debug_*.html` so you
can inspect the real form.

## Known limitations

- **No MFA support.** Login is email + password only.
- **Data lags 5–8 hours** behind real time — this is for historical analysis,
  not live power. For real-time, add a clamp meter (Emporia Vue, Shelly EM).
- **Credentials are stored by HA in plaintext** in `.storage`, like all HA
  config entries. Use a unique password and keep your config encrypted.
- **It screen-scrapes.** A portal redesign can break it; fixes usually mean
  updating field names in `const.py`.

## Running the tests

```bash
python3 tests/test_green_button.py
```

## License

MIT — see [LICENSE](LICENSE).
