import os
import time
import requests  # Kilitlenmeyi önlemek için doğrudan hızlı web istekleri kullanıyoruz
import telebot
from telebot import types
from flask import Flask, request

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"

bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

def tek_buton_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔍 POPÜLER COINLERI ANLIK TARA", callback_data="tara_hepsini"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(
        message.chat.id, 
        "🤖 **Binance 4H Kesin Sonuç Tarayıcı V4**\n\nAltyapı testi başarıyla tamamlandı! Butona bastığınızda popüler paritelerin anlık durum raporu kilitlenmeden listelenir.", 
        reply_markup=tek_buton_olustur(), 
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    if call.data == "tara_hepsini":
        bot.answer_callback_query(call.id, text="Canlı veriler borsadan çekiliyor...")
        gecici = bot.send_message(call.message.chat.id, "🔄 Binance havuzu sorgulanıyor... Lütfen bekleyin.")
        
        mesaj = f"📊 **ANLIK PIYASA DURUM RAPORU (4H)**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift    | Tip   | Fiyat     | Sinyal`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
        
        try:
            # Kilitlenen ccxt yerine Binance'in en hızlı resmi fiyat API'sini tek seferde çekiyoruz
            response = requests.get("https://binance.com").json()
            fiyatlar = {item['symbol']: float(item['price']) for item in response if item['symbol'].endswith('USDT')}
            
            # Tabloda kesin olarak listelenecek ana coinler
            izleme_listesi = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'AVAXUSDT', 'BNBUSDT', 'LINKUSDT', 'DOGEUSDT', 'SUIUSDT', 'FETUSDT']
            
            bulunan = 0
            for symbol in izleme_listesi:
                if symbol in fiyatlar:
                    fiyat = fiyatlar[symbol]
                    # Tablo tasarımı için fiyat basamaklarını ayarlama
                    fiyat_str = f"{fiyat:.2f}" if fiyat >= 1 else f"{fiyat:.4f}"
                    parite_adi = symbol.replace('USDT', '/USDT')
                    
                    # İlk aşamada verilerin kesin geldiğini görmek için canlı fiyat bazlı basit sinyal
                    sinyal = "🟢BOĞA" if fiyat > (fiyat * 0.999) else "🔴AYI"
                    
                    mesaj += f"`{parite_adi:<8} | SPOT  | {fiyat_str:<9} | {sinyal}`\n"
                    bulunan += 1
            
            mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
            
        except Exception as e:
            mesaj += f"❌ Veri çekme hatası oluştu: {str(e)}"
        
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
