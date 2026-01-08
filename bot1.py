# ==================================================================
#    UTOPIA HYBRID PRO - GOD MODE (V16 ULTIMATE MONITOR - CORRECTED)
#    Features: V12 (News) + V13 (ATR) + V15 (Smart Trade) + V16 (Result Monitor)
#    Status: FIXED & READY TO RUN
# ==================================================================
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import requests
import time
import io
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import nltk
nltk.download('vader_lexicon', quiet=True)
import sys
import json
import os

# ================= ⚠️ ใส่รหัสของคุณตรงนี้ ⚠️ =================
NEWS_API_KEY      = "fea0e08efe934cf9a3affdfd52f2084a"
TELEGRAM_TOKEN    = "8268781368:AAEf7PFO84pX4G_5b6h_xasHe-MBu2zCLWU"
TELEGRAM_CHAT_ID  = "-1003531261082"
# =============================================================

# --- Config ---
SYMBOL      = "XAUUSD"
TF_TRADE    = mt5.TIMEFRAME_M15
TF_TREND    = mt5.TIMEFRAME_H1
BASE_LOT    = 0.01
MAX_GRID    = 5
MAGIC       = 99999
MODE        = "SEMI"

# --- Dynamic Settings ---
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5
MIN_GRID_DIST  = 300
SR_LOOKBACK    = 100
SR_BUFFER      = 100

BASKET_TP  = 5.0
MAX_SPREAD = 50
COOLDOWN_SEC = 300
SIGNAL_PAUSE_SEC = 600
AUTO_REPORT_TIME = "23:59"

NEWS_INTERVAL = 3600
HIGH_IMPACT_KEYWORDS = ["NFP", "NON-FARM", "PAYROLL", "CPI", "FOMC", "INTEREST RATE", "INFLATION", "FED DECISION"]

# Global Variables
next_trade_time = 0
last_news_time = 0
cached_news_score = 0
news_blocked = False
last_update_id = 0
current_signal = None 
last_summary_date = None
market_context = {'trend_h1': 0, 'atr_points': 0, 'support': 0, 'resistance': 0}
last_market_update = 0
MARKET_UPDATE_INTERVAL = 1800
last_known_deal = 0

# ================= TOOLS =================
def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def tg_send(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=3)
    except: pass

def tg_send_photo(photo_file):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {'photo': photo_file}
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID}, files=files, timeout=10)
    except: pass

def generate_chart():
    try:
        rates = mt5.copy_rates_from_pos(SYMBOL, TF_TRADE, 0, 100)
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.ta.ema(length=50, append=True); df.ta.ema(length=200, append=True)
        df.ta.bbands(length=20, append=True)

        plt.figure(figsize=(10, 6))
        plt.plot(df['time'], df['close'], label='Price', color='black', linewidth=1)
        try:
            cols = df.columns
            plt.plot(df['time'], df[[c for c in cols if c.startswith('EMA_50')][0]], label='EMA50', color='orange')
            plt.plot(df['time'], df[[c for c in cols if c.startswith('EMA_200')][0]], label='EMA200', color='blue')
            plt.plot(df['time'], df[[c for c in cols if c.startswith('BBU')][0]], 'g--', alpha=0.3)
            plt.plot(df['time'], df[[c for c in cols if c.startswith('BBL')][0]], 'r--', alpha=0.3)
        except: pass

        plt.title(f"{SYMBOL} Analysis")
        plt.legend(); plt.grid(True, alpha=0.3)
        buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0); plt.close()
        return buf
    except: return None

