import os
import time
import telebot
from telebot import types
from flask import Flask, request
from tradingview_ta import TA_Handler, Interval, Exchange

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 KRİPTO SİNYAL BULUCUYU ÇALIŞTIR", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(
        message.chat.id, 
        "🤖 **Binance 4H Kripto Sinyal Bulucu (TradingView Altyapılı)**\n\n429 Hız engeli tamamen aşıldı! Butona bastığınızda saniyeler içinde sinyaller güvenli modda listelenir.", 
        reply_markup=tek_buton_olustur(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="TradingView sunucularından veriler güvenli modda taranıyor...")
        gecici = bot.send_message(call.message.chat.id, "🔄 Sinyal bulucu çalıştırıldı... Lütfen bekleyin (Güvenli geçiş devrede).")
        
        mesaj = "📊 **BİNANCE 4H KRİPTO SİNYAL RAPORU**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Sizin takipçinizdeki en aktif ve en çok sinyal üreten coinler en başa alındı
        pariteler = ['XLMUSDT', 'STXUSDT', 'FETUSDT', 'BONKUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'AVAXUSDT', 'DOGEUSDT', 'SUIUSDT']
        bulunan = 0
        
        try:
            for symbol in pariteler:
                try:
                    # TradingView sunucularından anlık indikatör analizlerini çekiyoruz
                    handler = TA_Handler(
                        symbol=symbol,
                        screener="crypto",
                        exchange="BINANCE",
                        interval=Interval.INTERVAL_4_HOURS
                    )
                    analysis = handler.get_analysis()
                    
                    rsi = analysis.indicators.get("RSI")
                    close = analysis.indicators.get("close")
                    ema50 = analysis.indicators.get("EMA50")
                    
                    if rsi is None or close is None or ema50 is None:
                        continue
                    
                    # Filtrenize göre durum renklendirmesi
                    if rsi <= 35:
                        rsi_str = f"🟢 {rsi:.1f} (Ucuz)"
                        sinyal = "🟢 LONG (AL)"
                        ema_str = "🟢 ÜSTÜNDE (Yükselen)" if close > ema50 else "🔴 ALTINDA (Düşen)"
                    elif rsi >= 65:
                        rsi_str = f"🔴 {rsi:.1f} (Şişmiş)"
                        sinyal = "🔴 SHORT (SAT)"
                        ema_str = "🟢 ÜSTÜNDE (Yükselen)" if close > ema50 else "🔴 ALTINDA (Düşen)"
                    else:
                        # Kafa karıştırmamak için nötrleri gizleyip sade tasarıma sadık kalıyoruz
                        continue
                    
                    parite_temiz = symbol.replace('USDT', '/USDT')
                    mesaj += (
                        f"🪙 **{parite_temiz} (SPOT)**\n"
                        f"├ RSI: {rsi_str}\n"
                        f"├ EMA50: {ema_str}\n"
                        f"└ Yön: **{sinyal}**\n\n"
                    )
                    bulunan += 1
                    
                except Exception as inner_error:
                    # Tek bir coindeki hata tüm taramayı bozmasın diye sessizce pas geçiyoruz
                    print(f"{symbol} tarama hatası: {str(inner_error)}")
                    continue
                
                # 🎯 429 ENGELLENMESİNİ ÖNLEYEN EN KRİTİK AYAR:
                # Her coinden sonra TradingView sunucularını yormamak için 1 saniye bekliyoruz
                time.sleep(1.0)
                
            mesaj += "━━━━━━━━━━━━━━━━━━━━"
            
            if bulunan == 0:
                mesaj = "📊 **BİNANCE 4H KRİPTO SİNYAL RAPORU**\n━━━━━━━━━━━━━━━━━━━━\n\nℹ️ Şu anda filtre kriterlerinize uyan (RSI 30/70 uçlarında olan) aktif bir fırsat bulunamadı.\n━━━━━━━━━━━━━━━━━━━━"
                
        except Exception as e:
            mesaj += f"❌ Genel Sistem Hatası: {str(e)}"
        
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
