# ==================================================================
#         UTOPIA HYBRID PRO - GUARDIAN EDITION (V10.1 COMPLETE)
# ==================================================================
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import requests
import time
import nltk
from datetime import datetime
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# ================= 1. CONFIGURATION =================
SYMBOL     = "XAUUSD"
TF         = mt5.TIMEFRAME_M15
BASE_LOT   = 0.01
GRID_DIST  = 500
MAX_GRID   = 5
MAGIC      = 99999

MODE       = "SEMI"    # AUTO / SEMI
BASKET_TP  = 5.0       # $
EQUITY_STOP = 0.7
MAX_SPREAD = 50
COOLDOWN_SEC = 300
SIGNAL_PAUSE_SEC = 600
NEAR_POINT = 100
AUTO_REPORT_TIME = "23:59"

# ================= ⚠️ ใส่รหัสของคุณตรงนี้ ⚠️ =================
NEWS_API_KEY      = "fea0e08efe934cf9a3affdfd52f2084a"
TELEGRAM_TOKEN    = "8268781368:AAEf7PFO84pX4G_5b6h_xasHe-MBu2zCLWU"
TELEGRAM_CHAT_ID  = "-1003531261082"

NEWS_INTERVAL = 3600
HIGH_IMPACT_KEYWORDS = ["NFP", "NON-FARM", "PAYROLL", "CPI", "FOMC", "INTEREST RATE", "INFLATION", "FED DECISION"]

# ตัวแปรระบบ
next_trade_time = 0
last_news_time = 0
cached_news_score = 0
news_blocked = False
last_update_id = 0
current_signal = None 
last_summary_date = None

# ================= 2. UTILS =================
def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def tg_send(msg):
    if "ใส่" in TELEGRAM_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=3)
    except: pass

def close_all_positions():
    pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
    if not pos: return 0
    count = 0
    for p in pos:
        tick = mt5.symbol_info_tick(SYMBOL)
        mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": SYMBOL, "volume": p.volume, "type": 1 if p.type==0 else 0, "price": tick.bid if p.type==0 else tick.ask, "magic": MAGIC})
        count += 1
    return count

# ================= 3. PRO REPORT (V10) =================
def get_daily_report():
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
    history = mt5.history_deals_get(today_start, now, group=SYMBOL)
    
    if history is None or len(history) == 0: return "😴 <b>สรุปยอดวันนี้</b>\nยังไม่มีออเดอร์ครับ"

    total_net_profit = 0.0; gross_profit = 0.0; gross_loss = 0.0
    win_count = 0; loss_count = 0
    plus_points = 0.0; minus_points = 0.0
    
    for deal in history:
        if deal.magic == MAGIC and deal.entry == mt5.DEAL_ENTRY_OUT:
            profit = deal.profit + deal.commission + deal.swap
            total_net_profit += profit
            if profit > 0: gross_profit += profit; win_count += 1
            else: gross_loss += abs(profit); loss_count += 1
            try:
                if deal.volume > 0:
                    pts = deal.profit / deal.volume
                    if pts > 0: plus_points += pts
                    else: minus_points += abs(pts)
            except: pass

    total_trades = win_count + loss_count
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99
    net_points = plus_points - minus_points
    
    icon = "🤑" if total_net_profit >= 0 else "🩸"
    pf_icon = "🔥" if profit_factor >= 1.5 else "⚠️" if profit_factor < 1.0 else "✅"

    msg = (f"📊 <b>รายงานผลระดับโปร (Pro Report)</b>\n"
           f"📅 <i>{today_start.strftime('%d/%m/%Y')}</i>\n"
           f"━━━━━━━━━━━━━━━━\n"
           f"💰 <b>Net Profit:</b> ${total_net_profit:,.2f} {icon}\n"
           f"━━━━━━━━━━━━━━━━\n"
           f"🎯 <b>Win Rate:</b> {win_rate:.1f}%\n"
           f"⚖️ <b>Profit Factor:</b> {profit_factor:.2f} {pf_icon}\n"
           f"━━━━━━━━━━━━━━━━\n"
           f"📈 <b>แต้มบวก:</b> +{plus_points:,.0f} จุด\n"
           f"📉 <b>แต้มลบ:</b> -{minus_points:,.0f} จุด\n"
           f"🏁 <b>สุทธิ:</b> {net_points:+,.0f} จุด\n"
           f"━━━━━━━━━━━━━━━━\n"
           f"🔢 <b>Trades:</b> {total_trades} (✅{win_count} / ❌{loss_count})")
    return msg