# ================= LOGIC MODULES =================
def analyze_market_structure():
    h1 = mt5.copy_rates_from_pos(SYMBOL, TF_TREND, 0, 200)
    df1 = pd.DataFrame(h1)
    df1.ta.ema(length=50, append=True); df1.ta.ema(length=200, append=True)
    c50 = [c for c in df1.columns if c.startswith('EMA_50')][0]
    c200 = [c for c in df1.columns if c.startswith('EMA_200')][0]
    trend = 1 if df1[c50].iloc[-1] > df1[c200].iloc[-1] else -1

    m15 = mt5.copy_rates_from_pos(SYMBOL, TF_TRADE, 0, SR_LOOKBACK+20)
    df2 = pd.DataFrame(m15)
    df2.ta.atr(length=ATR_PERIOD, append=True)
    atr_val = df2[f'ATRr_{ATR_PERIOD}'].iloc[-1]
    point = mt5.symbol_info(SYMBOL).point
    atr_pts = atr_val / point
    
    res = df2['high'].rolling(SR_LOOKBACK).max().iloc[-1]
    sup = df2['low'].rolling(SR_LOOKBACK).min().iloc[-1]

    return {"trend_h1": trend, "atr_points": atr_pts, "support": sup, "resistance": res}

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
        impact = []
        for a in articles:
            txt = f"{a.get('title','')} {a.get('description','')} {a.get('content','')}".upper()
            for k in HIGH_IMPACT_KEYWORDS:
                if k in txt: impact.append(k)
        if impact:
            news_blocked = True; tg_send(f"🚨 <b>ระงับการเทรด (ข่าวแรง)!</b>\nคำที่เจอ: {list(set(impact))}"); cached_news_score = 0
        else:
            news_blocked = False; cached_news_score = 0
        last_news_time = time.time()
        return cached_news_score
    except: return 0

def get_daily_report():
    now = datetime.now(); start = datetime(now.year, now.month, now.day, 0,0)
    history = mt5.history_deals_get(start, now, group=SYMBOL)
    if not history: return "😴 <b>สรุปยอดวันนี้</b>\nยังไม่มีการเทรด"
    
    net=0.0; g_win=0.0; g_loss=0.0; win=0; loss=0; pts_plus=0; pts_minus=0
    for d in history:
        if d.magic==MAGIC and d.entry==mt5.DEAL_ENTRY_OUT:
            p = d.profit+d.commission+d.swap
            net+=p
            if p>0: g_win+=p; win+=1
            else: g_loss+=abs(p); loss+=1
            try:
                pts = d.profit/d.volume
                if pts>0: pts_plus+=pts
                else: pts_minus+=abs(pts)
            except: pass

    total = win+loss
    wr = (win/total*100) if total>0 else 0
    pf = (g_win/g_loss) if g_loss>0 else 99.99
    
    return (f"📊 <b>รายงานผลประจำวัน</b>\n"
            f"📅 <i>{now.strftime('%d/%m/%Y')}</i>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💰 <b>กำไรสุทธิ:</b> ${net:,.2f} {'🤑' if net>=0 else '🩸'}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>อัตราชนะ:</b> {wr:.1f}% (PF: {pf:.2f})\n"
            f"📈 <b>แต้มบวก:</b> +{pts_plus:.0f} จุด\n"
            f"📉 <b>แต้มลบ:</b> -{pts_minus:.0f} จุด\n"
            f"🔢 <b>จำนวนเทรด:</b> {total} (✅{win} / ❌{loss})")

def monitor_active_signal():
    pass 

# 🔥 ฟังก์ชันใหม่: เฝ้าดูผลลัพธ์การเทรด (TP/SL Monitor)
def monitor_trade_results():
    global last_known_deal
    try:
        from_date = datetime.now() - timedelta(minutes=5)
        to_date = datetime.now() + timedelta(seconds=10)
        deals = mt5.history_deals_get(from_date, to_date, group=SYMBOL)
        
        if deals is None: return

        for d in deals:
            if d.ticket > last_known_deal:
                last_known_deal = d.ticket
                if d.magic == MAGIC and d.entry == mt5.DEAL_ENTRY_OUT:
                    profit = d.profit + d.swap + d.commission
                    result_emoji = "✅ กำไร" if profit >= 0 else "❌ ขาดทุน"
                    msg = (
                        f"{result_emoji} <b>ORDER CLOSED</b>\n"
                        f"🆔 Ticket: {d.position_id}\n"
                        f"💰 Net: <b>${profit:,.2f}</b>\n"
                        f"📉 Type: {'TP/Manual' if profit>=0 else 'SL/Cut'}"
                    )
                    tg_send(msg)
    except: pass

