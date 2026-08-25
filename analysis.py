"""
Teknisk analys: demand zones, trendlinjer och Fair Value Gaps (FVG).

Alla funktioner tar en OHLCV-DataFrame (kolumner Open/High/Low/Close/Volume)
och är rena i den bemärkelsen att de inte hämtar data eller ritar något -
de returnerar bara strukturerade resultat (dataclasses).
"""
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from config import (
    FVG_MIN_GAP_PCT,
    MAX_ZONE_AGE_BARS,
    PROXIMITY_ATR_MULT,
    SWING_LOOKBACK,
    ZONE_MIN_IMPULSE_PCT,
)


# ---------------------------------------------------------------------------
# Datastrukturer
# ---------------------------------------------------------------------------

@dataclass
class DemandZone:
    low: float
    high: float
    start_idx: int
    end_idx: int


@dataclass
class TrendLine:
    slope: float
    intercept: float
    p1_idx: int
    p2_idx: int
    p1_price: float
    p2_price: float

    def value_at(self, idx: int) -> float:
        return self.slope * idx + self.intercept


@dataclass
class FVG:
    low: float
    high: float
    idx: int  # index för mittencandlen i 3-candle-mönstret


@dataclass
class Setup:
    kind: str  # "demand_zone" | "trendline" | "fvg"
    level_low: float
    level_high: float
    distance_pct: float
    description: str
    zone: Optional[DemandZone] = None
    trendline: Optional[TrendLine] = None
    fvg: Optional[FVG] = None


