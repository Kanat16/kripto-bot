import ccxt
import pandas as pd
import pandas_ta as ta
import telebot
from telebot import types
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

TELEGRAM_TOKEN = "8970525485:AAHgJZIzdvWJEPRkcT1C6xOx5qx-eSrviMk"
WHALE_THRESHOLD_USD = 50000  

bot = telebot.TeleBot(TELEGRAM_TOKEN)
exchange = ccxt.binance({'enableRateLimit': True})

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Aktif")

def web_sunucu_baslat():
    server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    server.serve_forever()

def marketleri_getir(market_type='spot'):
    try:
        exchange.load_markets()
        semboller = []
        for symbol, market in exchange.markets.items():
            if market['quote'] == 'USDT' and market['active']:
                if market_type == 'spot' and market['spot']: semboller.append(symbol)
                elif market_type == 'swap' and market['linear']: semboller.append(symbol)
        return semboller
    except: return []

def trend_ve_balina_analizi(symbol, timeframe='4h', market_type='spot'):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if len(df) < 55: return None
        df['RSI'] = ta.rsi(df['close'], length=14)
        df['EMA50'] = ta.ema(df['close'], length=50)
        son_rsi, son_kapanis, son_ema50 = df['RSI'].iloc[-1], df['close'].iloc[-1], df['EMA50'].iloc[-1]
        
        trades = exchange.fetch_trades(symbol, limit=100)
        buy_whale_vol, sell_whale_vol, total_whale_vol = 0, 0, 0
        for trade in trades:
            usd_size = trade['price'] * trade['amount']
            if usd_size >= WHALE_THRESHOLD_USD:
                total_whale_vol += usd_size
                if trade['side'] == 'buy': buy_whale_vol += usd_size
                elif trade['side'] == 'sell': sell_whale_vol += usd_size
        balina_durum = "NÖTR"
        if total_whale_vol > 0:
            buy_ratio = (buy_whale_vol / total_whale_vol) * 100
            sell_ratio = (sell_whale_vol / total_whale_vol) * 100
            if buy_ratio > 55: balina_durum = "AL"
            elif sell_ratio > 55: balina_durum = "SAT"
            
        if son_kapanis > son_ema50 and son_rsi < 45 and balina_durum == "AL":
            return [symbol.replace('/USDT', ''), "🟢YÜKSELEN", f"🟢{son_rsi:.0f}", f"🐳 %{buy_ratio:.0f} GİRİŞ", "⚡ GÜÇLÜ AL"]
        elif son_kapanis < son_ema50 and son_rsi > 55 and balina_durum == "SAT":
            return [symbol.replace('/USDT', ''), "🔴DÜŞEN", f"🔴{son_rsi:.0f}", f"🚨 %{sell_ratio:.0f} ÇIKIŞ", "💥 GÜÇLÜ SAT"]
        return None
    except: return None

def ana_butonlari_olustur():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🟢 SPOT PİYASAYI TARA", callback_data="tara_spot"),
               types.InlineKeyboardButton("🔴 VADELİ PİYASAYI TARA", callback_data="tara_vadeli"))
    return markup

@bot.message_handler(commands=['start', 'menu'])
def karsilama_mesaji(message):
    bot.send_message(message.chat.id, "🤖 **Binance 4H Sinyal Tarayıcı**\nTaramayı başlatmak için butonları kullanın.", reply_markup=ana_butonlari_olustur(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def buton_isleyici(call):
    bot.answer_callback_query(call.id, text="Tarama başlatıldı...")
    market_tipi = 'spot' if call.data == 'tara_spot' else 'swap'
    gecici = bot.send_message(call.message.chat.id, f"🔄 Binance 4H ({market_tipi.upper()}) taranıyor...")
    
    tum_semboller = marketleri_getir(market_tipi)
    secilen_semboller = [s for s in tum_semboller if s in ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'AVAX/USDT', 'BNB/USDT', 'LINK/USDT']]
    
    mesaj = f"📊 **BİNANCE 4H TARAMA ({market_tipi.upper()})**\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n`Çift      | Trend    | RSI  | Balina Girişi | Sinyal`\n`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`\n"
    bulunan = 0
    for symbol in secilen_semboller:
        res = trend_ve_balina_analizi(symbol, timeframe='4h', market_type=market_tipi)
        if res:
            mesaj += f"`{res:<9} | {res:<8} | {res:<4} | {res:<13} | {res}`\n"
            bulunan += 1
        time.sleep(0.2)
    if bulunan == 0: mesaj += "ℹ️ _Kriterlere uyan aktif bir fırsat yok._\n"
    mesaj += "`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`"
    bot.delete_message(call.message.chat.id, gecici.message_id)
    bot.send_message(call.message.chat.id, mesaj, reply_markup=ana_butonlari_olustur(), parse_mode="Markdown")

if __name__ == "__main__":
    t = threading.Thread(target=web_sunucu_baslat)
    t.daemon = True
    t.start()
    print("Bot başlatıldı...")
    bot.polling(none_stop=True)