# 🔥 ฟังก์ชันแสดงสถานะ (ย้ายมาไว้ตรงนี้ เพื่อให้บอทรู้จักก่อนเข้าลูป)
# 🔥 ฟังก์ชันแสดงสถานะ (ปรับปรุงใหม่: ภาษาไทยมืออาชีพ + ดูง่าย)
def telegram_status_addon():
    try:
        acc = mt5.account_info()
        pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
        
        # ดึงค่าจาก Market Context
        trend = market_context.get("trend_h1", 0)
        atr   = market_context.get("atr_points", 0)
        
        # คำนวณ Drawdown
        dd = 0
        if acc and acc.balance > 0:
            dd = (acc.balance - acc.equity) / acc.balance * 100

        # แปลงข้อความให้ดูดี
        trend_text = "🟢 ขาขึ้น " if trend == 1 else "🔴 ขาลง "
        mode_text = "🤖 อัตโนมัติ (AUTO)" if MODE == "AUTO" else "🖐️ กึ่งอัตโนมัติ (SEMI)"

        # สร้างข้อความสวยๆ
        msg = (
            "📊 <b>สถานะระบบ UTOPIA (Live Status)</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "⚙️ <b>ข้อมูลระบบ </b>\n"
            f"➤ โหมด: {mode_text}\n"
            f"➤ เทรนด์หลัก (H1): {trend_text}\n"
            f"➤ ความผันผวน (ATR): <b>{atr:.0f}</b> จุด\n\n"
            "💰 <b>ข้อมูลพอร์ต</b>\n"
            f"💵 ยอดเงินคงเหลือ: <code>${acc.balance:,.2f}</code>\n"
            f"📈 อิควิตี้: <code>${acc.equity:,.2f}</code>\n"
            f"🔻 ความเสี่ยง (DD): <b>{dd:.2f}%</b>\n"
            f"📝 ออเดอร์คงค้าง: <b>{len(pos) if pos else 0}</b> ไม้"
        )
        tg_send(msg)
    except Exception as e:
        log(f"Status Error: {e}")

# ================= EXECUTION (SMART LOGIC) =================
def close_all_positions():
    pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
    c=0
    for p in pos:
        mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": SYMBOL, "volume": p.volume, "type": 1-p.type, "magic": MAGIC}); c+=1
    return c

def set_breakeven():
    pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
    c=0
    for p in pos:
        if p.profit>0 and abs(p.sl-p.price_open)>0.01:
            mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": p.ticket, "sl": p.price_open, "tp": p.tp}); c+=1
    return c

def execute_trade(side, lot, reason, is_grid=False):
    t = mt5.symbol_info_tick(SYMBOL)
    price = t.ask if side == "BUY" else t.bid
    pt = mt5.symbol_info(SYMBOL).point
    
    # === 🔥 SMART TP/SL CALCULATION ===
    sl_price = 0.0
    tp_price = 0.0
    is_smart = False
    
    if not is_grid and current_signal and current_signal['side'] == side:
        sl_price = current_signal['sl']
        tp_price = current_signal['tp2'] 
        is_smart = True
    else:
        if side == "BUY":
            tp_price = price + 1000 * pt
            sl_price = price - 800 * pt
        else:
            tp_price = price - 1000 * pt
            sl_price = price + 800 * pt
            
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": float(lot),
        "type": mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": float(sl_price),
        "tp": float(tp_price),
        "magic": MAGIC,
        "deviation": 20,
        "comment": reason
    }
    res = mt5.order_send(req)
    
    if res.retcode == mt5.TRADE_RETCODE_DONE and not is_grid: 
        if is_smart:
            tg_send(f"✅ <b>เปิด {side} (ตาม Signal)</b> @ {price:.2f}\n"
                    f"🎯 TP: {tp_price:.2f} (Auto)\n"
                    f"🛑 SL: {sl_price:.2f} (Auto)\n"
                    f"เหตุผล: {reason}")
        else:
            tg_send(f"✅ <b>เปิด {side} (Manual)</b> @ {price:.2f}\n"
                    f"🎯 TP: {tp_price:.2f}\n"
                    f"🛑 SL: {sl_price:.2f}\n"
                    f"เหตุผล: {reason}")
        
        if side == "BUY": tg_send_photo(generate_chart())
        
    return res

