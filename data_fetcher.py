"""
Datahämtning via yfinance.

Ansvarar bara för att hämta och normalisera OHLCV-data samt slå upp
kommande earnings-datum/bolagsnamn. Ingen analyslogik ligger här.

fetch_batch_ohlcv() är huvudvägen in när man scannar många tickers (t.ex.
hela NASDAQ-100): den hämtar flera tickers i samma yfinance-anrop
(grupperat i chunks) istället för ett anrop per ticker, vilket är
väsentligt snabbare och skonsammare mot Yahoo Finance API:t.
"""
import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from config import BATCH_CHUNK_SIZE, BATCH_SLEEP_SECONDS, TIMEFRAMES


def fetch_ohlcv(ticker: str, timeframe: str) -> pd.DataFrame:
    """
    Hämtar OHLCV-data för en ticker och given tidsram ("1h", "2h", "4h", "1d").
    Returnerar en DataFrame med kolumnerna Open/High/Low/Close/Volume,
    indexerad på tid. Tom DataFrame returneras om inget data finns.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Okänd tidsram: {timeframe}")

    cfg = TIMEFRAMES[timeframe]

    df = yf.download(
        ticker,
        interval=cfg["interval"],
        period=cfg["period"],
        auto_adjust=False,
        progress=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance returnerar ibland MultiIndex-kolumner (t.ex. vid batch-hämtning)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.title)
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return pd.DataFrame()

    df = df[required].dropna()

    if cfg["resample"]:
        df = _resample(df, cfg["resample"])

    return df


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Slår ihop t.ex. två eller fyra 1h-candles till en 2h/4h-candle."""
    agg = {
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }
    out = df.resample(rule, label="right", closed="right").agg(agg)
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out


def _chunks(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_batch_ohlcv(tickers: List[str], timeframe: str) -> Dict[str, pd.DataFrame]:
    """
    Hämtar OHLCV-data för flera tickers samtidigt för en given tidsram.
    Hämtningen delas upp i chunks om BATCH_CHUNK_SIZE tickers, med en
    kort paus (BATCH_SLEEP_SECONDS) mellan varje chunk för att undvika
    rate limiting från Yahoo Finance.

    Returnerar en dict {ticker: DataFrame}. Tickers utan data (t.ex. fel
    tickersymbol eller tillfälligt saknad data) utelämnas helt enkelt.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Okänd tidsram: {timeframe}")

    cfg = TIMEFRAMES[timeframe]
    result: Dict[str, pd.DataFrame] = {}

    chunk_list = list(_chunks(tickers, BATCH_CHUNK_SIZE))

    for chunk_idx, chunk in enumerate(chunk_list):
        try:
            raw = yf.download(
                tickers=chunk,
                interval=cfg["interval"],
                period=cfg["period"],
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            print(f"[VARNING] Batch-hämtning misslyckades för {chunk}: {e}")
            continue

        if raw is None or raw.empty:
            continue

        single_ticker = len(chunk) == 1

        for ticker in chunk:
            try:
                if single_ticker:
                    df = raw
                else:
                    if not isinstance(raw.columns, pd.MultiIndex) or ticker not in raw.columns.get_level_values(0):
                        continue
                    df = raw[ticker]

                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)

                df = df.rename(columns=str.title)
                required = ["Open", "High", "Low", "Close", "Volume"]
                if any(c not in df.columns for c in required):
                    continue

                df = df[required].dropna()
                if df.empty:
                    continue

                if cfg["resample"]:
                    df = _resample(df, cfg["resample"])

                if not df.empty:
                    result[ticker] = df
            except Exception:
                continue  # en trasig ticker ska inte stoppa resten av batchen

        if chunk_idx < len(chunk_list) - 1 and BATCH_SLEEP_SECONDS:
            time.sleep(BATCH_SLEEP_SECONDS)

    return result


def get_company_name(ticker: str) -> str:
    """Bästa möjliga bolagsnamn för visning i grafen; faller tillbaka på tickern."""
    try:
        info = yf.Ticker(ticker).get_info()
        name = info.get("shortName") or info.get("longName")
        return name if name else ticker
    except Exception:
        return ticker


def get_next_earnings_date(ticker: str) -> str | None:
    """
    Returnerar nästa kommande earnings-datum som en sträng (YYYY-MM-DD),
    eller None om det inte går att hitta.
    """
    try:
        t = yf.Ticker(ticker)
        cal = t.get_earnings_dates(limit=8)
        if cal is None or cal.empty:
            return None

        now = pd.Timestamp.now(tz=cal.index.tz) if cal.index.tz is not None else pd.Timestamp.now()
        future = cal[cal.index >= now]
        if future.empty:
            return None

        next_date = future.index.min()
        return next_date.strftime("%Y-%m-%d")
    except Exception:
        return None
