import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# ============================================================
# AYARLAR
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

TOP_SYMBOLS = int(os.getenv("TOP_SYMBOLS", "100"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "4"))
VOLUME_MULTIPLIER = float(os.getenv("VOLUME_MULTIPLIER", "1.50"))

BASE = "https://data-api.binance.vision"
FUTURES_BASE = "https://fapi.binance.com"

session = requests.Session()
session.headers.update({
    "User-Agent": "KriptoBot-1H/5.0"
})


# ============================================================
# BINANCE
# ============================================================

def api_get(url, params=None):

    response = session.get(
        url,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:

        print("Telegram bilgileri eksik.")

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        response = session.post(
            url,
            data=data,
            timeout=20
        )

        response.raise_for_status()

        print("Telegram mesajı gönderildi.")

        return True

    except Exception as e:

        print("Telegram hatası:", e)

        return False


# ============================================================
# SPOT COINLER
# ============================================================

def get_symbols():

    data = api_get(
        f"{BASE}/api/v3/exchangeInfo"
    )

    symbols = []

    for item in data["symbols"]:

        if item["status"] != "TRADING":
            continue

        if item["quoteAsset"] != "USDT":
            continue

        if not item.get(
            "isSpotTradingAllowed",
            False
        ):
            continue

        symbols.append(item["symbol"])

    return symbols


# ============================================================
# EN YÜKSEK HACİMLİ COINLER
# ============================================================

def get_top_symbols(symbols):

    data = api_get(
        f"{BASE}/api/v3/ticker/24hr"
    )

    allowed = set(symbols)

    volumes = {}

    for item in data:

        symbol = item["symbol"]

        if symbol not in allowed:
            continue

        try:

            volumes[symbol] = float(
                item["quoteVolume"]
            )

        except (TypeError, ValueError):

            continue

    sorted_symbols = sorted(
        volumes,
        key=volumes.get,
        reverse=True
    )

    return sorted_symbols[:TOP_SYMBOLS]


# ============================================================
# 1H KLINE
# ============================================================

def get_klines(
    symbol,
    limit=150
):

    data = api_get(
        f"{BASE}/api/v3/klines",
        {
            "symbol": symbol,
            "interval": "1h",
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
        "volume"
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        unit="ms"
    )

    return df


# ============================================================
# İNDİKATÖRLER
# ============================================================

def calculate_indicators(df):

    # --------------------------------------------------------
    # EMA20
    # --------------------------------------------------------

    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # EMA50
    # --------------------------------------------------------

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # RSI14
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.rolling(
        14
    ).mean()

    avg_loss = loss.rolling(
        14
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = (
        ema12 - ema26
    )

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    # --------------------------------------------------------
    # HACİM ORTALAMASI
    # --------------------------------------------------------

    df["volume_avg"] = df["volume"].rolling(
        20
    ).mean()

    return df


# ============================================================
# BTC TREND
# ============================================================

def get_btc_trend():

    df = get_klines(
        "BTCUSDT",
        100
    )

    df = calculate_indicators(df)

    # SON KAPANMIŞ 1H MUM
    last = df.iloc[-2]

    long_trend = (
        last["close"] > last["ema20"]
        and
        last["ema20"] > last["ema50"]
    )

    short_trend = (
        last["close"] < last["ema20"]
        and
        last["ema20"] < last["ema50"]
    )

    return long_trend, short_trend


# ============================================================
# FUNDING RATE
# ============================================================

def get_funding_rate(symbol):

    try:

        data = api_get(
            f"{FUTURES_BASE}/fapi/v1/premiumIndex",
            {
                "symbol": symbol
            }
        )

        return float(
            data.get(
                "lastFundingRate",
                0
            )
        ) * 100

    except Exception:

        return 0.0


# ============================================================
# COIN ANALİZİ
# ============================================================

def analyze_symbol(
    symbol,
    btc_long,
    btc_short
):

    try:

        df = get_klines(symbol)

        df = calculate_indicators(df)

        # ----------------------------------------------------
        # SADECE KAPANMIŞ MUM
        # ----------------------------------------------------

        last = df.iloc[-2]

        previous = df.iloc[-3]

        long_score = 0

        short_score = 0

        long_reasons = []

        short_reasons = []

        # ----------------------------------------------------
        # RSI LONG
        # ----------------------------------------------------

        if 30 <= last["rsi"] <= 40:

            long_score += 1

            long_reasons.append(
                "RSI 30-40 bölgesinde"
            )

        if (
            previous["rsi"] < 40
            and
            last["rsi"] > previous["rsi"]
        ):

            long_score += 1

            long_reasons.append(
                "RSI yukarı dönüyor"
            )

        # ----------------------------------------------------
        # RSI SHORT
        # ----------------------------------------------------

        if last["rsi"] >= 60:

            short_score += 1

            short_reasons.append(
                "RSI yüksek"
            )

        if (
            previous["rsi"] > 60
            and
            last["rsi"] < previous["rsi"]
        ):

            short_score += 1

            short_reasons.append(
                "RSI aşağı dönüyor"
            )

        # ----------------------------------------------------
        # EMA20 KIRILIMI LONG
        # ----------------------------------------------------

        if (
            previous["close"] <= previous["ema20"]
            and
            last["close"] > last["ema20"]
        ):

            long_score += 1

            long_reasons.append(
                "EMA20 yukarı kırıldı"
            )

        # ----------------------------------------------------
        # EMA20 KIRILIMI SHORT
        # ----------------------------------------------------

        if (
            previous["close"] >= previous["ema20"]
            and
            last["close"] < last["ema20"]
        ):

            short_score += 1

            short_reasons.append(
                "EMA20 aşağı kırıldı"
            )

        # ----------------------------------------------------
        # EMA20 / EMA50 TREND
        # ----------------------------------------------------

        if last["ema20"] > last["ema50"]:

            long_score += 1

            long_reasons.append(
                "EMA20 > EMA50"
            )

        if last["ema20"] < last["ema50"]:

            short_score += 1

            short_reasons.append(
                "EMA20 < EMA50"
            )

        # ----------------------------------------------------
        # MACD LONG
        # ----------------------------------------------------

        if last["macd"] > last["macd_signal"]:

            long_score += 1

            long_reasons.append(
                "MACD pozitif"
            )

        # ----------------------------------------------------
        # MACD SHORT
        # ----------------------------------------------------

        if last["macd"] < last["macd_signal"]:

            short_score += 1

            short_reasons.append(
                "MACD negatif"
            )

        # ----------------------------------------------------
        # HACİM
        # ----------------------------------------------------

        volume_strong = (
            last["volume"]
            >=
            last["volume_avg"] * VOLUME_MULTIPLIER
        )

        if volume_strong:

            # Mum yönüne göre hacim puanı
            if last["close"] > last["open"]:

                long_score += 1

                long_reasons.append(
                    "Yükseliş hacmi güçlü"
                )

            elif last["close"] < last["open"]:

                short_score += 1

                short_reasons.append(
                    "Düşüş hacmi güçlü"
                )

        # ----------------------------------------------------
        # BTC TREND FİLTRESİ
        # ----------------------------------------------------

        if btc_long:

            long_score += 1

            long_reasons.append(
                "BTC trend LONG"
            )

        if btc_short:

            short_score += 1

            short_reasons.append(
                "BTC trend SHORT"
            )

        # ----------------------------------------------------
        # FUNDING
        # ----------------------------------------------------

        funding = get_funding_rate(symbol)

        return {
            "symbol": symbol,
            "price": float(last["close"]),
            "rsi": float(last["rsi"]),
            "long_score": long_score,
            "short_score": short_score,
            "funding": funding,
            "candle_time": last["open_time"],
            "long_reasons": long_reasons,
            "short_reasons": short_reasons
        }

    except Exception as e:

        print(
            f"{symbol} analiz hatası: {e}"
        )

        return None


# ============================================================
# TELEGRAM MESAJI
# ============================================================

def format_signal(
    item,
    direction
):

    if direction == "LONG":

        title = "🟢 GÜÇLÜ LONG ADAYI"

        score = item["long_score"]

        reasons = item["long_reasons"]

    else:

        title = "🔴 GÜÇLÜ SHORT ADAYI"

        score = item["short_score"]

        reasons = item["short_reasons"]

    funding = item["funding"]

    if funding >= 0.05:

        funding_text = (
            "⚠️ Longlar çok kalabalık"
        )

    elif funding <= -0.05:

        funding_text = (
            "⚠️ Shortlar çok kalabalık"
        )

    else:

        funding_text = (
            "⚪ Funding dengeli"
        )

    message = (
        f"<b>{title}</b>\n\n"
        f"<b>Coin:</b> {item['symbol']}\n"
        f"<b>Skor:</b> {score}\n"
        f"<b>Fiyat:</b> {item['price']:.8f}\n"
        f"<b>RSI:</b> {item['rsi']:.2f}\n\n"
        f"<b>Funding:</b> {funding:.4f}%\n"
        f"{funding_text}\n\n"
        f"<b>Nedenler:</b>\n"
    )

    for reason in reasons:

        message += (
            f"• {reason}\n"
        )

    message += (
        f"\n<b>1H Mum:</b> "
        f"{item['candle_time'].strftime('%Y-%m-%d %H:%M')}\n\n"
        "⚠️ Bu bir işlem emri değil, "
        "teknik tarama sinyalidir."
    )

    return message


# ============================================================
# 1H BİLDİRİM PENCERESİ
# ============================================================

def is_1h_notification_window():

    now = datetime.now(
        timezone.utc
    )

    # Saat başındaki ilk 30 dakika
    #
    # Örnek:
    # 12:00 -> bildirim
    # 12:30 -> bildirim yok
    # 13:00 -> bildirim
    #

    return now.minute < 30


# ============================================================
# ANA PROGRAM
# ============================================================

def main():

    print("=" * 60)

    print(
        "1H KRIPTO BOT BASLIYOR"
    )

    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN:

        print(
            "UYARI: TELEGRAM_BOT_TOKEN bulunamadı."
        )

    if not TELEGRAM_CHAT_ID:

        print(
            "UYARI: TELEGRAM_CHAT_ID bulunamadı."
        )

    print(
        "Coin listesi alınıyor..."
    )

    symbols = get_symbols()

    print(
        "Toplam Spot USDT coin:",
        len(symbols)
    )

    top_symbols = get_top_symbols(
        symbols
    )

    print(
        f"En yüksek hacimli "
        f"{len(top_symbols)} coin taranacak."
    )

    # --------------------------------------------------------
    # BTC TREND
    # --------------------------------------------------------

    btc_long, btc_short = get_btc_trend()

    print(
        f"BTC 1H trend: "
        f"LONG={btc_long} "
        f"SHORT={btc_short}"
    )

    long_candidates = []

    short_candidates = []

    # --------------------------------------------------------
    # TARAMA
    # --------------------------------------------------------

    for index, symbol in enumerate(
        top_symbols,
        start=1
    ):

        print(
            f"[{index}/{len(top_symbols)}] "
            f"{symbol}"
        )

        result = analyze_symbol(
            symbol,
            btc_long,
            btc_short
        )

        if result is None:

            continue

        if (
            result["long_score"]
            >= MIN_SCORE
        ):

            long_candidates.append(
                result
            )

        if (
            result["short_score"]
            >= MIN_SCORE
        ):

            short_candidates.append(
                result
            )

    # --------------------------------------------------------
    # SIRALAMA
    # --------------------------------------------------------

    long_candidates.sort(
        key=lambda x: x["long_score"],
        reverse=True
    )

    short_candidates.sort(
        key=lambda x: x["short_score"],
        reverse=True
    )

    print()

    print(
        "LONG ADAYLARI:",
        len(long_candidates)
    )

    for item in long_candidates:

        print(
            f"{item['symbol']:12} "
            f"SKOR={item['long_score']} "
            f"RSI={item['rsi']:.2f}"
        )

    print()

    print(
        "SHORT ADAYLARI:",
        len(short_candidates)
    )

    for item in short_candidates:

        print(
            f"{item['symbol']:12} "
            f"SKOR={item['short_score']} "
            f"RSI={item['rsi']:.2f}"
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    notification_window = (
        is_1h_notification_window()
    )

    print()

    print(
        "1H bildirim penceresi:",
        notification_window
    )

    messages_sent = 0

    if notification_window:

        # ----------------------------------------------------
        # LONG
        # ----------------------------------------------------

        if not btc_short or btc_long:

            for item in long_candidates[:5]:

                message = format_signal(
                    item,
                    "LONG"
                )

                if telegram_send(
                    message
                ):

                    messages_sent += 1

        # ----------------------------------------------------
        # SHORT
        # ----------------------------------------------------

        if not btc_long or btc_short:

            for item in short_candidates[:5]:

                message = format_signal(
                    item,
                    "SHORT"
                )

                if telegram_send(
                    message
                ):

                    messages_sent += 1

    else:

        print(
            "Saat başı bildirim penceresi "
            "değil. Telegram mesajı "
            "gönderilmeyecek."
        )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

    print()

    print(
        "Telegram gönderilen sinyal:",
        messages_sent
    )

    print()

    print(
        "1H TARAMA TAMAMLANDI."
    )


if __name__ == "__main__":

    main()