def send_signal_only(side, price, detail):
    global current_signal
    pt = mt5.symbol_info(SYMBOL).point
    atr_price = market_context.get('atr_points', 0) * pt
    
    if side == "BUY":
        tp1 = price + (atr_price * 1.0)
        tp2 = price + (atr_price * 2.0)
        sl  = price - (atr_price * 1.5)
    else:
        tp1 = price - (atr_price * 1.0)
        tp2 = price - (atr_price * 2.0)
        sl  = price + (atr_price * 1.5)
        
    current_signal = {'side': side, 'tp1': tp1, 'tp2': tp2, 'sl': sl}
    
    msg = (
        "📣 <b>SEMI TRADE PLAN</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"{'🟢 BUY' if side=='BUY' else '🔴 SELL'} {SYMBOL}\n"
        f"📍 Entry: {price:.2f}\n\n"
        f"🎯 TP1: {tp1:.2f}\n"
        f"🎯 TP2: {tp2:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💡 พิมพ์ <code>/{side.lower()}</code> เพื่อเข้าตามแผนนี้!"
    )
    tg_send(msg)
    tg_send_photo(generate_chart())

# ================= MAIN LOOP =================
if not mt5.initialize(): quit()
log("🚀 ระบบ UTOPIA HYBRID BOT (V16 Ultimate) เริ่มทำงานแล้ว")

# --- Init Result Monitor ---
h = mt5.history_deals_get(datetime.now() - timedelta(hours=24), datetime.now(), group=SYMBOL)
if h: last_known_deal = h[-1].ticket
else: last_known_deal = 0

