"""
Visual RSI explainer using real XAUUSD data.
Shows price chart with RSI subplot and Egon's entry/exit zones.

Usage:
    python -m analysis.rsi_explainer
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from src.core.config import load_config
from src.core.indicators import compute_indicators
from tests.data_cache import fetch_and_cache


def main():
    # Load M1 config for thresholds
    config = load_config("config/m1_params.json")

    # Get recent data - use M5 for cleaner visual
    data = fetch_and_cache(days=105)
    df = data["m5"].copy()

    # Compute indicators
    df = compute_indicators(df, config)
    df = df.dropna(subset=["RSI"]).reset_index(drop=True)

    # Take last 3 days (~864 M5 candles) for a readable chart
    df = df.tail(500).reset_index(drop=True)

    # Find entry/exit signals
    buy_signals = df[df["RSI"] < config.rsi_buy].index
    sell_signals = df[(df["RSI"] > config.rsi_sell) & df["downtrend"]].index
    exit_long = df[df["RSI"] > config.rsi_exit_long].index
    exit_short = df[df["RSI"] < config.rsi_exit_short].index

    # Plot
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(16, 9), height_ratios=[2, 1],
        sharex=True, gridspec_kw={"hspace": 0.05}
    )
    fig.patch.set_facecolor("#1a1a2e")

    # ── Price chart ─────────────────────────────────────────────────
    ax1.set_facecolor("#16213e")
    ax1.plot(df.index, df["close"], color="#e0e0e0", linewidth=0.8, label="XAUUSD Price")

    # Mark buy entries (green triangles)
    ax1.scatter(buy_signals, df.loc[buy_signals, "close"],
                marker="^", color="#00e676", s=40, zorder=5, label="LONG entry (RSI < 35)")

    # Mark sell entries (red triangles)
    ax1.scatter(sell_signals, df.loc[sell_signals, "close"],
                marker="v", color="#ff1744", s=40, zorder=5, label="SHORT entry (RSI > 65 + downtrend)")

    ax1.set_ylabel("Price ($)", color="#e0e0e0", fontsize=11)
    ax1.tick_params(colors="#e0e0e0")
    ax1.legend(loc="upper left", fontsize=9, facecolor="#16213e", edgecolor="#444",
               labelcolor="#e0e0e0")
    ax1.set_title("How Egon Uses RSI — XAUUSD M5", color="#e0e0e0", fontsize=14, pad=12)
    ax1.grid(True, alpha=0.15, color="#555")

    # ── RSI chart ───────────────────────────────────────────────────
    ax2.set_facecolor("#16213e")
    ax2.plot(df.index, df["RSI"], color="#64b5f6", linewidth=1.0, label="RSI")

    # Buy zone (oversold)
    ax2.axhspan(0, config.rsi_buy, alpha=0.15, color="#00e676")
    ax2.axhline(config.rsi_buy, color="#00e676", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.text(df.index[3], config.rsi_buy + 1.5, f"Buy zone < {config.rsi_buy:.0f}",
             color="#00e676", fontsize=9, va="bottom")

    # Sell zone (overbought)
    ax2.axhspan(config.rsi_sell, 100, alpha=0.15, color="#ff1744")
    ax2.axhline(config.rsi_sell, color="#ff1744", linestyle="--", linewidth=0.8, alpha=0.7)
    ax2.text(df.index[3], config.rsi_sell - 1.5, f"Sell zone > {config.rsi_sell:.0f}",
             color="#ff1744", fontsize=9, va="top")

    # Exit long threshold
    ax2.axhline(config.rsi_exit_long, color="#ffd740", linestyle=":", linewidth=0.8, alpha=0.6)
    ax2.text(df.index[-1], config.rsi_exit_long + 1, f"Exit LONG > {config.rsi_exit_long:.0f}",
             color="#ffd740", fontsize=8, ha="right")

    # Exit short threshold
    ax2.axhline(config.rsi_exit_short, color="#ffd740", linestyle=":", linewidth=0.8, alpha=0.6)
    ax2.text(df.index[-1], config.rsi_exit_short - 1, f"Exit SHORT < {config.rsi_exit_short:.0f}",
             color="#ffd740", fontsize=8, ha="right", va="top")

    # Neutral zone label
    mid = (config.rsi_buy + config.rsi_sell) / 2
    ax2.text(df.index[len(df)//2], mid, "Neutral — no action",
             color="#888", fontsize=10, ha="center", va="center", style="italic")

    # Color RSI line segments by zone
    for i in range(1, len(df)):
        rsi_val = df["RSI"].iloc[i]
        if rsi_val < config.rsi_buy:
            color = "#00e676"
        elif rsi_val > config.rsi_sell:
            color = "#ff1744"
        else:
            color = "#64b5f6"
        ax2.plot([df.index[i-1], df.index[i]],
                 [df["RSI"].iloc[i-1], df["RSI"].iloc[i]],
                 color=color, linewidth=1.2)

    ax2.set_ylim(5, 95)
    ax2.set_ylabel("RSI", color="#e0e0e0", fontsize=11)
    ax2.set_xlabel("Candles (M5)", color="#e0e0e0", fontsize=11)
    ax2.tick_params(colors="#e0e0e0")
    ax2.grid(True, alpha=0.15, color="#555")

    # Explanation box
    explanation = (
        "RSI (Relative Strength Index) measures momentum on a 0-100 scale.\n"
        "Low RSI = oversold (price dropped fast, likely to bounce)\n"
        "High RSI = overbought (price rose fast, likely to pull back)\n\n"
        f"Egon buys when RSI < {config.rsi_buy:.0f}, sells when RSI > {config.rsi_sell:.0f} + downtrend\n"
        f"Exits longs at RSI > {config.rsi_exit_long:.0f}, exits shorts at RSI < {config.rsi_exit_short:.0f}"
    )
    fig.text(0.5, -0.02, explanation, ha="center", va="top",
             fontsize=10, color="#bbb", style="italic",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#16213e", edgecolor="#444"))

    plt.tight_layout()
    plt.savefig("results/rsi_explainer.png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print("Saved to results/rsi_explainer.png")
    plt.close()


if __name__ == "__main__":
    main()