import os
import time
import ccxt
import pandas as pd
import telebot
from telebot import types
from flask import Flask, request

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN (ÖRN: "123456:ABCdef...")
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"
WHALE_THRESHOLD_USD = 50000  

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

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
    except: return []

def trend_ve_balina_analizi(symbol, market_tipi):
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
        
        trend_str = "🟢AL" if son_kapanis > son_ema50 else "🔴SAT"
        
        # 🎯 RSI GÖSTERGE MANTIĞI 30 VE 70 SINIRLARINA GÖRE GÜNCELLENDİ
        if son_rsi <= 30:
            rsi_str = f"🟢{son_rsi:.0f}" # 30 altı aşırı ucuz (Alım bölgesi)
        elif son_rsi >= 70:
            rsi_str = f"🔴{son_rsi:.0f}" # 70 üstü aşırı şişmiş (Satış bölgesi)
        else:
            rsi_str = f"⚪{son_rsi:.0f}" # Güvenli/Nötr bölge
        
        trades = exchange.fetch_trades(symbol, limit=100)
        buy_whale_vol, sell_whale_vol, total_whale_vol = 0, 0, 0
        for trade in trades:
            usd_size = trade['price'] * trade['amount']
            if usd_size >= WHALE_THRESHOLD_USD:
                total_whale_vol += usd_size
                if trade['side'] == 'buy': buy_whale_vol += usd_size
                elif trade['side'] == 'sell': sell_whale_vol += usd_size
        
        balina_str = "⚪Sakin"
        if total_whale_vol > 0:
            buy_ratio = (buy_whale_vol / total_whale_vol) * 100
            sell_ratio = (sell_whale_vol / total_whale_vol) * 100
            if buy_ratio >= 50: balina_str = f"🐳%{buy_ratio:.0f}"
            elif sell_ratio >= 50: balina_str = f"🚨%{sell_ratio:.0f}"

        parite_temiz = symbol.replace('/USDT', '')
        return f"`{parite_temiz:<7} | {market_tipi:<5} | {rsi_str:<3} | {balina_str:<5} | {trend_str}`\n"
    except: return None

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 TÜM PİYASAYI ANLIK TARA", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(message.chat.id, "🤖 **Binance 4H Tüm Piyasa Durum Tarayıcı (RSI 30 Limitli)**\n\nButona bastığınızda tüm havuz taranır ve en aktif 30 paritenin RSI 30/70 uyumlu raporu listelenir.", reply_markup=tek_buton_olustur(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="RSI 30 odaklı tarama başlatıldı...")
        gecici = bot.send_message(call.message.chat.id, "🔄 Tüm Binance pariteleri taranıyor... Lütfen bekleyin.")
        
        tum_listeler = tum_marketleri_getir()
        mesaj = f"📊 **TÜM PİYASA DURUM RAPORU (4H)**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift    | Tip   | RSI | Balina | EMA50`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
        bulunan = 0
        
        for symbol, market_info, market_tipi in tum_listeler:
            res = trend_ve_balina_analizi(symbol, market_tipi)
            if res:
                mesaj += res
                bulunan += 1
                if bulunan >= 30:
                    break
            time.sleep(0.15)
            
        mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
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
