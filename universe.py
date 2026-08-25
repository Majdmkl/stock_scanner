"""
Bygger listan av tickers som ska scannas.

Stödjer en dynamisk NASDAQ-100-lista (hämtas från Wikipedia och cachas
lokalt i NASDAQ100_CACHE_FILE) eller en egen statisk lista i config.py.
Om Wikipedia inte går att nå faller vi tillbaka på en inbyggd lista -
den kan med tiden bli något inaktuell eftersom indexet ändras några
gånger per år, men den dynamiska hämtningen är alltid förstahandsvalet.
"""
import json
import os
import time
from typing import List, Optional

import pandas as pd

from config import (
    EXTRA_TICKERS,
    LIMIT_UNIVERSE,
    NASDAQ100_CACHE_FILE,
    NASDAQ100_CACHE_TTL_HOURS,
    TICKERS as CUSTOM_TICKERS,
    UNIVERSE,
)

NASDAQ100_WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"

# Reservlista om Wikipedia-hämtningen misslyckas (t.ex. inget nätverk).
# Uppdatera gärna manuellt då och då - men i normalfallet används den
# aldrig eftersom listan hämtas live vid varje körning (med 24h cache).
FALLBACK_NASDAQ100 = sorted(set([
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALAB", "ALNY", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR",
    "CCEP", "CDNS", "CEG", "CMCSA", "COST", "CPRT", "CRWD", "CRWV", "CSCO", "CSX",
    "CTAS", "DASH", "DDOG", "DXCM", "EXC", "FANG", "FAST", "FER", "FTNT", "GEHC",
    "GILD", "GOOG", "GOOGL", "HON", "IDXX", "INTC", "INTU", "ISRG", "KDP", "KHC",
    "KLAC", "LIN", "LITE", "LRCX", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST",
    "MPWR", "MRVL", "MSFT", "MSTR", "MU", "NBIS", "NFLX", "NVDA", "NXPI", "ODFL",
    "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM", "REGN",
    "RKLB", "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "STX", "TER", "TMUS",
    "TRI", "TTWO", "TSLA", "TXN", "VRTX", "WBD", "WDAY", "WDC", "WMT", "XEL",
]))


def _load_cache() -> Optional[List[str]]:
    if not os.path.exists(NASDAQ100_CACHE_FILE):
        return None
    try:
        with open(NASDAQ100_CACHE_FILE, "r") as f:
            data = json.load(f)
        age_hours = (time.time() - data.get("fetched_at", 0)) / 3600
        if age_hours > NASDAQ100_CACHE_TTL_HOURS:
            return None
        tickers = data.get("tickers")
        return tickers or None
    except Exception:
        return None


def _save_cache(tickers: List[str]) -> None:
    try:
        with open(NASDAQ100_CACHE_FILE, "w") as f:
            json.dump({"fetched_at": time.time(), "tickers": tickers}, f)
    except Exception:
        pass  # cachning är bara en optimering, inget kritiskt


def fetch_nasdaq100_tickers() -> List[str]:
    """
    Hämtar NASDAQ-100-listan dynamiskt från Wikipedia (cachas i
    NASDAQ100_CACHE_TTL_HOURS timmar för att slippa hämta varje körning).
    Faller tillbaka på FALLBACK_NASDAQ100 om det inte går.
    """
    cached = _load_cache()
    if cached:
        return cached

    try:
        tables = pd.read_html(NASDAQ100_WIKI_URL)
        tickers = None
        for table in tables:
            match = [c for c in table.columns if "ticker" in str(c).lower()]
            if match:
                tickers = table[match[0]].astype(str).str.strip().tolist()
                break

        if not tickers:
            raise ValueError("Hittade ingen tickerkolumn i Wikipedia-tabellerna")

        # Yahoo Finance använder "-" istället för "." i tickers (t.ex. BRK.B -> BRK-B)
        tickers = sorted({t.replace(".", "-") for t in tickers if t and t.lower() != "nan"})

        if len(tickers) < 50:
            raise ValueError(f"Misstänkt kort lista ({len(tickers)} tickers), litar inte på den")

        _save_cache(tickers)
        return tickers
    except Exception as e:
        print(f"[VARNING] Kunde inte hämta NASDAQ-100-listan dynamiskt ({e}).")
        print("[VARNING] Använder inbyggd fallback-lista (kan vara något inaktuell).")
        return list(FALLBACK_NASDAQ100)


def get_universe_tickers() -> List[str]:
    """
    Returnerar den slutliga listan av tickers som ska scannas, enligt
    inställningarna i config.py (UNIVERSE, TICKERS, EXTRA_TICKERS,
    LIMIT_UNIVERSE).
    """
    if UNIVERSE == "nasdaq100":
        base = fetch_nasdaq100_tickers()
    else:
        base = list(CUSTOM_TICKERS)

    combined = list(dict.fromkeys(base + list(EXTRA_TICKERS)))  # unika, bevarar ordning

    if LIMIT_UNIVERSE:
        combined = combined[:LIMIT_UNIVERSE]

    return combined
