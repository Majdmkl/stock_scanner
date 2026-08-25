"""
Testar notification_state.py med syntetisk data (ingen nätverksanslutning
eller Telegram-konfiguration krävs).

Verifierar tre scenarion:
  (a) Ny setup -> should_notify() = True, state sparas korrekt.
  (b) Samma setup igen inom cooldown-fönstret -> should_notify() = False.
  (c) Samma setup-typ efter att cooldown gått ut -> should_notify() = True.

Kör med:
    python test_notification_state.py
"""
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta

# Importera modulen vi testar
from notification_state import (
    NotificationRecord,
    load_state,
    record_notification,
    save_state,
    should_notify,
)
from analysis import Setup


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

def _make_setup(kind: str = "demand_zone", level_low: float = 100.0, level_high: float = 105.0) -> Setup:
    return Setup(
        kind=kind,
        level_low=level_low,
        level_high=level_high,
        distance_pct=0.01,
        description=f"testsetup {kind}",
    )


def _ok(condition: bool, label: str) -> None:
    status = "OK  " if condition else "FEL "
    print(f"  [{status}] {label}")
    if not condition:
        raise AssertionError(f"Test misslyckades: {label}")


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------

def test_ny_setup_skickar(state: dict) -> None:
    """(a) En ny setup för en ticker som aldrig sett förut ska skicka notis."""
    setup = _make_setup()
    result = should_notify(state, "NVDA", setup, cooldown_hours=6)
    _ok(result is True, "Ny setup -> should_notify() = True")

    record_notification(state, "NVDA", setup)
    _ok("NVDA:demand_zone" in state, "record_notification() sparar korrekt nyckel")
    rec = state["NVDA:demand_zone"]
    _ok(rec.level_low == 100.0, "level_low sparas korrekt")
    _ok(rec.level_high == 105.0, "level_high sparas korrekt")


def test_cooldown_aktiv_samma_niva(state: dict) -> None:
    """(b) Samma setup igen INOM cooldown -> ska INTE skicka."""
    setup = _make_setup()
    result = should_notify(state, "NVDA", setup, cooldown_hours=6)
    _ok(result is False, "Samma setup inom cooldown -> should_notify() = False")


def test_cooldown_aktiv_ny_niva(state: dict) -> None:
    """Ny prisnivå (>2% skillnad) inom cooldown -> ska skicka trots cooldown."""
    setup_ny_niva = _make_setup(level_low=90.0, level_high=94.0)  # >2% lägre
    result = should_notify(state, "NVDA", setup_ny_niva, cooldown_hours=6, level_tolerance_pct=0.02)
    _ok(result is True, "Ny nivå inom cooldown -> should_notify() = True")


def test_cooldown_utgangen(state: dict) -> None:
    """(c) Simulera att cooldown gått ut genom att backa sent_at i state."""
    # Sätt sent_at till 7 timmar sedan
    gammal_tid = (datetime.now() - timedelta(hours=7)).isoformat(timespec="seconds")
    state["NVDA:demand_zone"] = NotificationRecord(
        ticker="NVDA",
        kind="demand_zone",
        level_low=100.0,
        level_high=105.0,
        sent_at=gammal_tid,
    )
    setup = _make_setup()
    result = should_notify(state, "NVDA", setup, cooldown_hours=6)
    _ok(result is True, "Cooldown utgången (7h > 6h) -> should_notify() = True")


def test_annan_setup_typ(state: dict) -> None:
    """Annan setup-typ (fvg) för samma ticker -> eget cooldown, ska skicka."""
    setup_fvg = _make_setup(kind="fvg", level_low=108.0, level_high=112.0)
    result = should_notify(state, "NVDA", setup_fvg, cooldown_hours=6)
    _ok(result is True, "Annan setup-typ (fvg) -> eget cooldown, should_notify() = True")


def test_spara_och_ladda_fil(tmp_path: str) -> None:
    """State sparas till disk och laddas tillbaka korrekt."""
    state: dict = {}
    setup = _make_setup()
    record_notification(state, "AAPL", setup)
    save_state(state, path=tmp_path)

    _ok(os.path.exists(tmp_path), "JSON-filen skapas")

    laddat = load_state(path=tmp_path)
    _ok("AAPL:demand_zone" in laddat, "Nyckel finns efter inläsning")
    rec = laddat["AAPL:demand_zone"]
    _ok(rec.ticker == "AAPL", "ticker läses tillbaka korrekt")
    _ok(rec.level_low == 100.0, "level_low läses tillbaka korrekt")


def test_ladda_saknad_fil() -> None:
    """load_state() på en fil som inte finns ger tom dict utan krasch."""
    state = load_state(path="/tmp/finns_ej_xyzxyz.json")
    _ok(state == {}, "Saknad fil -> tom dict, ingen krasch")


def test_skadad_fil(tmp_path: str) -> None:
    """load_state() på en skadad JSON-fil ger tom dict med varning."""
    with open(tmp_path, "w") as f:
        f.write("detta är inte JSON {{{")
    state = load_state(path=tmp_path)
    _ok(state == {}, "Skadad JSON-fil -> tom dict, ingen krasch")


# ---------------------------------------------------------------------------
# Kör alla tester
# ---------------------------------------------------------------------------

def run_all() -> None:
    print("=" * 55)
    print("Testar notification_state.py")
    print("=" * 55)

    state: dict = {}

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        print("\n--- (a) Ny setup ---")
        test_ny_setup_skickar(state)

        print("\n--- (b) Cooldown aktiv ---")
        test_cooldown_aktiv_samma_niva(state)
        test_cooldown_aktiv_ny_niva(state)

        print("\n--- (c) Cooldown utgången ---")
        test_cooldown_utgangen(state)

        print("\n--- Övriga fall ---")
        test_annan_setup_typ(state)

        print("\n--- Fil-I/O ---")
        test_spara_och_ladda_fil(tmp_path)
        test_ladda_saknad_fil()

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp2:
            test_skadad_fil(tmp2.name)
            os.unlink(tmp2.name)

        print("\n" + "=" * 55)
        print("Alla tester OK.")
        print("=" * 55)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


if __name__ == "__main__":
    run_all()
