"""Constants for the SnoPUD Green Button integration."""

DOMAIN = "snopud_gb"

BASE_URL = "https://my.snopud.com"

# Portal endpoints.
PATH_ROOT = "/"
PATH_LOGIN = "/Home/Login"
PATH_DOWNLOAD_SETTINGS = "/Usage/InitializeDownloadSettings"
PATH_DOWNLOAD = "/Usage/Download"
PATH_LOGOUT = "/User/LogOut"

# ---------------------------------------------------------------------------
# Form field names.
#
# These are the ONLY values inferred rather than confirmed. If login or the
# export POST fails, run tools/snopud_probe.py, open the debug_*.html it
# writes, find the real <form>, and correct the names here. Nothing else in
# the integration needs to change.
# ---------------------------------------------------------------------------
FIELD_TOKEN = "__RequestVerificationToken"
FIELD_EMAIL = "LoginEmail"
FIELD_PASSWORD = "LoginPassword"
FIELD_REMEMBER = "RememberMe"
# Download form (confirmed against the live MyMeter portal).
FIELD_FORMAT = "SelectedFormat"          # "1" = Green Button, "2" = CSV
FIELD_SERVICE_TYPE = "SelectedServiceType"  # "1" = Electric
FIELD_INTERVAL = "SelectedInterval"      # "3"=15min "5"=hourly "6"=daily "7"=billing
FIELD_USAGE_TYPE = "SelectedUsageType"   # "1" = kWh, "3" = Dollar
FIELD_HAS_MULTIPLE = "HasMultipleUsageTypes"
FIELD_START = "Start"                     # YYYY-MM-DD
FIELD_END = "End"                         # YYYY-MM-DD
# Meters are an indexed array: Meters[i].Value / Meters[i].Selected

FORMAT_GREEN_BUTTON = "1"
SERVICE_ELECTRIC = "1"
USAGE_CONSUMPTION = "1"
USAGE_DOLLAR = "3"
INTERVAL_15MIN = "3"
INTERVAL_HOURLY = "5"

DATE_FORMAT = "%Y-%m-%d"

# Config / options keys.
CONF_METERS = "meters"
CONF_SCAN_INTERVAL_MIN = "scan_interval_minutes"
CONF_BACKFILL_DAYS = "backfill_days"

DEFAULT_SCAN_INTERVAL_MIN = 1440  # once a day
MIN_SCAN_INTERVAL_MIN = 15
MAX_SCAN_INTERVAL_MIN = 1440

DEFAULT_BACKFILL_DAYS = 30
MAX_BACKFILL_DAYS = 730

# The portal lags real time; don't bother asking for the last few hours.
PORTAL_LAG_HOURS = 8

USER_AGENT = "ha-snopud-greenbutton/{version} (+https://github.com/OfficerDoughboy/ha-snopud-greenbutton)"
