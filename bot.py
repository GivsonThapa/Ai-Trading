import ccxt
import pandas as pd
from dotenv import load_dotenv
import csv
from pathlib import Path
from datetime import datetime
import requests
import os

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

COOLDOWN_HOURS = 1

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=payload, timeout=10)
    except:
        pass


def get_state():

    if not STATE_FILE.exists():
        return {
            "balance": START_BALANCE,
            "position": 0.0,
            "entry_price": 0.0,
            "last_trade_time": ""
        }

    with open(STATE_FILE, "r") as f:
        content = f.read().strip()

    if not content:
        return {
            "balance": START_BALANCE,
            "position": 0.0,
            "entry_price": 0.0,
            "last_trade_time": ""
        }

    parts = content.split(",")

    while len(parts) < 4:
        parts.append("")

    return {
        "balance": float(parts[0]),
        "position": float(parts[1]),
        "entry_price": float(parts[2]),
        "last_trade_time": parts[3]
    }


def save_state(state):

    with open(STATE_FILE, "w") as f:

        f.write(
            f"{state['balance']},"
            f"{state['position']},"
            f"{state['entry_price']},"
            f"{state['last_trade_time']}"
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


def cooldown_active(last_trade_time):

    if not last_trade_time:
        return False

    try:

        last_trade = datetime.fromisoformat(last_trade_time)

        hours = (
            datetime.utcnow() - last_trade
        ).total_seconds() / 3600

        return hours < COOLDOWN_HOURS

    except:
        return False


def run():

    state = get_state()

    # 5m timeframe
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

    # 1h timeframe trend confirmation
    higher_data = exchange.fetch_ohlcv(
        "BTC/USD",
        timeframe="1h"
    )

    higher_df = pd.DataFrame(
        higher_data,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    )

    higher_df = add_indicators(higher_df)

    latest = df.iloc[-1]
    higher_latest = higher_df.iloc[-1]

    price = float(latest["close"])

    signal = "HOLD"
    reason = "No clear signal"

    # Average volume filter
    avg_volume = df["volume"].tail(20).mean()

    volume_ok = latest["volume"] > avg_volume

    # Higher timeframe trend
    higher_trend_bullish = (
        higher_latest["ema_fast"]
        > higher_latest["ema_slow"]
    )

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

    else:

        if cooldown_active(state["last_trade_time"]):

            signal = "HOLD"
            reason = "Cooldown active"

        elif (
            latest["ema_fast"] > latest["ema_slow"]
            and latest["rsi"] < 70
            and volume_ok
            and higher_trend_bullish
        ):

            signal = "BUY"

            reason = (
                "EMA bullish + RSI valid + "
                "Volume confirmed + 1h trend bullish"
            )

        elif latest["ema_fast"] < latest["ema_slow"]:

            signal = "SELL"
            reason = "EMA bearish"

    # News filter
    news = get_news()

    risky_news, risk_word = news_is_risky(news)

    if signal == "BUY" and risky_news:

        signal = "HOLD"

        reason = f"Risky news detected: {risk_word}"

    log_decision(signal, price, reason)

    print("BTC Price:", price)
    print("Signal:", signal)
    print("Reason:", reason)

    # BUY
    if signal == "BUY" and state["position"] <= 0:

        trade_amount = (
            state["balance"]
            * RISK_PER_TRADE
        )

        quantity = trade_amount / price

        state["balance"] -= trade_amount

        state["position"] = quantity

        state["entry_price"] = price

        state["last_trade_time"] = (
            datetime.utcnow().isoformat()
        )

        log_trade(
            "BUY",
            price,
            quantity,
            reason
        )

        send_telegram(
            f"🟢 BUY BTC/USD\n"
            f"Price: {price}\n"
            f"Reason: {reason}"
        )

        print("PAPER BUY executed")

    # SELL
    elif signal == "SELL" and state["position"] > 0:

        quantity = state["position"]

        sell_value = quantity * price

        state["balance"] += sell_value

        state["position"] = 0.0

        state["entry_price"] = 0.0

        state["last_trade_time"] = (
            datetime.utcnow().isoformat()
        )

        log_trade(
            "SELL",
            price,
            quantity,
            reason
        )

        send_telegram(
            f"🔴 SELL BTC/USD\n"
            f"Price: {price}\n"
            f"Reason: {reason}"
        )

        print("PAPER SELL executed")

    else:

        print("No paper trade executed")

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
