import os
import time
import ccxt
import pandas as pd
import telebot

# ⚠️ GEREKLİ TANIMLAMALARI YAPIN
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
MY_CHAT_ID = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"
WHALE_THRESHOLD_USD = 50000  

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def rsi_hesapla(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def tum_marketleri_getir():
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        exchange.load_markets()
        pariteler = []
        for symbol, market in exchange.markets.items():
            if market['quote'] == 'USDT' and market['active']:
                if "UP/" in symbol or "DOWN/" in symbol or "BUSD" in symbol or "EUR" in symbol:
                    continue
                if market['spot']:
                    pariteler.append((symbol, market, 'SPOT'))
                elif market['linear']:
                    pariteler.append((symbol, market, 'VADELİ'))
        return pariteler
    except:
        return []

def trend_ve_balina_analizi(symbol, market_info, market_tipi):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        # 🎯 Başarı oranı en yüksek makro periyot: 4 Saatlik (4h)
        ohlcv = exchange.fetch_ohlcv(symbol, '4h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if len(df) < 55: return None
        
        df['RSI'] = rsi_hesapla(df['close'], period=14)
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        son_rsi = df['RSI'].iloc[-1]
        son_kapanis = df['close'].iloc[-1]
        son_ema50 = df['EMA50'].iloc[-1]
        
        if pd.isna(son_rsi) or pd.isna(son_ema50): return None
        
        trades = exchange.fetch_trades(symbol, limit=100)
        buy_whale_vol, sell_whale_vol, total_whale_vol = 0, 0, 0
        for trade in trades:
            usd_size = trade['price'] * trade['amount']
            if usd_size >= WHALE_THRESHOLD_USD:
                total_whale_vol += usd_size
                if trade['side'] == 'buy': buy_whale_vol += usd_size
                elif trade['side'] == 'sell': sell_whale_vol += usd_size
        
        balina_durum = "NÖTR"
        buy_ratio, sell_ratio = 0, 0
        if total_whale_vol > 0:
            buy_ratio = (buy_whale_vol / total_whale_vol) * 100
            sell_ratio = (sell_whale_vol / total_whale_vol) * 100
            if buy_ratio >= 50: balina_durum = "AL"
            elif sell_ratio >= 50: balina_durum = "SAT"
            
        risk_etiketi = ""
        info = market_info.get('info', {})
        permissions = info.get('permissions', [])
        if info.get('isMarginTradingAllowed') == False or "LEVERAGE" in permissions:
            risk_etiketi = "⚠️R"

        parite_temiz = symbol.replace('/USDT', '')
        
        # 4H Grafiklerde güvenli ama sinyal yakalayacak esnek RSI sınırları (50 altı al, 50 üstü sat)
        if son_kapanis > son_ema50 and son_rsi < 50 and balina_durum == "AL":
            return f"`{parite_temiz:<7} | {market_tipi:<5} | 🟢{son_rsi:.0f} | 🐳%{buy_ratio:.0f} | ⚡AL {risk_etiketi}`\n".strip() + "\n"
        elif son_kapanis < son_ema50 and son_rsi > 50 and balina_durum == "SAT":
            return f"`{parite_temiz:<7} | {market_tipi:<5} | 🔴{son_rsi:.0f} | 🚨%{sell_ratio:.0f} | 💥SAT {risk_etiketi}`\n".strip() + "\n"
        return None
    except:
        return None

def otomatik_tarama_gorevi():
    print("⏰ 4 Saatlik periyodik makro tarama başlatıldı...")
    tum_listeler = tum_marketleri_getir()
    
    mesaj = f"🚨 **4H MAKRO PİYASA TARAMASI (GÜVENLİ MOD)**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift    | Tip   | RSI | Balina | Sinyal`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
    bulunan = 0
    
    for symbol, market_info, market_tipi in tum_listeler:
        res = trend_ve_balina_analizi(symbol, market_info, market_tipi)
        if res:
            mesaj += res
            bulunan += 1
            if bulunan >= 15:
                mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n⚠️ _Sınır nedeniyle ilk 15 güçlü fırsat listelenmiştir._"
                break
        time.sleep(0.20)
        
    if bulunan > 0:
        if bulunan < 15:
            mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
        try:
            bot.send_message(MY_CHAT_ID, mesaj, parse_mode="Markdown")
            print("🟢 4H Makro fırsatları başarıyla Telegram'a gönderildi.")
        except Exception as e:
            print(f"Mesaj gönderme hatası: {e}")
    else:
        print("⚪ Bu periyotta makro kriterlere uyan güvenli coin bulunamadı, sessiz geçiliyor.")

if __name__ == "__main__":
    print("🚀 4 Saatlik (4H) Otomatik Makro Tarayıcı Başlatıldı...")
    
    # Sunucu her açıldığında veya güncellendiğinde hemen ilk taramayı yapar
    otomatik_tarama_gorevi()
    
    # 4 Saatlik kusursuz döngü (4 saat = 14400 saniye)
    while True:
        print("💤 Bir sonraki makro tarama için 4 saatlik bekleme moduna girildi...")
        time.sleep(14400)