# ================= 4. SIGNAL TRACKER (V9) =================
def monitor_active_signal():
    global current_signal
    if not current_signal: return
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        curr = tick.bid if current_signal['side'] == "BUY" else tick.ask
        s = current_signal
        
        hit_sl = (s['side']=="BUY" and curr<=s['sl']) or (s['side']=="SELL" and curr>=s['sl'])
        hit_tp2 = (s['side']=="BUY" and curr>=s['tp2']) or (s['side']=="SELL" and curr<=s['tp2'])
        
        if hit_sl: tg_send(f"😭 <b>ชน SL</b> @ {curr:.2f}"); current_signal=None; return
        if hit_tp2: tg_send(f"🏆 <b>ชน TP2</b> @ {curr:.2f}"); current_signal=None; return

        hit_tp1 = (s['side']=="BUY" and curr>=s['tp1']) or (s['side']=="SELL" and curr<=s['tp1'])
        if hit_tp1 and 'TP1' not in s['alerted']:
            tg_send(f"🎯 <b>ชน TP1</b> @ {curr:.2f}"); s['alerted'].append('TP1')
        elif 'TP1' not in s['alerted'] and 'NEAR' not in s['alerted']:
            dist = abs(curr - s['tp1']) / mt5.symbol_info(SYMBOL).point
            if dist <= NEAR_POINT: tg_send(f"🔔 <b>ใกล้ TP1 ({dist:.0f} จุด)</b>"); s['alerted'].append('NEAR')
    except: pass

# ================= 5. AI NEWS =================
def deep_news_analysis():
    global last_news_time, cached_news_score, news_blocked
    if "ใส่" in NEWS_API_KEY: return 0
    if (time.time() - last_news_time < NEWS_INTERVAL): return cached_news_score
    try:
        url = f"https://newsapi.org/v2/everything?q=gold+price+OR+inflation+OR+fed&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}"
        r = requests.get(url, timeout=5).json()
        articles = r.get("articles", [])
        if not articles: return 0
        s = SentimentIntensityAnalyzer()
        total_sentiment = 0; impact_detected = []
        for a in articles:
            full_text = f"{a.get('title','')} {a.get('description','')} {a.get('content','')}".upper()
            for key in HIGH_IMPACT_KEYWORDS:
                if key in full_text: impact_detected.append(key)
            total_sentiment += s.polarity_scores(full_text)["compound"]
        if impact_detected:
            news_blocked = True; tg_send(f"🚨 <b>NEWS BLOCK!</b>\n{list(set(impact_detected))}"); cached_news_score = 0
        else:
            news_blocked = False; avg = total_sentiment / len(articles)
            cached_news_score = 1 if avg > 0.1 else -1 if avg < -0.1 else 0
        last_news_time = time.time()
        return cached_news_score
    except: return 0

# ================= 6. EXECUTE =================
def execute_trade(side, lot, reason, is_grid=False):
    t = mt5.symbol_info_tick(SYMBOL)
    price = t.ask if side == "BUY" else t.bid
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": float(lot), "type": mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL, "price": price, "magic": MAGIC, "deviation": 20, "comment": reason, "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    if res.retcode == mt5.TRADE_RETCODE_DONE and not is_grid: tg_send(f"✅ <b>{side}</b> @ {price:.2f}\nเหตุผล: {reason}")
    return res

def send_signal_only(side, price, detail):
    global current_signal
    pt = mt5.symbol_info(SYMBOL).point
    tp1, tp2, sl = (price + 500*pt, price + 1000*pt, price - 800*pt) if side=="BUY" else (price - 500*pt, price - 1000*pt, price + 800*pt)
    current_signal = {'side': side, 'tp1': tp1, 'tp2': tp2, 'sl': sl, 'alerted': []}
    icon = "🔵" if side=="BUY" else "🟠"
    tg_send(f"{icon} <b>Signal {side}</b> @ {price:.2f}\n🎯 TP1: {tp1:.2f} | TP2: {tp2:.2f}\n🛑 SL: {sl:.2f}\n{detail}")

# ================= 7. MAIN LOOP =================
if not mt5.initialize(): quit()
log("🚀 SYSTEM V10.1 (FULL COMPLETE) STARTED")