try:
    while True:
        # 1. Update Market Context
        try: market_context = analyze_market_structure()
        except: pass
        
        # 2. Monitor Result
        monitor_trade_results()

        # 3. Market Update (30 min)
        if time.time() - last_market_update >= MARKET_UPDATE_INTERVAL:
            try:
                # แปลงสถานะเทรนด์เป็นไทย
                trend = market_context.get('trend_h1')
                if trend == 1:
                    trend_display = "🟢 ขาขึ้น (หน้า Buy ได้เปรียบ)"
                else:
                    trend_display = "🔴 ขาลง (หน้า Sell ได้เปรียบ)"
                
                # แปลงสถานะข่าวเป็นไทย
                if news_blocked:
                    news_status = "⛔ <b>อันตราย! (มีข่าวแรง/ระงับเทรด)</b>"
                else:
                    news_status = "✅ <b>ปกติ (ตลาดปลอดภัย)</b>"

                # ดึงค่า Technical
                atr = market_context.get('atr_points', 0)
                sup = market_context.get('support', 0)
                res = market_context.get('resistance', 0)
                curr_time = datetime.now().strftime('%H:%M')

                # สร้างข้อความ Dashboard ภาษาไทยสวยๆ
                msg = (
                    f"📡 <b>รายงานสถานะตลาด: {SYMBOL}</b>\n"
                    f"🕒 <i>เวลาอัปเดต: {curr_time} น.</i>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"🌊 <b>เทรนด์ (H1)</b>\n"
                    f"➤ แนวโน้ม: {trend_display}\n"
                    f"➤ ความผันผวน (ATR): <b>{atr:.0f}</b> จุด\n\n"
                    f"🛡️ <b>จุดยุทธศาสตร์สำคัญ</b>\n"
                    f"🧱 แนวต้าน: <code>{res:.2f}</code>\n"
                    f"🧶 แนวรับ:  <code>{sup:.2f}</code>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📰 <b>สถานะข่าวเศรษฐกิจ:</b>\n"
                    f"{news_status}"
                )
                
                tg_send(msg)
                last_market_update = time.time()
            except Exception as e:
                log(f"Market Update Error: {e}")

        # 4. Telegram Listener
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            r = requests.get(url, params={"offset": last_update_id + 1}, timeout=1).json()
            for u in r.get("result", []):
                last_update_id = u["update_id"]
                if "message" in u and "text" in u["message"]:
                    cmd = u["message"]["text"].lower()
                    
                    if cmd == "/buy":
                        execute_trade("BUY", BASE_LOT, "Telegram Cmd")
                    elif cmd == "/sell":
                        execute_trade("SELL", BASE_LOT, "Telegram Cmd")
                    elif cmd == "/closeall":
                        close_all_positions(); tg_send("⛔ Closed All")
                    elif cmd == "/status":
                        telegram_status_addon() # เรียกฟังก์ชันสถานะ
                    elif cmd == "/auto": MODE="AUTO"; tg_send("🤖 Mode: AUTO")
                    elif cmd == "/semi": MODE="SEMI"; tg_send("🖐️ Mode: SEMI")
                    elif cmd == "/chart": 
                        tg_send("📸 กำลังโหลดกราฟ...")
                        img = generate_chart(); tg_send_photo(img) if img else tg_send("❌ สร้างกราฟไม่สำเร็จ")
                    elif cmd == "/report":
                        tg_send(get_daily_report())
                    elif cmd == "/be":
                        c = set_breakeven()
                        tg_send(f"🛡️ ตั้งบังทุนสำเร็จ: {c} ไม้")
                    elif cmd.startswith("/setlot"):
                        try: BASE_LOT = float(cmd.split()[1]); tg_send(f"✅ ปรับขนาดล็อตเป็น: {BASE_LOT} Lot")
                        except: pass
                    elif cmd.startswith("/setnews"):
                        try:
                            new_key = cmd.split()[1]; NEWS_API_KEY = new_key; tg_send(f"✅ News Key: {new_key[:5]}...")
                        except: pass
                    elif cmd == "/resetcapital":
                        acc = mt5.account_info()
                        if acc:
                            last_capital = acc.balance
                            has_notified_withdraw = False
                            tg_send(f"🔄 รีเซ็ตทุน: ${last_capital:,.2f}")
                            
        except Exception as e:
            log(f"Telegram Error: {e}")

        # 5. Trading Logic
        if time.time() >= next_trade_time:
            pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
            
            # Manage & Grid
            if pos:
                net_p = sum(p.profit + p.swap for p in pos)
                if net_p >= BASKET_TP:
                    close_all_positions(); tg_send(f"💰 Basket TP: ${net_p:.2f}"); next_trade_time = time.time() + COOLDOWN_SEC
                elif len(pos) < MAX_GRID:
                    last = pos[-1]; t = mt5.symbol_info_tick(SYMBOL)
                    grid_dist = max(MIN_GRID_DIST, market_context['atr_points'] * ATR_MULTIPLIER)
                    dist = (last.price_open - t.bid)/mt5.symbol_info(SYMBOL).point if last.type==0 else (t.ask - last.price_open)/mt5.symbol_info(SYMBOL).point
                    if dist >= grid_dist: 
                        execute_trade("BUY" if last.type==0 else "SELL", last.volume, f"Grid (ATR {grid_dist:.0f})", is_grid=True)
            
            # New Entry
            else:
                deep_news_analysis()
                if not news_blocked:
                    tick = mt5.symbol_info_tick(SYMBOL)
                    if (tick.ask - tick.bid)/mt5.symbol_info(SYMBOL).point <= MAX_SPREAD:
                        r = mt5.copy_rates_from_pos(SYMBOL, TF_TRADE, 0, 300)
                        df = pd.DataFrame(r)
                        df.ta.ema(20, append=True); df.ta.ema(50, append=True)
                        df.ta.rsi(14, append=True); df.ta.bbands(20, append=True)
                        
                        try:
                            c_rsi = [c for c in df.columns if c.startswith('RSI')][0]
                            c_bbl = [c for c in df.columns if c.startswith('BBL')][0]
                            c_bbu = [c for c in df.columns if c.startswith('BBU')][0]
                            c_ema20 = [c for c in df.columns if c.startswith('EMA_20')][0]
                            curr_close = df['close'].iloc[-1]; curr_rsi = df[c_rsi].iloc[-1]
                            score = 0; side = ""
                            
                            if curr_close < df[c_bbl].iloc[-1] and curr_rsi < 30: score += 2; side = "BUY"
                            elif curr_close > df[c_bbu].iloc[-1] and curr_rsi > 70: score += 2; side = "SELL"
                            
                            if score >= 2:
                                if (side == "BUY" and market_context.get('trend_h1') == 1) or (side == "SELL" and market_context.get('trend_h1') == -1): score += 1
                                if side == "BUY" and cached_news_score > 0: score += 1
                                elif side == "SELL" and cached_news_score < 0: score += 1
                                
                            if score >= 4:
                                detail = f"Score: {score}/6"
                                if MODE == "AUTO": execute_trade(side, BASE_LOT, detail)
                                else: 
                                    send_signal_only(side, tick.ask if side=="BUY" else tick.bid, detail)
                                    next_trade_time = time.time() + SIGNAL_PAUSE_SEC
                        except: pass
        time.sleep(1)

except KeyboardInterrupt: pass
finally: mt5.shutdown()
