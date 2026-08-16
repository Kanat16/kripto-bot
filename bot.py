import os
import requests
import pandas as pd
import numpy as np

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
    "User-Agent": "KriptoBot-4H/3.0"
})


# ============================================================
# BINANCE API
# ============================================================

def api_get(url, params=None):
    r = session.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram bilgileri eksik.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        r = session.post(url, data=data, timeout=20)
        r.raise_for_status()
        print("Telegram mesajı gönderildi.")
        return True
    except Exception as e:
        print("Telegram hatası:", e)
        return False


# ============================================================
# COIN LISTESI
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

        if item["isSpotTradingAllowed"] is not True:
            continue

        symbol = item["symbol"]

        if symbol.endswith("USDT"):
            symbols.append(symbol)

    return symbols


# ============================================================
# HACIM SIRALAMASI
# ============================================================

def get_top_symbols(symbols):

    data = api_get(
        f"{BASE}/api/v3/ticker/24hr"
    )

    volume_map = {}

    allowed = set(symbols)

    for item in data:

        symbol = item["symbol"]

        if symbol not in allowed:
            continue

        try:
            volume_map[symbol] = float(item["quoteVolume"])
        except:
            pass

    sorted_symbols = sorted(
        volume_map,
        key=volume_map.get,
        reverse=True
    )

    return sorted_symbols[:TOP_SYMBOLS]


# ============================================================
# KLINE
# ============================================================

def get_klines(symbol, limit=150):

    data = api_get(
        f"{BASE}/api/v3/klines",
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

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:
        df[col] = pd.to_numeric(df[col])

    df["open_time"] = pd.to_datetime(
        df["open_time"],
        unit="ms"
    )

    return df


# ============================================================
# INDIKATORLER
# ============================================================

def calculate_indicators(df):

    # EMA
    df["ema20"] = df["close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=50,
        adjust=False
    ).mean()

    # RSI
    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["rsi"] = 100 - (
        100 / (1 + rs)
    )

    # MACD
    ema12 = df["close"].ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = df["close"].ewm(
        span=26,
        adjust=False
    ).mean()

    df["macd"] = ema12 - ema26

    df["macd_signal"] = df["macd"].ewm(
        span=9,
        adjust=False
    ).mean()

    # Ortalama hacim
    df["volume_avg"] = df["volume"].rolling(20).mean()

    return df


# ============================================================
# BTC TREND
# ============================================================

def get_btc_trend():

    df = get_klines("BTCUSDT", 100)
    df = calculate_indicators(df)

    # Son kapanmış mum
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
            data.get("lastFundingRate", 0)
        ) * 100

    except:
        return 0.0


# ============================================================
# COIN ANALIZI
# ============================================================

def analyze_symbol(symbol, btc_long, btc_short):

    try:

        df = get_klines(symbol)
        df = calculate_indicators(df)

        # Son tamamlanmış 4H mum
        last = df.iloc[-2]
        prev = df.iloc[-3]

        score_long = 0
        score_short = 0

        reasons_long = []
        reasons_short = []

        # ----------------------------------------------------
        # RSI
        # ----------------------------------------------------

        if 30 <= last["rsi"] <= 40:
            score_long += 1
            reasons_long.append("RSI 30-40 bölgesinde")

        if (
            prev["rsi"] < 40
            and
            last["rsi"] > prev["rsi"]
        ):
            score_long += 1
            reasons_long.append("RSI yukarı dönüyor")

        if last["rsi"] >= 60:
            score_short += 1
            reasons_short.append("RSI yüksek")

        if (
            prev["rsi"] > 60
            and
            last["rsi"] < prev["rsi"]
        ):
            score_short += 1
            reasons_short.append("RSI aşağı dönüyor")

        # ----------------------------------------------------
        # EMA20
        # ----------------------------------------------------

        if (
            prev["close"] <= prev["ema20"]
            and
            last["close"] > last["ema20"]
        ):
            score_long += 1
            reasons_long.append("EMA20 yukarı kırıldı")

        if (
            prev["close"] >= prev["ema20"]
            and
            last["close"] < last["ema20"]
        ):
            score_short += 1
            reasons_short.append("EMA20 aşağı kırıldı")

        # EMA trend
        if last["ema20"] > last["ema50"]:
            score_long += 1
            reasons_long.append("EMA20 > EMA50")

        if last["ema20"] < last["ema50"]:
            score_short += 1
            reasons_short.append("EMA20 < EMA50")

        # ----------------------------------------------------
        # MACD
        # ----------------------------------------------------

        if (
            last["macd"] > last["macd_signal"]
        ):
            score_long += 1
            reasons_long.append("MACD pozitif")

        if (
            last["macd"] < last["macd_signal"]
        ):
            score_short += 1
            reasons_short.append("MACD negatif")

        # ----------------------------------------------------
        # HACIM
        # ----------------------------------------------------

        volume_ok = (
            last["volume"]
            >=
            last["volume_avg"] * VOLUME_MULTIPLIER
        )

        if volume_ok:
            score_long += 1
            score_short += 1

            reasons_long.append("Hacim güçlü")
            reasons_short.append("Hacim güçlü")

        # ----------------------------------------------------
        # BTC TREND FILTRESI
        # ----------------------------------------------------

        if btc_long:
            score_long += 1
            reasons_long.append("BTC trend LONG")

        if btc_short:
            score_short += 1
            reasons_short.append("BTC trend SHORT")

        # ----------------------------------------------------
        # SONUÇ
        # ----------------------------------------------------

        funding = get_funding_rate(symbol)

        result = {
            "symbol": symbol,
            "price": float(last["close"]),
            "rsi": float(last["rsi"]),
            "score_long": score_long,
            "score_short": score_short,
            "funding": funding,
            "candle_time": last["open_time"],
            "long_reasons": reasons_long,
            "short_reasons": reasons_short
        }

        return result

    except Exception as e:

        print(
            f"{symbol} analiz hatası: {e}"
        )

        return None


