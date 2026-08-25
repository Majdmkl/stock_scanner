"""
Orkestrering: bygger tickerlistan (NASDAQ-100 eller egen lista), hämtar
OHLCV-data batchvis per tidsram, kör analys per ticker över alla
tidsramar, väljer den tydligaste setupen, ritar graf och skickar till
Telegram.

Kör manuellt:
    python main.py

Kör kontinuerligt (enkel polling-loop):
    python main.py --loop --interval-minutes 60

Se SETUP_GUIDE.md för hur du sätter upp venv, paket och Telegram-bot,
samt hur du schemalägger körningen (cron / Task Scheduler) istället för
att använda --loop.
"""
import argparse
import time
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from analysis import Setup, evaluate_setups
from charting import KIND_LABELS, plot_setup
from config import TIMEFRAMES
from data_fetcher import fetch_batch_ohlcv, get_company_name, get_next_earnings_date
from notification_state import load_state, record_notification, save_state, should_notify
from telegram_bot import send_photo, send_test_message
from universe import get_universe_tickers


def build_bullets(ticker: str, timeframe: str, setup: Setup, current_price: float) -> list:
    """
    Genererar de tre korta textrader som visas både i grafens textruta
    och i Telegram-bildtexten, så de alltid stämmer överens.
    """
    earnings = get_next_earnings_date(ticker)
    earnings_line = f"Nästa earnings: {earnings}" if earnings else "Nästa earnings: okänt"

    return [
        f"${ticker} pris ${current_price:.2f} ligger {setup.distance_pct * 100:.2f}% "
        f"från {setup.description}",
        "Håll koll på hur köpare/säljare reagerar på denna nivå",
        earnings_line,
    ]


def build_caption(ticker: str, timeframe: str, setup: Setup, bullets: list) -> str:
    kind_label = KIND_LABELS.get(setup.kind, setup.kind)
    header = f"*${ticker}* | {timeframe} | {kind_label}"
    body = "\n".join(f"• {b}" for b in bullets)
    return f"{header}\n{body}"


def analyze_ticker(ticker: str, data_by_timeframe: Dict[str, Dict[str, pd.DataFrame]]) -> Optional[dict]:
    """
    Väljer, utifrån redan hämtad data, den tidsram där tickerns pris
    ligger närmast en identifierad setup. Returnerar None om ingen
    relevant setup hittades på någon tidsram.
    """
    best_setup = None
    best_timeframe = None
    best_df = None

    for timeframe in TIMEFRAMES:
        df = data_by_timeframe.get(timeframe, {}).get(ticker)
        if df is None or df.empty:
            continue

        setup = evaluate_setups(df)
        if setup is None:
            continue

        if best_setup is None or setup.distance_pct < best_setup.distance_pct:
            best_setup = setup
            best_timeframe = timeframe
            best_df = df

    if best_setup is None or best_df is None:
        return None

    return {"timeframe": best_timeframe, "setup": best_setup, "df": best_df}


def process_ticker(ticker: str, result: dict, state: dict) -> bool:
    """
    Ritar graf och skickar Telegram-notis för en ticker om cooldown-reglerna
    tillåter det. Returnerar True om notisen skickades, False om den skippades.
    """
    timeframe = result["timeframe"]
    setup = result["setup"]
    df = result["df"]
    current_price = float(df["Close"].iloc[-1])

    print(
        f"[{ticker}] Bästa setup: {timeframe} - {setup.kind} "
        f"({setup.distance_pct * 100:.2f}% från pris {current_price:.2f})"
    )

    if not should_notify(state, ticker, setup):
        print(
            f"[{ticker}] Skippas — cooldown aktiv, samma {setup.kind}-nivå "
            f"(${setup.level_low:.2f}–${setup.level_high:.2f})."
        )
        return False

    bullets = build_bullets(ticker, timeframe, setup, current_price)
    company_name = get_company_name(ticker)
    chart_path = plot_setup(df, ticker, timeframe, setup, bullets=bullets, company_name=company_name)
    caption = build_caption(ticker, timeframe, setup, bullets)

    send_photo(chart_path, caption)
    record_notification(state, ticker, setup)
    return True


def run_once() -> None:
    print(f"--- Scan startad {datetime.now().isoformat(timespec='seconds')} ---")

    tickers = get_universe_tickers()
    preview = ", ".join(tickers[:12]) + ("..." if len(tickers) > 12 else "")
    print(f"Bevakar {len(tickers)} tickers: {preview}")

    notification_state = load_state()

    # Hämta all data batchvis, en gång per tidsram, istället för ett anrop
    # per ticker och tidsram - mycket snabbare för stora tickerlistor.
    data_by_timeframe: Dict[str, Dict[str, pd.DataFrame]] = {}
    for timeframe in TIMEFRAMES:
        print(f"Hämtar {timeframe}-data för {len(tickers)} tickers...")
        data_by_timeframe[timeframe] = fetch_batch_ohlcv(tickers, timeframe)
        found = len(data_by_timeframe[timeframe])
        print(f"  -> data hittad för {found}/{len(tickers)} tickers")

    hits = 0
    sent = 0
    skipped = 0
    for ticker in tickers:
        try:
            result = analyze_ticker(ticker, data_by_timeframe)
            if result is None:
                print(f"[{ticker}] Ingen tydlig setup hittades på någon tidsram.")
                continue
            hits += 1
            if process_ticker(ticker, result, notification_state):
                sent += 1
            else:
                skipped += 1
        except Exception as e:  # ett fel på en ticker ska inte stoppa hela scannen
            print(f"[{ticker}] Fel under analys: {e}")

    save_state(notification_state)
    print(
        f"--- Scan klar: {hits} setup(ar) hittade, {sent} notis(er) skickade, "
        f"{skipped} skippade (cooldown) ---"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aktiescanner: demand zones, trendlinjer, FVG -> Telegram")
    parser.add_argument("--loop", action="store_true", help="Kör kontinuerligt istället för en gång")
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=60,
        help="Minuter mellan varje scan när --loop används (default 60)",
    )
    parser.add_argument("--test-telegram", action="store_true", help="Skicka ett testmeddelande till Telegram och avsluta")
    args = parser.parse_args()

    if args.test_telegram:
        send_test_message()
        return

    if not args.loop:
        run_once()
        return

    print(f"Kör i loop-läge, scannar var {args.interval_minutes}:e minut. Avbryt med Ctrl+C.")
    while True:
        run_once()
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    main()