try:
    while True:
        now = datetime.now()
        if now.strftime("%H:%M") == AUTO_REPORT_TIME and last_summary_date != now.date():
            tg_send(get_daily_report()); last_summary_date = now.date()

        if "ใส่" not in TELEGRAM_TOKEN:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                r = requests.get(url, params={"offset": last_update_id + 1}, timeout=1).json()
                for u in r.get("result", []):
                    last_update_id = u["update_id"]
                    if "message" in u and "text" in u["message"]:
                        cmd = u["message"]["text"].lower()
                        
                        # --- นี่คือส่วนที่ผมแก้คืนให้ครับ (แบบละเอียด) ---
                        if cmd == "/status": 
                            wait_time = max(0, int(next_trade_time - time.time()))
                            st_msg = f"พักอีก {wait_time} วินาที" if wait_time > 0 else "พร้อมเทรด ✅"
                            track_msg = f"กำลังตาม {current_signal['side']}" if current_signal else "ไม่มีสัญญาณ"
                            news_msg = "⛔ ติดข่าว (Block)" if news_blocked else "✅ ข่าวปกติ"
                            
                            tg_send(f"📊 <b>สถานะระบบปัจจุบัน</b>\n━━━━━━━━━━━━\n🕹️ <b>โหมด:</b> {MODE}\n⏳ <b>ระบบ:</b> {st_msg}\n📡 <b>สัญญาณ:</b> {track_msg}\n📰 <b>ข่าว:</b> {news_msg}")
                        
                        elif cmd == "/report": tg_send(get_daily_report())
                        elif cmd == "/auto": MODE="AUTO"; tg_send("🤖 เปลี่ยนโหมด: AUTO")
                        elif cmd == "/semi": MODE="SEMI"; tg_send("🖐️ เปลี่ยนโหมด: SEMI")
                        elif cmd == "/buy": execute_trade("BUY", BASE_LOT, "Manual")
                        elif cmd == "/sell": execute_trade("SELL", BASE_LOT, "Manual")
                        elif cmd == "/closeall": c=close_all_positions(); tg_send(f"⛔ ปิดรวบยอด: {c} ไม้")
            except: pass

        if MODE == "SEMI": monitor_active_signal()

        acc = mt5.account_info()
        if acc is None:
            if not mt5.initialize(): time.sleep(5)
            continue
        if acc.equity < acc.balance * EQUITY_STOP: tg_send("🚨 EQUITY STOP"); break

        if time.time() >= next_trade_time:
            pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
            if pos:
                net_p = sum(p.profit + p.swap for p in pos)
                if net_p >= BASKET_TP:
                    close_all_positions(); tg_send(f"💰 <b>Basket TP: ${net_p:.2f}</b>"); next_trade_time = time.time() + COOLDOWN_SEC; continue
                if len(pos) < MAX_GRID:
                    last = pos[-1]; t = mt5.symbol_info_tick(SYMBOL)
                    dist = (last.price_open - t.bid)/mt5.symbol_info(SYMBOL).point if last.type==0 else (t.ask - last.price_open)/mt5.symbol_info(SYMBOL).point
                    if dist >= GRID_DIST: execute_trade("BUY" if last.type==0 else "SELL", last.volume, "Grid", is_grid=True)
            else:
                vn = deep_news_analysis()
                if not news_blocked:
                    tick = mt5.symbol_info_tick(SYMBOL)
                    if (tick.ask - tick.bid)/mt5.symbol_info(SYMBOL).point <= MAX_SPREAD:
                        r = mt5.copy_rates_from_pos(SYMBOL, TF, 0, 300)
                        df = pd.DataFrame(r)
                        df.ta.ema(50, append=True); df.ta.ema(200, append=True)
                        df.ta.rsi(14, append=True); df.ta.bbands(20, append=True)
                        try:
                            c = df.columns
                            c_ema50 = [x for x in c if x.startswith('EMA_50')][0]
                            c_ema200 = [x for x in c if x.startswith('EMA_200')][0]
                            c_bbl = [x for x in c if x.startswith('BBL')][0]
                            c_bbu = [x for x in c if x.startswith('BBU')][0]
                            c_rsi = [x for x in c if x.startswith('RSI')][0]
                            vt = 1 if df[c_ema50].iloc[-1] > df[c_ema200].iloc[-1] else -1
                            vq = 0
                            if df['close'].iloc[-1] < df[c_bbl].iloc[-1] and df[c_rsi].iloc[-1] < 30: vq = 1
                            elif df['close'].iloc[-1] > df[c_bbu].iloc[-1] and df[c_rsi].iloc[-1] > 70: vq = -1
                            score = (vt * 2) + vq + vn
                            if abs(score) >= 3:
                                detail = f"Score: {score}"
                                if MODE == "AUTO": execute_trade("BUY" if score > 0 else "SELL", BASE_LOT, detail)
                                else: send_signal_only("BUY" if score > 0 else "SELL", tick.ask if score > 0 else tick.bid, detail); next_trade_time = time.time() + SIGNAL_PAUSE_SEC
                        except: pass
        time.sleep(1)
except KeyboardInterrupt: pass
finally: mt5.shutdown()