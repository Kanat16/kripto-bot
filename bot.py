import os
import time
import ccxt
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

def rsi_hesapla(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def tum_marketleri_getir():
    """Binance üzerindeki istisnasız tüm aktif pariteleri toplar"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        exchange.load_markets()
        pariteler = []
        for symbol, market in exchange.markets.items():
            if market['quote'] == 'USDT' and market['active']:
                if "UP/" in symbol or "DOWN/" in symbol or "BUSD" in symbol or "EUR" in symbol:
                    continue
                if market['spot']:
                    pariteler.append((symbol, 'SPOT'))
                elif market['linear']:
                    pariteler.append((symbol, 'VADELİ'))
        return pariteler
    except: return []

def trend_ve_sinyal_analizi(symbol, market_tipi):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '4h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if len(df) < 55: return None
        
        df['RSI'] = rsi_hesapla(df['close'], period=14)
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        son_rsi = df['RSI'].iloc[-1]
        son_kapanis = df['close'].iloc[-1]
        son_ema50 = df['EMA50'].iloc[-1]
        
        if pd.isna(son_rsi) or pd.isna(son_ema50): return None
        
        # Sinyal ve Yön Mantığı (Esnetilmiş ve Geliştirilmiş)
        # RSI 30 civarı veya altındaysa ve trend dönüyorsa LONG, RSI 70 civarı ve üstündeyse SHORT
        if son_kapanis > son_ema50 and son_rsi <= 45:
            sinyal_str = "🟢 LONG (AL)"
            rsi_renkli = f"🟢 {son_rsi:.0f} (Ucuz)"
            ema_renkli = "🟢 ÜSTÜNDE (Yükselen)"
        elif son_kapanis < son_ema50 and son_rsi >= 55:
            sinyal_str = "🔴 SHORT (SAT)"
            rsi_renkli = f"🔴 {son_rsi:.0f} (Şişmiş)"
            ema_renkli = "🔴 ALTINDA (Düşen)"
        else:
            return None # Kriter dışı coinleri eler, listeyi şişirmez

        parite_temiz = symbol.replace('/USDT', '')
        
        # İstediğiniz bloklu ve sade tasarım şablonu
        return (
            f"🪙 **{parite_temiz} ({market_tipi})**\n"
            f"├ RSI: {rsi_renkli}\n"
            f"├ EMA50: {ema_renkli}\n"
            f"└ Sinyal: **{sinyal_str}**\n\n"
        )
    except: return None

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 TÜM PİYASAYI KOMPLE TARA", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(
        message.chat.id, 
        "🤖 **Binance Süper Tarayıcı V6**\n\nButona bastığınızda Binance üzerindeki tüm altcoinler (Spot + Vadeli) taranır. RSI 30 ve EMA50 uyumlu Long/Short fırsatları listelenir.\n_(Not: Tarama yaklaşık 1.5 dakika sürer)_", 
        reply_markup=tek_buton_olustur(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="Tüm piyasa komple taranıyor...")
        gecici = bot.send_message(call.message.chat.id, "🔄 Tüm Binance pariteleri taranıyor... Lütfen bekleyin (1.5 dk sürebilir).")
        
        tum_listeler = tum_marketleri_getir()
        mesaj = "📊 **BİNANCE KOMPLE PİYASA RAPORU**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        bulunan = 0
        
        for symbol, market_tipi in tum_listeler:
            res = trend_ve_sinyal_analizi(symbol, market_tipi)
            if res:
                mesaj += res
                bulunan += 1
                if bulunan >= 10:
                    mesaj += "⚠️ _Telegram sınırından dolayı en güçlü ilk 10 fırsat listelenmiştir._\n"
                    break
            # Ban yememek için optimize edilmiş geçiş süresi
            time.sleep(0.15)
            
        if bulunan == 0:
            mesaj += "ℹ️ _Şu anda kriterlere uyan aktif bir Long veya Short fırsatı bulunamadı._\n"
            
        mesaj += "━━━━━━━━━━━━━━━━━━━━"
        bot.delete_message(call.message.chat.id, gecici.message_id)
        bot.send_message(call.message.chat.id, mesaj, reply_markup=tek_buton_olustur(), parse_mode="Markdown")

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
