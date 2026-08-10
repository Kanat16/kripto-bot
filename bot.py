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
    """Binance üzerindeki istisnasız tüm aktif spot ve vadeli USDT paritelerini toplar"""
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        exchange.load_markets()
        pariteler = []
        for symbol, market in exchange.markets.items():
            if market['quote'] == 'USDT' and market['active']:
                # Karmaşayı önlemek için kaldıraçlı tokenları ve stabil pariteleri eliyoruz
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
            if buy_ratio > 55: balina_durum = "AL"
            elif sell_ratio > 55: balina_durum = "SAT"
            
        risk_etiketi = ""
        info = market_info.get('info', {})
        permissions = info.get('permissions', [])
        if info.get('isMarginTradingAllowed') == False or "LEVERAGE" in permissions:
            risk_etiketi = "⚠️R"

        parite_temiz = symbol.replace('/USDT', '')
        if son_kapanis > son_ema50 and son_rsi < 45 and balina_durum == "AL":
            return f"`{parite_temiz:<7} | {market_tipi:<5} | 🟢{son_rsi:.0f} | 🐳%{buy_ratio:.0f} | ⚡AL {risk_etiketi}`\n".strip() + "\n"
        elif son_kapanis < son_ema50 and son_rsi > 55 and balina_durum == "SAT":
            return f"`{parite_temiz:<7} | {market_tipi:<5} | 🔴{son_rsi:.0f} | 🚨%{sell_ratio:.0f} | 💥SAT {risk_etiketi}`\n".strip() + "\n"
        return None
    except:
        return None

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 TÜM PİYASAYI TEK TIKLA TARA", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(
        message.chat.id, 
        "🤖 **Binance 4H Süper Tarayıcı V2**\n\nTek butonla hem Spot hem Vadeli tüm altcoin piyasasını taratabilirsiniz.\n_(Not: Dev tarama yaklaşık 2 dakika sürer)_", 
        reply_markup=tek_buton_olustur(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="Dev tarama motoru çalıştırıldı (2 dk sürebilir)...")
        gecici = bot.send_message(call.message.chat.id, "🔄 Binance üzerindeki istisnasız TÜM Spot ve Vadeli pariteler taranıyor... Lütfen analiz tablosunu bekleyin.")
        
        tum_listeler = tum_marketleri_getir()
        
        mesaj = f"📊 **TÜM PİYASA SÜPER TARAMA (4H)**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift    | Tip   | RSI | Balina | Sinyal`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
        bulunan = 0
        
        for symbol, market_info, market_tipi in tum_listeler:
            res = trend_ve_balina_analizi(symbol, market_info, market_tipi)
            if res:
                mesaj += res
                bulunan += 1
                # Telegram mesaj uzunluğu sınırına takılmamak için maksimum 15 güçlü fırsatı listeliyoruz
                if bulunan >= 15:
                    mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n⚠️ _Sınır nedeniyle ilk 15 güçlü fırsat listelenmiştir._"
                    break
            # Sunucu güvenliği için her coinde 0.20 saniye bekleme
            time.sleep(0.20)
            
        if bulunan == 0: 
            mesaj += "ℹ️ _Şu anda kriterlere uyan aktif bir fırsat yok._\n"
        if bulunan < 15: 
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
