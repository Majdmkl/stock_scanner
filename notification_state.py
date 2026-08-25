"""
Hanterar cooldown och deduplicering av Telegram-notiser.

Sparar en lokal JSON-fil (notification_state.json) med metadata om den
senast skickade notisen per ticker+setup-typ. Filen läses in vid start av
varje scan och skrivs tillbaka efter att notiser skickats, så tillståndet
överlever mellan separata körningar (manuella, cron, launchd, --loop).

Nyckel i JSON: "{TICKER}:{kind}", t.ex. "NVDA:demand_zone".
"""
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Dict

from analysis import Setup
from config import (
    NOTIFICATION_COOLDOWN_HOURS,
    NOTIFICATION_LEVEL_TOLERANCE_PCT,
    NOTIFICATION_STATE_FILE,
)


@dataclass
class NotificationRecord:
    """Metadata om den senast skickade notisen för en ticker+setup-typ."""

    ticker: str
    kind: str
    level_low: float
    level_high: float
    sent_at: str  # ISO 8601, t.ex. "2025-06-01T14:30:00"


# ---------------------------------------------------------------------------
# Läsning / skrivning
# ---------------------------------------------------------------------------

def load_state(path: str = NOTIFICATION_STATE_FILE) -> Dict[str, NotificationRecord]:
    """
    Läser in notification-state från JSON-fil. Returnerar en tom dict om
    filen saknas eller är skadad — ett läsfel ska aldrig krascha scannen.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw: dict = json.load(f)
        return {key: NotificationRecord(**data) for key, data in raw.items()}
    except Exception as e:
        print(f"[VARNING] Kunde inte läsa {path}: {e} — startar med tomt notis-state.")
        return {}


def save_state(state: Dict[str, NotificationRecord], path: str = NOTIFICATION_STATE_FILE) -> None:
    """
    Skriver notification-state till JSON-fil. Ett skrivfel loggas men
    kraschar aldrig scannen.
    """
    try:
        raw = {key: asdict(record) for key, record in state.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[VARNING] Kunde inte spara {path}: {e}")


# ---------------------------------------------------------------------------
# Beslutsfunktion
# ---------------------------------------------------------------------------

def should_notify(
    state: Dict[str, NotificationRecord],
    ticker: str,
    setup: Setup,
    cooldown_hours: float = NOTIFICATION_COOLDOWN_HOURS,
    level_tolerance_pct: float = NOTIFICATION_LEVEL_TOLERANCE_PCT,
) -> bool:
    """
    Returnerar True om en Telegram-notis bör skickas, False om den ska
    skippas pga cooldown och oförändrad prisnivå.

    Skickar alltid om:
      - Ingen tidigare notis finns för detta ticker+setup-typ.
      - Cooldown-fönstret (NOTIFICATION_COOLDOWN_HOURS) har gått ut.
      - Prisnivån (level_low eller level_high) har ändrats mer än
        NOTIFICATION_LEVEL_TOLERANCE_PCT — priset lämnade zonen och en
        ny, annan zon identifierats.

    Skippar (returnerar False) om:
      - Cooldown är aktiv OCH nivån är i princip densamma som förra gången.
    """
    key = f"{ticker}:{setup.kind}"
    record = state.get(key)

    if record is None:
        return True  # aldrig skickat för denna kombination

    sent_at = datetime.fromisoformat(record.sent_at)
    if datetime.now() - sent_at > timedelta(hours=cooldown_hours):
        return True  # cooldown har gått ut

    # Cooldown är aktiv — kolla om nivån har ändrats signifikant
    def _rel_diff(a: float, b: float) -> float:
        denom = max(abs(b), 1e-9)
        return abs(a - b) / denom

    if _rel_diff(setup.level_low, record.level_low) > level_tolerance_pct:
        return True  # ny zon, annan nivå
    if _rel_diff(setup.level_high, record.level_high) > level_tolerance_pct:
        return True  # ny zon, annan nivå

    return False  # samma zon, cooldown aktiv → skippa


# ---------------------------------------------------------------------------
# Uppdatering
# ---------------------------------------------------------------------------

def record_notification(
    state: Dict[str, NotificationRecord],
    ticker: str,
    setup: Setup,
) -> None:
    """
    Uppdaterar state i minnet med tidpunkt och nivåer för den notis som
    precis skickades. Anropa save_state() efter att alla tickers bearbetats
    för att skriva till disk.
    """
    key = f"{ticker}:{setup.kind}"
    state[key] = NotificationRecord(
        ticker=ticker,
        kind=setup.kind,
        level_low=setup.level_low,
        level_high=setup.level_high,
        sent_at=datetime.now().isoformat(timespec="seconds"),
    )