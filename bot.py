import os
import telebot
from flask import Flask, request

# ⚠️ BURAYA BOTFATHER'DAN ALDIĞINIZ GERÇEK ŞİFREYİ YAZIN
TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
app = Flask(__name__)

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

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # Siz bota ne yazarsanız yazın, bot size aynen bu mesajı geri fırlatacak
    bot.reply_to(message, "⚙️ TEST BAŞARILI: Botunuz Render üzerinden canlı olarak yanıt veriyor!")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
