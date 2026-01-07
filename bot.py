# ==================================================================
#    UTOPIA HYBRID PRO - GOD MODE (V14 THAI EDITION)
#    Features: V12 (News/Chart/Report) + V13 (MTF/ATR/SR)
#    Language: THAI (Dashboard Only)
# ==================================================================
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import requests
import time
import io
import matplotlib.pyplot as plt
from datetime import datetime
from nltk.sentiment.vader import SentimentIntensityAnalyzer

# ================= 1. ตั้งค่าระบบ (CONFIGURATION) =================
SYMBOL     = "XAUUSD"
TF_TRADE   = mt5.TIMEFRAME_M15  # เทรดบน M15
TF_TREND   = mt5.TIMEFRAME_H1   # ดูเทรนด์ H1
BASE_LOT   = 0.01
MAX_GRID   = 5
MAGIC      = 99999

# --- ตั้งค่า Dynamic (ATR/SR) ---
ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5   # ตัวคูณ ATR หาระยะแก้ไม้
MIN_GRID_DIST  = 300   # ระยะแก้ไม้ต่ำสุด (จุด)
SR_LOOKBACK    = 100   # ย้อนหลังหาแนวรับต้าน
SR_BUFFER      = 100   # ระยะปลอดภัยจากแนวรับต้าน

MODE       = "SEMI"
BASKET_TP  = 5.0
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
market_context = {'trend_h1': 0, 'atr_points': 0, 'support': 0, 'resistance': 0}

# ================= 2. เครื่องมือ & กราฟิก (UTILS) =================
def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def tg_send(msg):
    if "ใส่" in TELEGRAM_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=3)
    except: pass

def tg_send_photo(photo_file):
    if "ใส่" in TELEGRAM_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        files = {'photo': photo_file}
        data = {'chat_id': TELEGRAM_CHAT_ID}
        requests.post(url, data=data, files=files, timeout=10)
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
            c_ema50 = [c for c in cols if c.startswith('EMA_50')][0]
            c_ema200 = [c for c in cols if c.startswith('EMA_200')][0]
            c_bbu = [c for c in cols if c.startswith('BBU')][0]
            c_bbl = [c for c in cols if c.startswith('BBL')][0]
            plt.plot(df['time'], df[c_ema50], label='EMA50', color='orange')
            plt.plot(df['time'], df[c_ema200], label='EMA200', color='blue')
            plt.plot(df['time'], df[c_bbu], 'g--', alpha=0.3)
            plt.plot(df['time'], df[c_bbl], 'r--', alpha=0.3)
        except: pass

        plt.title(f"{SYMBOL} Analysis (Thai V14)")
        plt.legend(); plt.grid(True, alpha=0.3)
        buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0); plt.close()
        return buf
    except: return None

# ================= 3. ระบบวิเคราะห์ซับซ้อน (LOGIC MODULES) =================

# --- A. วิเคราะห์โครงสร้างตลาด (V13 Logic) ---
def analyze_market_structure():
    # 1. เทรนด์ใหญ่ H1
    h1 = mt5.copy_rates_from_pos(SYMBOL, TF_TREND, 0, 200)
    df1 = pd.DataFrame(h1)
    df1.ta.ema(length=50, append=True); df1.ta.ema(length=200, append=True)
    c50 = [c for c in df1.columns if c.startswith('EMA_50')][0]
    c200 = [c for c in df1.columns if c.startswith('EMA_200')][0]
    trend = 1 if df1[c50].iloc[-1] > df1[c200].iloc[-1] else -1

    # 2. ATR & SR
    m15 = mt5.copy_rates_from_pos(SYMBOL, TF_TRADE, 0, SR_LOOKBACK+20)
    df2 = pd.DataFrame(m15)
    df2.ta.atr(length=ATR_PERIOD, append=True)
    atr_val = df2[f'ATRr_{ATR_PERIOD}'].iloc[-1]
    point = mt5.symbol_info(SYMBOL).point
    atr_pts = atr_val / point
    
    res = df2['high'].rolling(SR_LOOKBACK).max().iloc[-1]
    sup = df2['low'].rolling(SR_LOOKBACK).min().iloc[-1]

    return {"trend_h1": trend, "atr_points": atr_pts, "support": sup, "resistance": res}

# --- B. วิเคราะห์ข่าว (V12 Logic) ---
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

# --- C. รายงานผลภาษาไทย (V12 Logic) ---
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