# ---------------------------------------------------------------------------
# Hjälpfunktioner
# ---------------------------------------------------------------------------

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range - används för att normalisera "hur nära" priset
    behöver vara en nivå för att räknas som en aktuell setup."""
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _distance_pct(price: float, level: float) -> float:
    if price == 0:
        return float("inf")
    return abs(price - level) / price


def find_swing_lows(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> List[int]:
    """Index för candles vars Low är det lägsta inom +/- lookback candles."""
    lows = df["Low"].values
    swing_idx = []
    for i in range(lookback, len(lows) - lookback):
        window = lows[i - lookback : i + lookback + 1]
        if lows[i] == window.min():
            swing_idx.append(i)
    return swing_idx


def find_swing_highs(df: pd.DataFrame, lookback: int = SWING_LOOKBACK) -> List[int]:
    """Index för candles vars High är det högsta inom +/- lookback candles."""
    highs = df["High"].values
    swing_idx = []
    for i in range(lookback, len(highs) - lookback):
        window = highs[i - lookback : i + lookback + 1]
        if highs[i] == window.max():
            swing_idx.append(i)
    return swing_idx


# ---------------------------------------------------------------------------
# 1. Demand zones
# ---------------------------------------------------------------------------

def find_demand_zones(df: pd.DataFrame) -> List[DemandZone]:
    """
    Hittar konsolideringar (baser) runt en swing low som följs av en tydlig
    impulsiv rörelse uppåt (>= ZONE_MIN_IMPULSE_PCT). Zonens gränser är
    lägsta/högsta pris i konsolideringen.
    """
    work = df.tail(MAX_ZONE_AGE_BARS).reset_index(drop=True)
    if len(work) < 20:
        return []

    swing_lows = find_swing_lows(work)
    zones: List[DemandZone] = []

    for idx in swing_lows:
        base_start = max(0, idx - 3)
        base_end = min(len(work) - 1, idx + 3)
        base_slice = work.iloc[base_start : base_end + 1]

        base_low = float(base_slice["Low"].min())
        base_high = float(base_slice["High"].max())

        lookahead_end = min(len(work) - 1, base_end + 10)
        if lookahead_end <= base_end:
            continue

        move_high = float(work["High"].iloc[base_end + 1 : lookahead_end + 1].max())
        if base_high <= 0:
            continue

        impulse_pct = (move_high - base_high) / base_high
        if impulse_pct >= ZONE_MIN_IMPULSE_PCT:
            zones.append(
                DemandZone(low=base_low, high=base_high, start_idx=base_start, end_idx=base_end)
            )

    zones = sorted(zones, key=lambda z: z.end_idx)
    return zones[-8:]  # begränsa till de 8 senaste zonerna


# ---------------------------------------------------------------------------
# 2. Trendlinjer (higher lows)
# ---------------------------------------------------------------------------

def find_trendline(df: pd.DataFrame) -> Optional[TrendLine]:
    """
    Bygger en stigande trendlinje genom de två senaste "higher lows"
    (swing lows som stiger i pris över tid).
    """
    work = df.tail(MAX_ZONE_AGE_BARS).reset_index(drop=True)
    if len(work) < 20:
        return None

    swing_idx = find_swing_lows(work)
    if len(swing_idx) < 2:
        return None

    points = [(i, float(work["Low"].iloc[i])) for i in swing_idx]

    higher_lows = [points[0]]
    for p in points[1:]:
        if p[1] > higher_lows[-1][1]:
            higher_lows.append(p)

    if len(higher_lows) < 2:
        return None

    (x1, y1), (x2, y2) = higher_lows[-2], higher_lows[-1]
    if x2 == x1:
        return None

    slope = (y2 - y1) / (x2 - x1)
    intercept = y1 - slope * x1

    return TrendLine(slope=slope, intercept=intercept, p1_idx=x1, p2_idx=x2, p1_price=y1, p2_price=y2)


# ---------------------------------------------------------------------------
# 3. Fair Value Gaps
# ---------------------------------------------------------------------------

def find_fvgs(df: pd.DataFrame) -> List[FVG]:
    """
    Bullish FVG: gap mellan High på candle 1 och Low på candle 3 i en serie
    om tre candles (dvs candle 3 gapar upp över candle 1, mittencandlen
    "hoppar över" den zonen).
    """
    work = df.tail(MAX_ZONE_AGE_BARS).reset_index(drop=True)
    if len(work) < 3:
        return []

    fvgs: List[FVG] = []
    for i in range(2, len(work)):
        c1_high = float(work["High"].iloc[i - 2])
        c3_low = float(work["Low"].iloc[i])

        if c3_low > c1_high and c1_high > 0:
            gap_pct = (c3_low - c1_high) / c1_high
            if gap_pct >= FVG_MIN_GAP_PCT:
                fvgs.append(FVG(low=c1_high, high=c3_low, idx=i - 1))

    return fvgs[-5:]  # begränsa till de 5 senaste gapen


# ---------------------------------------------------------------------------
# Scoring / urval
# ---------------------------------------------------------------------------

def evaluate_setups(df: pd.DataFrame) -> Optional[Setup]:
    """
    Kör demand zone-, trendlinje- och FVG-analys på en tidsram och
    returnerar den setup vars nivå ligger närmast (i %) nuvarande pris,
    så länge avståndet är inom PROXIMITY_ATR_MULT * ATR. Returnerar None
    om ingen relevant setup hittas.
    """
    if df is None or df.empty or len(df) < 30:
        return None

    work = df.reset_index(drop=True)
    current_price = float(work["Close"].iloc[-1])

    atr_series = _atr(work)
    atr = atr_series.iloc[-1]
    if pd.isna(atr) or atr <= 0 or current_price <= 0:
        return None

    max_dist = (atr * PROXIMITY_ATR_MULT) / current_price

    candidates: List[Setup] = []

    for zone in find_demand_zones(work):
        ref = zone.high  # övre kanten av zonen = det priset som ligger närmast nuvarande pris
        dist = _distance_pct(current_price, ref)
        if dist <= max_dist:
            candidates.append(
                Setup(
                    kind="demand_zone",
                    level_low=zone.low,
                    level_high=zone.high,
                    distance_pct=dist,
                    description=f"demand zone ${zone.low:.2f}-${zone.high:.2f}",
                    zone=zone,
                )
            )

    tl = find_trendline(work)
    if tl is not None:
        last_idx = len(work) - 1
        tl_price = tl.value_at(last_idx)
        if tl_price > 0:
            dist = _distance_pct(current_price, tl_price)
            if dist <= max_dist:
                candidates.append(
                    Setup(
                        kind="trendline",
                        level_low=tl_price,
                        level_high=tl_price,
                        distance_pct=dist,
                        description=f"stigande trendlinje vid ${tl_price:.2f}",
                        trendline=tl,
                    )
                )

    for fvg in find_fvgs(work):
        mid = (fvg.low + fvg.high) / 2
        dist = _distance_pct(current_price, mid)
        if dist <= max_dist:
            candidates.append(
                Setup(
                    kind="fvg",
                    level_low=fvg.low,
                    level_high=fvg.high,
                    distance_pct=dist,
                    description=f"Fair Value Gap ${fvg.low:.2f}-${fvg.high:.2f}",
                    fvg=fvg,
                )
            )

    if not candidates:
        return None

    return min(candidates, key=lambda s: s.distance_pct)
