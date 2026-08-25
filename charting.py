"""
Grafritning med mplfinance + matplotlib.

Ritar en ren, "rapport-liknande" candlestick-graf i stil med de
referensbilder projektet utgick från: ljusgrå bakgrund, en rubrikrad
högst upp, ticker/tidsram som underrubrik, och en halvtransparent
textruta med tre punkter längst ner i högra hörnet. Den identifierade
setupen markeras direkt i grafen:
  - demand_zone / fvg -> grå horisontell zon över hela bredden
  - trendline         -> svart linje genom "higher lows"
"""
import os
from typing import List, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from analysis import Setup
from config import CHART_DIR

BG_COLOR = "#eaeaec"
UP_COLOR = "#3c8a46"
DOWN_COLOR = "#b23b3b"
ZONE_COLOR = "#8c8c8c"
TREND_COLOR = "#1a1a1a"
TEXTBOX_COLOR = "#d3d3d5"
TEXT_COLOR = "#1a1a1a"

KIND_LABELS = {
    "demand_zone": "Demand Zone",
    "trendline": "Trendlinje",
    "fvg": "Fair Value Gap",
}

_STYLE = mpf.make_mpf_style(
    base_mpf_style="charles",
    marketcolors=mpf.make_marketcolors(
        up=UP_COLOR,
        down=DOWN_COLOR,
        edge="inherit",
        wick="inherit",
        volume="inherit",
    ),
    facecolor=BG_COLOR,
    figcolor=BG_COLOR,
    edgecolor="#4d4d4d",
    gridstyle="",
    rc={
        "axes.edgecolor": "#4d4d4d",
        "axes.labelcolor": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "font.size": 10,
    },
)


def plot_setup(
    df: pd.DataFrame,
    ticker: str,
    timeframe: str,
    setup: Setup,
    bullets: Optional[List[str]] = None,
    company_name: Optional[str] = None,
) -> str:
    """
    Sparar en PNG-fil med candlestick-graf + markerad setup och returnerar
    filsökvägen. `bullets` är en lista med (helst 3) korta textrader som
    visas i en ruta längst ner till höger i grafen, samma text som skickas
    som Telegram-bildtext.
    """
    os.makedirs(CHART_DIR, exist_ok=True)

    full_len = len(df)
    n_show = min(150, full_len)
    plot_df = df.tail(n_show).copy()
    offset = full_len - n_show  # global index (i hela df) för första raden i plot_df

    addplots = []
    if setup.kind == "trendline" and setup.trendline is not None:
        tl = setup.trendline
        line_vals = [tl.value_at(offset + i) for i in range(len(plot_df))]
        addplots.append(
            mpf.make_addplot(
                pd.Series(line_vals, index=plot_df.index),
                color=TREND_COLOR,
                width=1.6,
            )
        )

    kind_label = KIND_LABELS.get(setup.kind, setup.kind)
    fname = os.path.join(CHART_DIR, f"{ticker}_{timeframe}.png")

    plot_kwargs = dict(
        type="candle",
        style=_STYLE,
        figsize=(11, 7.5),
        returnfig=True,
        tight_layout=False,
        ylabel="",
        datetime_format="%d %b",
        xrotation=0,
    )
    if addplots:
        plot_kwargs["addplot"] = addplots

    fig, axlist = mpf.plot(plot_df, **plot_kwargs)
    ax = axlist[0]

    # Grå zon (demand zone / FVG) över hela grafens bredd
    if setup.kind in ("demand_zone", "fvg"):
        ax.axhspan(setup.level_low, setup.level_high, color=ZONE_COLOR, alpha=0.35, zorder=0)

    # Lämna plats högst upp för rubrikblocket och längst ner lite marginal
    fig.subplots_adjust(top=0.80, bottom=0.10, left=0.07, right=0.96)

    # --- Rubrikblock -------------------------------------------------
    fig.text(0.07, 0.955, "Chart Analysis", fontsize=17, fontweight="bold", color=TEXT_COLOR)
    subtitle = f"Ticker: ${ticker}    Time Frame: {timeframe.upper()}"
    if company_name and company_name != ticker:
        subtitle = f"{company_name}  |  {subtitle}"
    fig.text(0.07, 0.915, subtitle, fontsize=11, style="italic", color=TEXT_COLOR)
    fig.text(0.93, 0.915, kind_label, fontsize=11, fontweight="bold", ha="right", color=TEXT_COLOR)

    header_line = plt.Line2D([0.07, 0.96], [0.895, 0.895], transform=fig.transFigure, color="#333333", linewidth=1.1)
    fig.add_artist(header_line)

    # --- Textruta med punkter (nere till höger) -----------------------
    if bullets:
        box_text = "\n".join(bullets)
        ax.text(
            0.985,
            0.03,
            box_text,
            transform=ax.transAxes,
            fontsize=9.5,
            color=TEXT_COLOR,
            ha="right",
            va="bottom",
            linespacing=1.6,
            bbox=dict(boxstyle="round,pad=0.6", facecolor=TEXTBOX_COLOR, edgecolor="none", alpha=0.95),
            zorder=5,
        )

    fig.savefig(fname, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)

    return fname
