import pandas as pd

def ema(series, period):
    return series.ewm(span=period).mean()

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(period).mean() / loss.rolling(period).mean()
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    df["ema_fast"] = ema(df["close"], 12)
    df["ema_slow"] = ema(df["close"], 26)
    df["rsi"] = rsi(df["close"])
    return df