# ============================================================
# TELEGRAM MESAJI
# ============================================================

def format_signal(item, direction):

    symbol = item["symbol"]
    price = item["price"]
    rsi = item["rsi"]
    funding = item["funding"]
    candle_time = item["candle_time"]

    if direction == "LONG":

        score = item["score_long"]
        reasons = item["long_reasons"]

        title = "🟢 GÜÇLÜ LONG ADAYI"

    else:

        score = item["score_short"]
        reasons = item["short_reasons"]

        title = "🔴 GÜÇLÜ SHORT ADAYI"

    if funding >= 0.05:
        funding_text = "⚠️ Longlar çok kalabalık"
    elif funding <= -0.05:
        funding_text = "⚠️ Shortlar çok kalabalık"
    else:
        funding_text = "⚪ Funding dengeli"

    message = f"""
<b>{title}</b>

<b>Coin:</b> {symbol}
<b>Skor:</b> {score}
<b>Fiyat:</b> {price:.8f}
<b>RSI:</b> {rsi:.2f}

<b>Funding:</b> {funding:.4f}%
{funding_text}

<b>Nedenler:</b>
"""

    for reason in reasons:
        message += f"• {reason}\n"

    message += f"""
<b>4H Mum:</b> {candle_time.strftime("%Y-%m-%d %H:%M")}

⚠️ Bu bir işlem emri değil, teknik tarama sinyalidir.
"""

    return message


# ============================================================
# ANA PROGRAM
# ============================================================

def main():

    print("=" * 60)
    print("4H KRIPTO BOT BASLIYOR")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN:
        print("UYARI: TELEGRAM_BOT_TOKEN bulunamadı.")

    if not TELEGRAM_CHAT_ID:
        print("UYARI: TELEGRAM_CHAT_ID bulunamadı.")

    print("Coin listesi alınıyor...")

    symbols = get_symbols()

    print(
        "Toplam Spot USDT coin:",
        len(symbols)
    )

    top_symbols = get_top_symbols(symbols)

    print(
        f"En yüksek hacimli {len(top_symbols)} coin taranacak."
    )

    btc_long, btc_short = get_btc_trend()

    print(
        f"BTC 4H trend: LONG={btc_long} SHORT={btc_short}"
    )

    long_candidates = []
    short_candidates = []

    for index, symbol in enumerate(
        top_symbols,
        start=1
    ):

        print(
            f"[{index}/{len(top_symbols)}] {symbol}"
        )

        result = analyze_symbol(
            symbol,
            btc_long,
            btc_short
        )

        if not result:
            continue

        if result["score_long"] >= MIN_SCORE:

            long_candidates.append(result)

        if result["score_short"] >= MIN_SCORE:

            short_candidates.append(result)

    # --------------------------------------------------------
    # SIRALAMA
    # --------------------------------------------------------

    long_candidates.sort(
        key=lambda x: x["score_long"],
        reverse=True
    )

    short_candidates.sort(
        key=lambda x: x["score_short"],
        reverse=True
    )

    print()
    print("LONG ADAYLARI:", len(long_candidates))

    for item in long_candidates:

        print(
            item["symbol"],
            "SKOR=",
            item["score_long"],
            "RSI=",
            round(item["rsi"], 2)
        )

    print()
    print("SHORT ADAYLARI:", len(short_candidates))

    for item in short_candidates:

        print(
            item["symbol"],
            "SKOR=",
            item["score_short"],
            "RSI=",
            round(item["rsi"], 2)
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    # Aynı 4H mum içinde sürekli mesaj spamlamamak için
    # sadece kapanmış 4H mum üzerinde sinyal gönderiyoruz.
    #
    # 30 dakikada bir tarama devam eder.
    # Ancak sinyal sadece yeni kapanmış 4H mumda oluştuğunda
  

now_utc = datetime.now(timezone.utc)

# 4H mum kapanış saatleri: 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC
# Sadece bu zamanlarda Telegram sinyali gönder.
send_alerts = (
    now_utc.minute < 15
    and now_utc.hour % 4 == 0
)

print(
    f"Telegram bildirim zamanı: {send_alerts} | "
    f"UTC: {now_utc.strftime('%Y-%m-%d %H:%M')}"
)



    messages_sent = 0

    if send_alerts:
       for item in long_candidates[:5]:

        # BTC SHORT ise LONG sinyalini engelle
        if btc_short and not btc_long:
            continue

        message = format_signal(
            item,
            "LONG"
        )

        if telegram_send(message):
            messages_sent += 1

    if send_alerts:
       for item in short_candidates[:5]:

        # BTC LONG ise SHORT sinyalini engelle
        if btc_long and not btc_short:
            continue

        message = format_signal(
            item,
            "SHORT"
        )

        if telegram_send(message):
            messages_sent += 1

    print()
    print(
        "Telegram gönderilen sinyal:",
        messages_sent
    )

    print()
    print("TARAMA TAMAMLANDI.")


if __name__ == "__main__":
    main()