# --- D. ติดตามสัญญาณ (V12 Logic) ---
def monitor_active_signal():
    global current_signal
    if not current_signal: return
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        curr = tick.bid if current_signal['side'] == "BUY" else tick.ask
        s = current_signal
        
        hit_sl = (s['side']=="BUY" and curr<=s['sl']) or (s['side']=="SELL" and curr>=s['sl'])
        hit_tp2 = (s['side']=="BUY" and curr>=s['tp2']) or (s['side']=="SELL" and curr<=s['tp2'])
        
        if hit_sl: tg_send(f"😭 <b>ตัดขาดทุน (SL)</b> @ {curr:.2f}"); current_signal=None; return
        if hit_tp2: tg_send(f"🏆 <b>ทำกำไรสูงสุด (TP2)</b> @ {curr:.2f}"); current_signal=None; return

        if ((s['side']=="BUY" and curr>=s['tp1']) or (s['side']=="SELL" and curr<=s['tp1'])) and 'TP1' not in s['alerted']:
            tg_send(f"🎯 <b>เก็บกำไรไม้แรก (TP1)</b> @ {curr:.2f}"); s['alerted'].append('TP1')
    except: pass

# ================= 4. การส่งคำสั่ง (EXECUTION) =================
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
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": SYMBOL, "volume": float(lot), "type": mt5.ORDER_TYPE_BUY if side=="BUY" else mt5.ORDER_TYPE_SELL, "price": price, "magic": MAGIC, "deviation": 20, "comment": reason}
    res = mt5.order_send(req)
    
    if res.retcode == mt5.TRADE_RETCODE_DONE and not is_grid: 
        # --- คำนวณ TP/SL เพื่อโชว์ในรายงาน (Display Only) ---
        pt = mt5.symbol_info(SYMBOL).point
        if side == "BUY":
            tp1 = price + 500 * pt
            tp2 = price + 1000 * pt
            sl  = price - 800 * pt
        else:
            tp1 = price - 500 * pt
            tp2 = price - 1000 * pt
            sl  = price + 800 * pt
            
        tg_send(f"✅ <b>บอทเปิดออเดอร์ {side} แล้ว!</b> @ {price:.2f}\n🎯 เป้า 1: {tp1:.2f}\n🎯 เป้า 2: {tp2:.2f}\n🛑 ยอมแพ้: {sl:.2f}\nเหตุผล: {reason}")
        
        if side == "BUY": tg_send_photo(generate_chart()) # ส่งกราฟให้ดูเฉพาะขา Buy
        
    return res

def send_signal_only(side, price, detail):
    global current_signal
    pt = mt5.symbol_info(SYMBOL).point
    tp1, tp2, sl = (price + 500*pt, price + 1000*pt, price - 800*pt) if side=="BUY" else (price - 500*pt, price - 1000*pt, price + 800*pt)
    current_signal = {'side': side, 'tp1': tp1, 'tp2': tp2, 'sl': sl, 'alerted': []}
    icon = "🔵" if side == "BUY" else "🟠"
    tg_send(f"{icon} <b>สัญญาณ {side} มาแล้ว!</b> @ {price:.2f}\n🎯 เป้า 1: {tp1:.2f}\n🎯 เป้า 2: {tp2:.2f}\n🛑 ยอมแพ้: {sl:.2f}\n{detail}")
    tg_send_photo(generate_chart())

# ================= 5. ลูปทำงานหลัก (MAIN LOOP) =================
if not mt5.initialize(): quit()
log("🚀 ระบบ UTOPIA HYBRID BOT เริ่มทำงานแล้ว")

