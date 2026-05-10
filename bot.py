import ccxt
import pandas as pd
from dotenv import load_dotenv
import csv
from pathlib import Path
from datetime import datetime

from indicators import add_indicators
from news_feed import get_news, news_is_risky

load_dotenv()

exchange = ccxt.kraken()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

TRADES_FILE = DATA_DIR / "trades.csv"
STATE_FILE = DATA_DIR / "state.txt"
DECISION_FILE = DATA_DIR / "decision_log.csv"

START_BALANCE = 1000
RISK_PER_TRADE = 0.01
STOP_LOSS = 0.02
TAKE_PROFIT = 0.04


def get_state():
    if not STATE_FILE.exists():
        return {
            "balance": START_BALANCE,
            "position": 0.0,
            "entry_price": 0.0
        }

    with open(STATE_FILE, "r") as f:
        content = f.read().strip()

    if not content:
        return {
            "balance": START_BALANCE,
            "position": 0.0,
            "entry_price": 0.0
        }

    parts = content.split(",")

    return {
        "balance": float(parts[0]),
        "position": float(parts[1]),
        "entry_price": float(parts[2])
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        f.write(
            f"{state['balance']},{state['position']},{state['entry_price']}"
        )


def log_trade(action, price, quantity, reason):
    file_exists = TRADES_FILE.exists()

    with open(TRADES_FILE, "a", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "time",
                "action",
                "price",
                "quantity",
                "reason"
            ])

        writer.writerow([
            datetime.now(),
            action,
            price,
            quantity,
            reason
        ])


def log_decision(signal, price, reason):
    file_exists = DECISION_FILE.exists()

    with open(DECISION_FILE, "a", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "time",
                "signal",
                "price",
                "reason"
            ])

        writer.writerow([
            datetime.now(),
            signal,
            price,
            reason
        ])


def run():
    state = get_state()

    data = exchange.fetch_ohlcv(
        "BTC/USD",
        timeframe="5m"
    )

    df = pd.DataFrame(
        data,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    )

    df = add_indicators(df)

    latest = df.iloc[-1]
    price = float(latest["close"])

    signal = "HOLD"
    reason = "No clear signal"

    # Existing position handling
    if state["position"] > 0:

        if price <= state["entry_price"] * (1 - STOP_LOSS):
            signal = "SELL"
            reason = "Stop loss triggered"

        elif price >= state["entry_price"] * (1 + TAKE_PROFIT):
            signal = "SELL"
            reason = "Take profit triggered"

        else:
            signal = "HOLD"
            reason = "Already holding BTC position"

    # New signal generation
    else:

        if (
            latest["ema_fast"] > latest["ema_slow"]
            and latest["rsi"] < 70
        ):
            signal = "BUY"
            reason = "EMA fast above EMA slow and RSI below 70"

        elif latest["ema_fast"] < latest["ema_slow"]:
            signal = "SELL"
            reason = "EMA fast below EMA slow"

    # News filter
    news = get_news()

    risky_news, risk_word = news_is_risky(news)

    if signal == "BUY" and risky_news:
        signal = "HOLD"
        reason = f"Risky news detected: {risk_word}"

    # Logging
    log_decision(signal, price, reason)

    print("BTC Price:", price)
    print("Signal:", signal)
    print("Reason:", reason)

    print("\nNews headlines:")

    for n in news:
        print("-", n.get("title", "No title"))

    # Execute BUY
    if signal == "BUY" and state["position"] <= 0:

        trade_amount = state["balance"] * RISK_PER_TRADE

        quantity = trade_amount / price

        state["balance"] -= trade_amount
        state["position"] = quantity
        state["entry_price"] = price

        log_trade(
            "BUY",
            price,
            quantity,
            reason
        )

        print("\nPAPER BUY executed")

    # Execute SELL
    elif signal == "SELL" and state["position"] > 0:

        quantity = state["position"]

        sell_value = quantity * price

        state["balance"] += sell_value

        state["position"] = 0.0
        state["entry_price"] = 0.0

        log_trade(
            "SELL",
            price,
            quantity,
            reason
        )

        print("\nPAPER SELL executed")

    else:
        print("\nNo paper trade executed")

    total_value = (
        state["balance"]
        + (state["position"] * price)
    )

    print("\nPaper account:")
    print("Balance:", round(state["balance"], 2))
    print("Position:", state["position"])
    print("Entry price:", state["entry_price"])
    print("Total value:", round(total_value, 2))

    save_state(state)


run()
