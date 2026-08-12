import os
import time
import json
import logging

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TOP_SYMBOLS = int(os.getenv("TOP_SYMBOLS", "100"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "5"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "12"))
VOLUME_MULTIPLIER = float(os.getenv("VOLUME_MULTIPLIER", "1.50"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))

BASE = "https://fapi.binance.com"

session = requests.Session()
session.headers["User-Agent"] = "KriptoBot-4H/1.0"

STATE_FILE = "state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


def api_get(path, params=None):
    response = session.get(
        BASE + path,
        params=params,
        timeout=15
    )
    response.raise_for_status()
    return response.json()


def telegram_send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik."
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    response = session.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=15
    )

    response.raise_for_status()


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2
        )


def ema(series, period):
    return series.ewm(
        span=period,
        adjust=False
    ).mean()


def rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def get_klines(symbol, limit=100):
    data = api_get(
        "/fapi/v1/klines",
        {
            "symbol": symbol,
            "interval": "4h",
            "limit": limit
        }
    )

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_volume",
        "trades",
        "taker_base",
        "taker_quote",
        "ignore"
    ]

    df = pd.DataFrame(data, columns=columns)

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume"
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["close_time"] = pd.to_datetime(
        df["close_time"],
        unit="ms",
        utc=True
    )

    return df


def closed_candles(df):
    now = pd.Timestamp.now(tz="UTC")

    return df[
        df["close_time"] <= now
    ].copy()


def get_symbols():
    info = api_get("/fapi/v1/exchangeInfo")

    result = []

    for symbol in info["symbols"]:
        if (
            symbol["status"] == "TRADING"
            and symbol["contractType"] == "PERPETUAL"
            and symbol["quoteAsset"] == "USDT"
        ):
            result.append(symbol["symbol"])

    return result


def get_top_symbols(all_symbols):
    tickers = api_get("/fapi/v1/ticker/24hr")

    allowed = set(all_symbols)

    rows = []

    for ticker in tickers:
        if ticker["symbol"] in allowed:
            rows.append(
                (
                    ticker["symbol"],
                    float(ticker["quoteVolume"])
                )
            )

    rows.sort(
        key=lambda x: x[1],
        reverse=True
    )

    return [
        symbol
        for symbol, volume in rows[:TOP_SYMBOLS]
    ]


def get_funding(symbol):
    try:
        data = api_get(
            "/fapi/v1/premiumIndex",
            {"symbol": symbol}
        )

        return float(
            data.get("lastFundingRate", 0)
        )

    except Exception:
        return 0.0


def get_open_interest(symbol):
    try:
        current = api_get(
            "/fapi/v1/openInterest",
            {"symbol": symbol}
        )

        current_oi = float(
            current["openInterest"]
        )

        history = api_get(
            "/futures/data/openInterestHist",
            {
                "symbol": symbol,
                "period": "4h",
                "limit": 2
            }
        )

        if len(history) >= 2:
            previous_oi = float(
                history[-2]["sumOpenInterest"]
            )

            if previous_oi:
                change = (
                    (current_oi - previous_oi)
                    / previous_oi
                    * 100
                )
            else:
                change = None
        else:
            change = None

        return current_oi, change

    except Exception:
        return None, None


def get_btc_filter():
    df = closed_candles(
        get_klines("BTCUSDT", 100)
    )

    df["ema20"] = ema(
        df["close"],
        20
    )

    df["ema50"] = ema(
        df["close"],
        50
    )

    x = df.iloc[-1]

    return {
        "long":
            x["close"] > x["ema20"]
            and x["ema20"] >= x["ema50"],

        "short":
            x["close"] < x["ema20"]
            and x["ema20"] <= x["ema50"]
    }


