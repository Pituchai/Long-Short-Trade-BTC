# LongShortTrader Bot (Binance Testnet)

## Overview

This is a **Long/Short Grid-Based Trading Bot** implemented using the **Binance API (Testnet)**.  
It trades **BTC/USDT** automatically on the **1-minute timeframe** by polling Binance's REST API (no WebSocket required).

### Strategy Logic:

- **Go Long** when returns are **low** and volume change is **normal**.
- **Go Short** when returns are **high** and volume change is **normal**.
- **Close positions (neutral)** when conditions are not met.

---

## Key Features

- **Polling-Based Trading** – Fetches the latest klines every 5 seconds.
- **Long / Short / Neutral Actions** based on return and volume thresholds.
- **Real Trade Execution** using `MARKET` orders on **Binance Testnet**.
- **Trade Management** – Tracks PnL and stops after 100 trades.
- **Error Handling** – Handles API failures, user interruptions, and order errors gracefully.

---

## Strategy Summary

| Condition | Action |
|-----------|--------|
| `returns <= return_thresh[0]` & `volume in volume_thresh` | **Go Long** |
| `returns >= return_thresh[1]` & `volume in volume_thresh` | **Go Short** |
| Otherwise | **Close Position (Neutral)** |

---

## Bot Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `symbol` | Trading pair | `BTCUSDT` |
| `bar_length` | Candle interval | `1m` |
| `return_thresh` | Return thresholds (log returns) | `[-0.0001, 0.0001]` |
| `volume_thresh` | Volume change thresholds (log vol) | `[-3, 3]` |
| `units` | Trade size in BTC | `0.01` |

---

## Setup Instructions

### 1️⃣ Install Dependencies

```bash
pip install python-binance pandas numpy