try:
    while True:
        # --- 1. อัปเดตข้อมูลตลาด (Smart Context) ---
        try:
            market_context = analyze_market_structure()
        except: pass

        # --- 2. ส่งรายงานอัตโนมัติ ---
        now = datetime.now()
        if now.strftime("%H:%M") == AUTO_REPORT_TIME and last_summary_date != now.date():
            tg_send(get_daily_report()); last_summary_date = now.date()

        # --- 3. คำสั่ง Telegram ---
        if "ใส่" not in TELEGRAM_TOKEN:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                r = requests.get(url, params={"offset": last_update_id + 1}, timeout=1).json()
                for u in r.get("result", []):
                    last_update_id = u["update_id"]
                    if "message" in u and "text" in u["message"]:
                        cmd = u["message"]["text"].lower()
                        if cmd == "/chart": 
                            tg_send("📸 กำลังโหลดกราฟ...")
                            img = generate_chart(); tg_send_photo(img) if img else tg_send("❌ สร้างกราฟไม่สำเร็จ")
                        elif cmd.startswith("/setlot"):
                            try: BASE_LOT = float(cmd.split()[1]); tg_send(f"✅ ปรับขนาดล็อตเป็น: {BASE_LOT} Lot")
                            except: pass

                        elif cmd.startswith("/setnews"):
                            try:
                                new_key = cmd.split()[1]
                                NEWS_API_KEY = new_key
                                tg_send(f"✅ บันทึก News Key แล้ว!\nKey: {new_key[:5]}...")
                            except: tg_send("❌ พิมพ์ผิด! ตัวอย่าง: /setnews xxxxxxxx")
                        elif cmd == "/be": c=set_breakeven(); tg_send(f"🛡️ ตั้งบังทุนสำเร็จ: {c} ไม้")
                        elif cmd == "/status":
                            trend = "ขาขึ้น 🟢" if market_context['trend_h1']==1 else "ขาลง 🔴"
                            atr = max(MIN_GRID_DIST, market_context['atr_points']*ATR_MULTIPLIER)
                            news = "⛔ ติดข่าว (ห้ามเทรด)" if news_blocked else "✅ ปกติ"
                            tg_send(f"📊 <b>สถานะระบบปัจจุบัน</b>\n━━━━━━━━━━━━\n🕹️ <b>โหมด:</b> {MODE} | 📰 <b>ข่าว:</b> {news}\n🌊 <b>เทรนด์ใหญ่ H1:</b> {trend}\n📏 <b>ระยะแก้ไม้ ATR:</b> {atr:.0f} จุด\n🧱 <b>แนวรับ/ต้าน:</b> {market_context['support']:.1f} / {market_context['resistance']:.1f}")
                        elif cmd == "/report": tg_send(get_daily_report())
                        elif cmd == "/auto": MODE="AUTO"; tg_send("🤖 เปลี่ยนเป็นโหมด: AUTO")
                        elif cmd == "/semi": MODE="SEMI"; tg_send("🖐️ เปลี่ยนเป็นโหมด: SEMI")
                        elif cmd == "/closeall": close_all_positions(); tg_send("⛔ ปิดรวบทุกไม้แล้ว")
            except: pass

        if MODE == "SEMI": monitor_active_signal()

        # --- 4. Logic Loop ---
        if time.time() >= next_trade_time:
            pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
            
            # A. ดูแลออเดอร์เก่า (Manage)
            if pos:
                net_p = sum(p.profit + p.swap for p in pos)
                if net_p >= BASKET_TP:
                    close_all_positions(); tg_send(f"💰 <b>ปิดรวบกำไร (Basket TP): ${net_p:.2f}</b>"); next_trade_time = time.time() + COOLDOWN_SEC
                elif len(pos) < MAX_GRID:
                    # Dynamic Grid
                    last = pos[-1]; t = mt5.symbol_info_tick(SYMBOL)
                    grid_dist = max(MIN_GRID_DIST, market_context['atr_points'] * ATR_MULTIPLIER)
                    
                    dist = (last.price_open - t.bid)/mt5.symbol_info(SYMBOL).point if last.type==0 else (t.ask - last.price_open)/mt5.symbol_info(SYMBOL).point
                    if dist >= grid_dist: 
                        execute_trade("BUY" if last.type==0 else "SELL", last.volume, f"แก้ไม้ (ATR {grid_dist:.0f})", is_grid=True)
            
            # B. หาจังหวะเข้าใหม่ (New Signal)
            else:
                deep_news_analysis() # เช็คข่าว
                if not news_blocked:
                    tick = mt5.symbol_info_tick(SYMBOL)
                    if (tick.ask - tick.bid)/mt5.symbol_info(SYMBOL).point <= MAX_SPREAD:
                        r = mt5.copy_rates_from_pos(SYMBOL, TF_TRADE, 0, 300)
                        df = pd.DataFrame(r)
                        df.ta.ema(50, append=True); df.ta.ema(200, append=True)
                        df.ta.rsi(14, append=True); df.ta.bbands(20, append=True)
                        try:
                            # Basic Signal
                            c_ema50 = [c for c in df.columns if c.startswith('EMA_50')][0]
                            c_ema200 = [c for c in df.columns if c.startswith('EMA_200')][0]
                            c_rsi = [c for c in df.columns if c.startswith('RSI')][0]
                            c_bbl = [c for c in df.columns if c.startswith('BBL')][0]
                            c_bbu = [c for c in df.columns if c.startswith('BBU')][0]

                            sig = 0
                            if df['close'].iloc[-1] < df[c_bbl].iloc[-1] and df[c_rsi].iloc[-1] < 30: sig = 1
                            elif df['close'].iloc[-1] > df[c_bbu].iloc[-1] and df[c_rsi].iloc[-1] > 70: sig = -1
                            
                            # Filters (MTF + SR)
                            if sig == 1 and market_context['trend_h1'] == -1: sig = 0
                            if sig == -1 and market_context['trend_h1'] == 1: sig = 0
                            
                            pt = mt5.symbol_info(SYMBOL).point
                            if sig == 1 and (market_context['resistance'] - tick.ask)/pt < SR_BUFFER: sig = 0
                            if sig == -1 and (tick.bid - market_context['support'])/pt < SR_BUFFER: sig = 0

                            if sig != 0:
                                side = "BUY" if sig > 0 else "SELL"
                                detail = f"คอนเฟิร์มเทรนด์ H1 | ระยะแก้ไม้: {market_context['atr_points']*ATR_MULTIPLIER:.0f} จุด"
                                if MODE == "AUTO": execute_trade(side, BASE_LOT, detail)
                                else: 
                                    send_signal_only(side, tick.ask if sig>0 else tick.bid, detail)
                                    next_trade_time = time.time() + SIGNAL_PAUSE_SEC
                        except: pass
        time.sleep(1)

except KeyboardInterrupt: pass
finally: mt5.shutdown()

