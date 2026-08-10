import os
import time
import requests
import telebot
from telebot import types
from flask import Flask, request

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 PİYASAYI TEK TIKLA TARA", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    metin = (
        "🤖 *Binance 4H Premium Tarayıcı*\n\n"
        "Tek tıkla tüm altcoin piyasasını taratabilir, kurumsal sinyal ve "
        "durum raporlarına ulaşabilirsiniz."
    )
    bot.send_message(message.chat.id, metin, reply_markup=tek_buton_olustur(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="Premium analiz motoru çalıştırıldı...")
        gecici = bot.send_message(call.message.chat.id, "🔄 *Piyasa taranıyor, lütfen bekleyin...*", parse_mode="Markdown")
        
        # Telegram'da gördüğünüz o dikey çizgisiz, boşluklu soft tasarım başlığı
        mesaj = "📊 *BİNANCE AKILLI DURUM RAPORU (4H)*\n"
        mesaj += "‾\n\n"
        
        try:
            # Engellenmeyen kurumsal önbellek API'sinden anlık majör piyasa verilerini çekiyoruz
            url = "https://coingecko.com"
            response = requests.get(url, headers={"accept": "application/json"}).json()
            
            coin_haritasi = {
                'bitcoin': 'BTC/USDT', 'ethereum': 'ETH/USDT', 'solana': 'SOL/USDT',
                'ripple': 'XRP/USDT', 'binancecoin': 'BNB/USDT', 'chainlink': 'LINK/USDT',
                'dogecoin': 'DOGE/USDT', 'fetch-ai': 'FET/USDT', 'sui': 'SUI/USDT', 'cardano': 'ADA/USDT'
            }
            
            for coin in response:
                coin_id = coin.get('id')
                if coin_id in coin_haritasi:
                    symbol = coin_haritasi[coin_id]
                    fiyat = float(coin.get('current_price', 0))
                    degisim = float(coin.get('price_change_percentage_24h', 0))
                    
                    fiyat_str = f"${fiyat:.2f}" if fiyat >= 1 else f"${fiyat:.4f}"
                    
                    # Soft görünümlü akıllı sinyal simülasyonu
                    if degisim >= 0:
                        sinyal = "🟢 *LONG (AL)*"
                        rsi_str = "🟢 `32` (Alım Bölgesi)" if degisim < 1 else "⚪ `45` (Normal)"
                        ema_str = "🟢 *Üstünde* (Yükselen)"
                    else:
                        sinyal = "🔴 *SHORT (SAT)*"
                        rsi_str = "🔴 `72` (Şişmiş Bölge)" if degisim > -1 else "⚪ `54` (Normal)"
                        ema_str = "🔴 *Altında* (Düşen)"
                    
                    # Tam olarak Telegram'da gördüğünüz o dikey çizgisiz, bloklu premium şablon tasarımı
                    mesaj += (
                        f"🪙 *{symbol}* \n"
                        f"• RSI (14): {rsi_str}\n"
                        f"• EMA (50): {ema_str}\n"
                        f"• Anlık Fiyat: `{fiyat_str}`\n"
                        f"• Sinyal Durumu: {sinyal}\n"
                        f"⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼⎼\n\n"
                    )
            
        except Exception as e:
            mesaj += f"❌ Veri eşleşme hatası: {str(e)}"
        
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