def analyze(symbol, btc_filter):
    df = closed_candles(
        get_klines(symbol, 100)
    )

    if len(df) < 60:
        return None

    df["rsi"] = rsi(
        df["close"],
        14
    )

    df["ema20"] = ema(
        df["close"],
        20
    )

    df["ema50"] = ema(
        df["close"],
        50
    )

    df["volume_average"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    current = df.iloc[-1]
    previous = df.iloc[-2]

    volume_ratio = (
        current["volume"]
        / current["volume_average"]
    )

    volume_ok = (
        volume_ratio >= VOLUME_MULTIPLIER
    )

    funding_rate = get_funding(symbol)

    oi, oi_change = get_open_interest(symbol)

    # =========================
    # LONG
    # =========================

    long_rsi = (
        30 <= previous["rsi"] <= 42
        and current["rsi"] > previous["rsi"]
        and current["rsi"] >= 35
    )

    long_ema = (
        previous["close"] <= previous["ema20"]
        and current["close"] > current["ema20"]
    )

    long_funding = (
        funding_rate <= 0.0005
    )

    long_trend = (
        current["ema20"] > current["ema50"]
        and current["close"]
        >= current["ema50"] * 0.995
    )

    resistance = (
        df["high"]
        .shift(1)
        .rolling(20)
        .max()
        .iloc[-1]
    )

    resistance_break = (
        current["close"] > resistance
    )

    long_score = sum([
        long_rsi,
        long_ema,
        volume_ok,
        long_funding,
        long_trend,
        resistance_break
    ])

    # =========================
    # SHORT
    # =========================

    short_rsi = (
        58 <= previous["rsi"] <= 70
        and current["rsi"] < previous["rsi"]
        and current["rsi"] <= 65
    )

    short_ema = (
        previous["close"] >= previous["ema20"]
        and current["close"] < current["ema20"]
    )

    short_funding = (
        funding_rate >= -0.0005
    )

    short_trend = (
        current["ema20"] < current["ema50"]
        and current["close"]
        <= current["ema50"] * 1.005
    )

    support = (
        df["low"]
        .shift(1)
        .rolling(20)
        .min()
        .iloc[-1]
    )

    support_break = (
        current["close"] < support
    )

    short_score = sum([
        short_rsi,
        short_ema,
        volume_ok,
        short_funding,
        short_trend,
        support_break
    ])

    direction = None
    score = 0

    # BTC trend filtresi
    if (
        btc_filter["long"]
        and long_score >= MIN_SCORE
        and long_score > short_score
    ):
        direction = "LONG"
        score = long_score

    elif (
        btc_filter["short"]
        and short_score >= MIN_SCORE
        and short_score > long_score
    ):
        direction = "SHORT"
        score = short_score

    if direction is None:
        return None

    level = (
        resistance
        if direction == "LONG"
        else support
    )

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "price": float(current["close"]),
        "rsi_previous": float(previous["rsi"]),
        "rsi": float(current["rsi"]),
        "volume_percent":
            (volume_ratio - 1) * 100,
        "funding_percent":
            funding_rate * 100,
        "oi_change": oi_change,
        "level": float(level),
        "candle":
            current["close_time"].isoformat()
    }


def format_signal(signal):
    long_signal = (
        signal["direction"] == "LONG"
    )

    emoji = (
        "🟢"
        if long_signal
        else "🔴"
    )

    arrow = (
        "↗️"
        if long_signal
        else "↘️"
    )

    level_name = (
        "Direnç"
        if long_signal
        else "Destek"
    )

    if signal["oi_change"] is None:
        oi_text = "bilgi yok"
    else:
        oi_text = (
            f"{signal['oi_change']:+.2f}%"
        )

    return (
        f"{emoji} "
        f"{signal['direction']} ADAYI — "
        f"{signal['symbol']}\n\n"

        f"RSI: "
        f"{signal['rsi_previous']:.1f}"
        f" → "
        f"{signal['rsi']:.1f} "
        f"{arrow}\n"

        f"EMA20: "
        f"{'ÜSTÜNE' if long_signal else 'ALTINA'} "
        f"4H KAPANIŞ ✅\n"

        f"Hacim: "
        f"+{signal['volume_percent']:.0f}% 🔥\n"

        f"Funding: "
        f"{signal['funding_percent']:+.4f}%\n"

        f"OI değişimi: "
        f"{oi_text}\n"

        f"{level_name}: "
        f"{signal['level']:.8g}\n\n"

        f"📊 Skor: "
        f"{signal['score']}/6\n"

        f"⏱ 4H kapanışı\n\n"

        f"⚠️ SADECE ADAY SİNYALİ\n"
        f"Grafiği kontrol et, "
        f"işlemi sen değerlendir."
    )


def should_send(state, signal):
    key = (
        f"{signal['symbol']}:"
        f"{signal['direction']}"
    )

    last_time = state.get(
        key,
        0
    )

    return (
        time.time() - last_time
        >= COOLDOWN_HOURS * 3600
    )


def scan():
    all_symbols = get_symbols()

    watchlist = get_top_symbols(
        all_symbols
    )

    btc_filter = get_btc_filter()

    state = load_state()

    sent = 0

    logging.info(
        "4H tarama başladı: %d coin",
        len(watchlist)
    )

    for symbol in watchlist:

        if symbol == "BTCUSDT":
            continue

        try:
            signal = analyze(
                symbol,
                btc_filter
            )

            if (
                signal
                and should_send(
                    state,
                    signal
                )
            ):

                telegram_send(
                    format_signal(signal)
                )

                key = (
                    f"{signal['symbol']}:"
                    f"{signal['direction']}"
                )

                state[key] = time.time()

                save_state(state)

                sent += 1

                logging.info(
                    "Sinyal: %s %s %d/6",
                    signal["symbol"],
                    signal["direction"],
                    signal["score"]
                )

        except Exception as error:

            logging.warning(
                "%s atlandı: %s",
                symbol,
                error
            )

        time.sleep(0.08)

    logging.info(
        "Tarama bitti. Gönderilen: %d",
        sent
    )


def main():
    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID eksik."
        )

    logging.info(
        "Kripto Bot başladı."
    )

    try:
        scan()

    except Exception as error:
        logging.exception(
            "Tarama hatası: %s",
            error
        )
        raise


if __name__ == "__main__":
    main()
