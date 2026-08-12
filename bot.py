import os
import time
import logging
import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv


# =========================================================
# ENV
# =========================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()

TOP_SYMBOLS = int(
    os.getenv("TOP_SYMBOLS", "100")
)

MIN_SCORE = int(
    os.getenv("MIN_SCORE", "4")
)

VOLUME_MULTIPLIER = float(
    os.getenv("VOLUME_MULTIPLIER", "1.50")
)


# =========================================================
# BINANCE SPOT
# =========================================================

BASE = "https://data-api.binance.vision"

FUTURES_BASE = "https://fapi.binance.com"

session = requests.Session()

session.headers["User-Agent"] = (
    "KriptoBot-4H-Spot/1.0"
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# =========================================================
# BINANCE API
# =========================================================

def api_get(path, params=None):

    response = session.get(
        BASE + path,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# BINANCE FUTURES FUNDING
# =========================================================

def get_funding_rate(symbol):

    try:

        response = session.get(
            FUTURES_BASE + "/fapi/v1/premiumIndex",
            params={
                "symbol": symbol
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        funding = float(
            data.get(
                "lastFundingRate",
                0
            )
        )

        return funding

    except Exception as error:

        logging.warning(
            "%s funding alınamadı: %s",
            symbol,
            error
        )

        return None


# =========================================================
# TELEGRAM
# =========================================================

def telegram_send(text):

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya "
            "TELEGRAM_CHAT_ID eksik."
        )

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    response = session.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=20
    )

    response.raise_for_status()


# =========================================================
# INDICATORS
# =========================================================

def ema(series, period):

    return series.ewm(
        span=period,
        adjust=False
    ).mean()


def rsi(series, period=14):

    delta = series.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

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

    rs = (
        avg_gain
        /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    return 100 - (
        100 / (1 + rs)
    )


# =========================================================
# KLINES
# =========================================================

def get_klines(
    symbol,
    limit=100
):

    data = api_get(
        "/api/v3/klines",
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

    df = pd.DataFrame(
        data,
        columns=columns
    )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume"
    ]

    for column in numeric_columns:

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

    now = pd.Timestamp.now(
        tz="UTC"
    )

    return df[
        df["close_time"] <= now
    ].copy()


# =========================================================
# SYMBOLS
# =========================================================

def get_symbols():

    info = api_get(
        "/api/v3/exchangeInfo"
    )

    result = []

    for symbol in info["symbols"]:

        name = symbol["symbol"]

        if (
            symbol.get("status")
            == "TRADING"

            and symbol.get("quoteAsset")
            == "USDT"

            and symbol.get(
                "isSpotTradingAllowed",
                True
            )
        ):

            # Kaldıraçlı tokenleri dışarıda bırak
            if any(
                name.endswith(x)
                for x in [
                    "UPUSDT",
                    "DOWNUSDT",
                    "BULLUSDT",
                    "BEARUSDT"
                ]
            ):

                continue

            result.append(name)

    return result


def get_top_symbols(
    all_symbols
):

    tickers = api_get(
        "/api/v3/ticker/24hr"
    )

    allowed = set(
        all_symbols
    )

    rows = []

    for ticker in tickers:

        symbol = ticker.get(
            "symbol"
        )

        if symbol not in allowed:
            continue

        try:

            quote_volume = float(
                ticker.get(
                    "quoteVolume",
                    0
                )
            )

        except Exception:

            continue

        rows.append(
            (
                symbol,
                quote_volume
            )
        )

    rows.sort(
        key=lambda x: x[1],
        reverse=True
    )

    return [
        symbol
        for symbol, volume
        in rows[:TOP_SYMBOLS]
    ]


# =========================================================
# BTC TREND FILTER
# =========================================================

def get_btc_filter():

    df = closed_candles(
        get_klines(
            "BTCUSDT",
            100
        )
    )

    if len(df) < 60:

        return {
            "long": False,
            "short": False
        }

    df["ema20"] = ema(
        df["close"],
        20
    )

    df["ema50"] = ema(
        df["close"],
        50
    )

    current = df.iloc[-1]

    return {

        "long":
            current["close"]
            > current["ema20"]

            and current["ema20"]
            >= current["ema50"],

        "short":
            current["close"]
            < current["ema20"]

            and current["ema20"]
            <= current["ema50"]
    }


# =========================================================
# COIN ANALYSIS
# =========================================================

def analyze(
    symbol,
    btc_filter
):

    df = closed_candles(
        get_klines(
            symbol,
            100
        )
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

    if pd.isna(
        current["rsi"]
    ):

        return None

    if pd.isna(
        current["volume_average"]
    ):

        return None

    volume_ratio = (
        current["volume"]
        /
        current["volume_average"]
    )

    volume_ok = (
        volume_ratio
        >= VOLUME_MULTIPLIER
    )


    # =====================================================
    # LONG
    # =====================================================

    long_rsi = (
        30 <= previous["rsi"] <= 42

        and current["rsi"]
        > previous["rsi"]

        and current["rsi"] >= 35
    )

    long_ema = (
        previous["close"]
        <= previous["ema20"]

        and current["close"]
        > current["ema20"]
    )

    long_trend = (
        current["ema20"]
        > current["ema50"]

        and current["close"]
        >= current["ema50"]
        * 0.995
    )

    resistance = (
        df["high"]
        .shift(1)
        .rolling(20)
        .max()
        .iloc[-1]
    )

    resistance_break = (
        current["close"]
        > resistance
    )

    long_score = sum([
        long_rsi,
        long_ema,
        volume_ok,
        long_trend,
        resistance_break
    ])


    # =====================================================
    # SHORT
    # =====================================================

    short_rsi = (
        58 <= previous["rsi"] <= 70

        and current["rsi"]
        < previous["rsi"]

        and current["rsi"] <= 65
    )

    short_ema = (
        previous["close"]
        >= previous["ema20"]

        and current["close"]
        < current["ema20"]
    )

    short_trend = (
        current["ema20"]
        < current["ema50"]

        and current["close"]
        <= current["ema50"]
        * 1.005
    )

    support = (
        df["low"]
        .shift(1)
        .rolling(20)
        .min()
        .iloc[-1]
    )

    support_break = (
        current["close"]
        < support
    )

    short_score = sum([
        short_rsi,
        short_ema,
        volume_ok,
        short_trend,
        support_break
    ])


    # =====================================================
    # DIRECTION
    # =====================================================

    direction = None

    score = 0

    level = None

    if (
        btc_filter["long"]

        and long_score >= MIN_SCORE

        and long_score > short_score
    ):

        direction = "LONG"

        score = long_score

        level = resistance

    elif (
        btc_filter["short"]

        and short_score >= MIN_SCORE

        and short_score > long_score
    ):

        direction = "SHORT"

        score = short_score

        level = support

    if direction is None:

        return None


    # =====================================================
    # FUNDING
    # =====================================================

    funding_rate = get_funding_rate(
        symbol
    )


    # =====================================================
    # SIGNAL
    # =====================================================

    return {

        "symbol": symbol,

        "direction": direction,

        "score": score,

        "price":
            float(
                current["close"]
            ),

        "rsi_previous":
            float(
                previous["rsi"]
            ),

        "rsi":
            float(
                current["rsi"]
            ),

        "volume_percent":
            (
                volume_ratio - 1
            ) * 100,

        "level":
            float(level),

        "funding_rate":
            funding_rate,

        "candle":
            current[
                "close_time"
            ].isoformat()
    }


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

def format_signal(
    signal
):

    is_long = (
        signal["direction"]
        == "LONG"
    )

    emoji = (
        "🟢"
        if is_long
        else "🔴"
    )

    arrow = (
        "↗️"
        if is_long
        else "↘️"
    )

    funding = signal.get(
        "funding_rate"
    )


    # =====================================================
    # FUNDING COMMENT
    # =====================================================

    if funding is None:

        funding_text = (
            "💵 Funding: "
            "Alınamadı ⚪"
        )

    else:

        funding_percent = (
            funding * 100
        )

        if funding_percent >= 0.05:

            funding_text = (
                f"💵 Funding: "
                f"+{funding_percent:.4f}% 🔥\n"
                f"⚠️ Longlar çok kalabalık"
            )

        elif funding_percent >= 0.01:

            funding_text = (
                f"💵 Funding: "
                f"+{funding_percent:.4f}% 🟡\n"
                f"ℹ️ Longlar ödeme yapıyor"
            )

        elif funding_percent <= -0.05:

            funding_text = (
                f"💵 Funding: "
                f"{funding_percent:.4f}% 🔥\n"
                f"⚠️ Shortlar çok kalabalık"
            )

        elif funding_percent <= -0.01:

            funding_text = (
                f"💵 Funding: "
                f"{funding_percent:.4f}% 🟡\n"
                f"ℹ️ Shortlar ödeme yapıyor"
            )

        else:

            funding_text = (
                f"💵 Funding: "
                f"{funding_percent:.4f}% ⚪\n"
                f"ℹ️ Normal"
            )


    level_name = (
        "Direnç"
        if is_long
        else "Destek"
    )


    # =====================================================
    # MESSAGE
    # =====================================================

    return (

        f"{emoji} "
        f"{signal['direction']} ADAYI\n\n"

        f"🪙 Coin: "
        f"{signal['symbol']}\n"

        f"💰 Fiyat: "
        f"{signal['price']:.8g}\n\n"

        f"📊 RSI: "
        f"{signal['rsi_previous']:.1f}"
        f" → "
        f"{signal['rsi']:.1f} "
        f"{arrow}\n"

        f"📈 EMA20: "
        f"{'ÜSTÜNE' if is_long else 'ALTINA'} "
        f"4H KAPANIŞ ✅\n"

        f"📈 EMA50 trend filtresi: "
        f"✅\n"

        f"🔊 Hacim: "
        f"+{signal['volume_percent']:.0f}% 🔥\n\n"

        f"{funding_text}\n\n"

        f"🎯 {level_name}: "
        f"{signal['level']:.8g}\n\n"

        f"📊 Skor: "
        f"{signal['score']}/5\n\n"

        f"⏱ Zaman dilimi: "
        f"4H\n\n"

        f"⚠️ SADECE ADAY SİNYALİ\n"
        f"Grafiği kontrol et.\n"
        f"İşlemi kendin değerlendir."
    )


# =========================================================
# SCAN
# =========================================================

def scan():

    logging.info(
        "Coin listesi alınıyor..."
    )

    all_symbols = get_symbols()

    logging.info(
        "Toplam Spot USDT coin: %d",
        len(all_symbols)
    )

    watchlist = get_top_symbols(
        all_symbols
    )

    logging.info(
        "En yüksek hacimli %d coin taranacak.",
        len(watchlist)
    )

    btc_filter = get_btc_filter()

    logging.info(
        "BTC trend filtresi: "
        "LONG=%s SHORT=%s",
        btc_filter["long"],
        btc_filter["short"]
    )

    signals = []

    for symbol in watchlist:

        if symbol == "BTCUSDT":

            continue

        try:

            signal = analyze(
                symbol,
                btc_filter
            )

            if signal:

                signals.append(
                    signal
                )

                logging.info(
                    "Sinyal bulundu: "
                    "%s %s %d/5",
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


    # =====================================================
    # SEND TELEGRAM
    # =====================================================

    if signals:

        signals.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        for signal in signals:

            try:

                telegram_send(
                    format_signal(
                        signal
                    )
                )

            except Exception as error:

                logging.error(
                    "Telegram gönderim "
                    "hatası: %s",
                    error
                )

    else:

        # Aday yoksa Telegram'a
        # HİÇBİR MESAJ GÖNDERİLMEZ.

        logging.info(
            "Aday bulunamadı. "
            "Telegram mesajı gönderilmeyecek."
        )


    logging.info(
        "Tarama tamamlandı. "
        "Sinyal sayısı: %d",
        len(signals)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if (
        not TELEGRAM_BOT_TOKEN
        or not TELEGRAM_CHAT_ID
    ):

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN veya "
            "TELEGRAM_CHAT_ID eksik."
        )

    logging.info(
        "Kripto Bot başladı."
    )

    scan()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
