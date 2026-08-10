import os
import time
import ccxt
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WHALE_THRESHOLD_USD = 50000  

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

def rsi_hesapla(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def marketleri_getir(market_type='spot'):
    """Binance üzerindeki AKTİF pariteleri getirir, delist olanları otomatik dışarıda bırakır"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        exchange.load_markets()
        semboller = []
        for symbol, market in exchange.markets.items():
            # Delist olmuş veya inaktif pariteleri 'active' filtresiyle doğrudan eliyoruz
            if market['quote'] == 'USDT' and market['active']:
                if "UP/" in symbol or "DOWN/" in symbol or "BUSD" in symbol or "EUR" in symbol:
                    continue
                if market_type == 'spot' and market['spot']: 
                    semboller.append((symbol, market))
                elif market_type == 'swap' and market['linear']: 
                    semboller.append((symbol, market))
        return semboller
    except: return []

def trend_ve_balina_analizi(symbol, market_info, timeframe='4h', market_type='spot'):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
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
            if buy_ratio > 55: balina_durum = "AL"
            elif sell_ratio > 55: balina_durum = "SAT"
            
        # DELIST RİSKİ (İzleme Etiketi) KONTROLÜ
        # Binance API verilerindeki koruma etiketlerini tarar
        risk_etiketi = ""
        info = market_info.get('info', {})
        permissions = info.get('permissions', [])
        
        # Eğer coinin izinlerinde TRADING_TRADITIONAL dışında kısıtlamalar veya risk ibareleri varsa işaretle
        if info.get('isMarginTradingAllowed') == False or "LEVERAGE" in permissions:
            risk_etiketi = "⚠️RİSK"

        if son_kapanis > son_ema50 and son_rsi < 45 and balina_durum == "AL":
            sinyal = f"⚡ AL {risk_etiketi}".strip()
            return [symbol.replace('/USDT', ''), "🟢YÜKSELEN", f"🟢{son_rsi:.0f}", f"🐳 %{buy_ratio:.0f}", sinyal]
        elif son_kapanis < son_ema50 and son_rsi > 55 and balina_durum == "SAT":
            sinyal = f"💥 SAT {risk_etiketi}".strip()
            return [symbol.replace('/USDT', ''), "🔴DÜŞEN", f"🔴{son_rsi:.0f}", f"🚨 %{sell_ratio:.0f}", sinyal]
        return None
    except: return None

def ana_butonlari_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🟢 TÜM SPOT PİYASAYI TARA", callback_data="tara_spot"),
               types.InlineKeyboardButton("🔴 TÜM VADELİ PİYASAYI TARA", callback_data="tara_vadeli"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(message.chat.id, "🤖 **Binance 4H Tüm Piyasa Tarayıcı (Delist Korumalı)**\nTaramayı başlatmak için butonları kullanın.\n_(Not: Tarama yaklaşık 1.5 dakika sürer)_", reply_markup=ana_butonlari_olustur(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    bot.answer_callback_query(call.id, text="Tüm piyasa taranıyor (Delist kontrolü aktif)...")
    market_tipi = 'spot' if call.data == 'tara_spot' else 'swap'
    gecici = bot.send_message(call.message.chat.id, f"🔄 Binance üzerindeki TÜM {market_tipi.upper()} pariteleri tek tek taranıyor... Lütfen bekleyin.")
    
    secilen_marketler = marketleri_getir(market_tipi)
    
    mesaj = f"📊 **TÜM PİYASA 4H TARAMA ({market_tipi.upper()})**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift      | Trend    | RSI  | Balina | Sinyal`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
    bulunan = 0
    
    for symbol, market_info in secilen_marketler:
        res = trend_ve_balina_analizi(symbol, market_info, timeframe='4h', market_type=market_tipi)
        if res:
            mesaj += f"`{res:<9} | {res:<8} | {res:<4} | {res:<6} | {res}`\n"
            bulunan += 1
            if bulunan >= 15:
                mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n⚠️ _Mesaj boyutu sınırından dolayı ilk 15 fırsat listelenmiştir._"
                break
        time.sleep(0.25)
        
    if bulunan == 0: mesaj += "ℹ️ _Şu anda kriterlere uyan aktif bir fırsat yok._\n"
    if bulunan < 15: mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
    
    bot.delete_message(call.message.chat.id, gecici.message_id)
    bot.send_message(call.message.chat.id, mesaj, reply_markup=ana_butonlari_olustur(), parse_mode="Markdown")

@app.route('/' + TELEGRAM_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        bot.set_webhook(url=render_url + '/' + TELEGRAM_TOKEN)
        return "Webhook Başarıyla Kuruldu!", 200
    return "Render URL bulunamadı.", 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
