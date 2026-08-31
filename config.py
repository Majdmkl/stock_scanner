"""
Konfiguration för aktie-scannern.

Miljövariabler (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) laddas från en
.env-fil om python-dotenv är installerat och en .env-fil finns i mappen.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv är valfritt - man kan sätta miljövariabler manuellt istället
    pass

# ---------------------------------------------------------------------------
# Vilka tickers som ska bevakas
# ---------------------------------------------------------------------------
# "nasdaq100" = hämta hela NASDAQ-100-listan dynamiskt (se universe.py).
# "custom"    = använd bara listan i TICKERS nedan.
UNIVERSE = "nasdaq100"

# Används bara när UNIVERSE == "custom"
TICKERS = ["NVDA", "CRWD", "DAL", "NET", "MU"]

# Läggs alltid till, oavsett UNIVERSE (t.ex. för att bevaka enskilda
# aktier utanför NASDAQ-100, som DAL i exemplen ovan).
EXTRA_TICKERS = ["DAL"]

# Sätt till t.ex. 15 för att bara scanna de 15 första tickrarna - bra för
# snabba testkörningar. None = ingen begränsning (scanna alla).
LIMIT_UNIVERSE = None

# Hur länge (timmar) den hämtade NASDAQ-100-listan cachas lokalt innan
# den hämtas på nytt från Wikipedia.
NASDAQ100_CACHE_FILE = "nasdaq100_cache.json"
NASDAQ100_CACHE_TTL_HOURS = 24

# ---------------------------------------------------------------------------
# Tidsramar. yfinance har ingen nativ 2h/4h-upplösning, så vi hämtar 60m-data
# och "resamplar" (slår ihop candles) till 2h/4h med pandas.
# ---------------------------------------------------------------------------
TIMEFRAMES = {
    "1h": {"interval": "60m", "period": "1mo", "resample": None},
    "2h": {"interval": "60m", "period": "1mo", "resample": "2h"},
    "4h": {"interval": "60m", "period": "3mo", "resample": "4h"},
    "1d": {"interval": "1d", "period": "1y", "resample": None},
}

# ---------------------------------------------------------------------------
# Batch-hämtning: när vi scannar många tickers hämtas de i grupper (chunks)
# istället för en och en, för att gå snabbare och vara snällare mot Yahoo
# Finance API:t (undvika rate limiting).
# ---------------------------------------------------------------------------
BATCH_CHUNK_SIZE = 15
BATCH_SLEEP_SECONDS = 1.5

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Analysparametrar - justera fritt för att göra scannern striktare/löslligare
# ---------------------------------------------------------------------------

# Hur många candles på varje sida som krävs för att en high/low ska räknas
# som en "swing point" (pivot).
SWING_LOOKBACK = 5

# Hur stor den impulsiva rörelsen upp från en konsolidering minst måste vara
# (i procent) för att konsolideringen ska räknas som en demand zone.
ZONE_MIN_IMPULSE_PCT = 0.03

# Minsta gap-storlek (i procent av priset) för att en Fair Value Gap ska
# räknas som giltig - filtrerar bort brus.
FVG_MIN_GAP_PCT = 0.001

# Hur många candles bakåt i tiden som analyseras för zoner/trendlinjer/FVG.
MAX_ZONE_AGE_BARS = 200

# Hur nära (i ATR-multiplar) nuvarande pris måste vara en nivå för att den
# ska räknas som en aktuell/relevant setup.
PROXIMITY_ATR_MULT = 1.5

# ---------------------------------------------------------------------------
# Notis-cooldown / deduplicering
# ---------------------------------------------------------------------------

# Hur länge (timmar) en ticker+setup-typ "tystas" efter att en notis skickats,
# innan en ny notis för samma kombination får skickas igen.
NOTIFICATION_COOLDOWN_HOURS = 20

# Filen som håller koll på senaste notis per ticker+setup-typ, skriven av
# notification_state.py. Radera filen för att nollställa alla cooldowns.
NOTIFICATION_STATE_FILE = "notification_state.json"

# Hur stor relativ prisskillnad (0.02 = 2 %) som krävs på level_low eller
# level_high för att en ny setup-nivå ska räknas som "signifikant annorlunda"
# och trigga en notis trots att cooldown-fönstret inte gått ut.
NOTIFICATION_LEVEL_TOLERANCE_PCT = 0.02

# ---------------------------------------------------------------------------
# Övrigt
# ---------------------------------------------------------------------------
CHART_DIR = "charts"
