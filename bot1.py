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
import nltk
nltk.download('vader_lexicon', quiet=True)

# --- เพิ่ม Library ที่จำเป็นต้องใช้ (ห้ามลบ) ---
import sys
import json
import os
# -------------------------------------------

expire_date = datetime(2026, 1, 10) # ตั้งวันหมดอายุ (ปี, เดือน, วัน)
if datetime.now() > expire_date:
    print("❌ หมดเวลาทดสอบแล้วครับ! โปรดติดต่อ Anapat")
    time.sleep(10)
    sys.exit() # คำสั่งนี้จะปิดโปรแกรมทันที ไม่ให้โค้ดด้านล่างทำงานต่อ

# ==========================================
# 2. ส่วนระบบจัดการ Token (/settoken)
# ==========================================
CONFIG_FILE = "config.json" # ชื่อไฟล์ที่จะใช้เก็บ Token

def save_token(token):
    """ฟังก์ชันบันทึก Token ลงไฟล์"""
    data = {"user_token": token}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    print(f"✅ บันทึก Token เรียบร้อยแล้ว! (บันทึกลง {CONFIG_FILE})")

def load_token():
    """ฟังก์ชันอ่าน Token จากไฟล์"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("user_token")
        except:
            return None
    return None

# --- ตรวจสอบคำสั่ง /settoken จาก Arguments ---
if len(sys.argv) > 2 and sys.argv[1] == "/settoken":
    new_token = sys.argv[2]
    save_token(new_token)
    print("กรุณารันโปรแกรมใหม่อีกครั้งเพื่อเริ่มทำงาน")
    sys.exit()

# --- โหลด Token มาใช้งาน ---
my_token = load_token()

# ถ้ายังไม่มี Token ให้ถาม user
if not my_token:
    print("⚠️ ยังไม่พบ Token ในระบบ")
    user_input = input("กรุณากรอก Token ของคุณ: ")
    if user_input.strip():
        save_token(user_input.strip())
        my_token = user_input.strip()
    else:
        print("❌ คุณไม่ได้กรอก Token โปรแกรมจะปิดตัวลง")
        time.sleep(3)
        sys.exit()

# ==========================================
# 3. ส่วนการทำงานหลัก (Main Program)
# ==========================================
print(f"🔑 กำลังใช้งานด้วย Token: {my_token}")
print("🚀 เริ่มต้นระบบบอท...")

# ================= 1. ตั้งค่าระบบ (CONFIGURATION) =================
SYMBOL      = "XAUUSD"
TF_TRADE    = mt5.TIMEFRAME_M15  # เทรดบน M15
TF_TREND    = mt5.TIMEFRAME_H1   # ดูเทรนด์ H1
BASE_LOT    = 0.01
MAX_GRID    = 5
MAGIC       = 99999

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

# --- ระบบบริหารกำไรแบบ Dynamic ---
last_capital = 0.0             # ยอดทุนเริ่มต้น (ดึงอัตโนมัติเมื่อเริ่มรัน)
WITHDRAW_PERCENT = 50.0        # เปอร์เซ็นต์กำไรที่แนะนำให้ถอน
MIN_PROFIT_TO_ADVISE = 10.0    # กำไรขั้นต่ำที่จะเริ่มแจ้งเตือน
has_notified_withdraw = False  # สถานะการแจ้งเตือน

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
# --- D. ติดตามสัญญาณ (V14 Tuned Logic) ---
def monitor_active_signal():
    global current_signal
    if not current_signal: return
    try:
        tick = mt5.symbol_info_tick(SYMBOL)
        tick_price = tick.bid if current_signal['side'] == "BUY" else tick.ask
        s = current_signal
        side = s['side']
        
        # --- ดึงค่า ATR มาใช้คำนวณจุดแจ้งเตือน ---
        pt = mt5.symbol_info(SYMBOL).point
        atr_price = market_context.get('atr_points', 0) * pt

        # === ระบบ AUTO/SEMI EXECUTION ALERT (Logic Add-on) ===
        if side == "BUY":
            # เช็ค TP1 (1.0 * ATR)
            if tick_price >= s['tp1'] and 'TP1' not in s['alerted']:
                tg_send(f"🎯 <b>AUTO TP1 HIT</b>\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
                s['alerted'].append('TP1')
            
            # เช็ค TP2 (2.0 * ATR)
            if tick_price >= s['tp2']:
                tg_send(f"🎯 <b>AUTO TP2 HIT</b>\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
                current_signal = None; return
                
            # เช็ค SL (1.5 * ATR)
            if tick_price <= s['sl']:
                tg_send(f"🛑 <b>AUTO SL HIT</b>\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
                current_signal = None; return

        else: # ขา SELL
            # เช็ค TP1 (1.0 * ATR)
            if tick_price <= s['tp1'] and 'TP1' not in s['alerted']:
                tg_send(f"🎯 <b>AUTO TP1 HIT</b>\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")
                s['alerted'].append('TP1')
                
            # เช็ค TP2 (2.0 * ATR)
            if tick_price <= s['tp2']:
                tg_send(f"🎯 <b>AUTO TP2 HIT</b>\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")
                current_signal = None; return
                
            # เช็ค SL (1.5 * ATR)
            if tick_price >= s['sl']:
                tg_send(f"🛑 <b>AUTO SL HIT</b>\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")
                current_signal = None; return
                
    except Exception as e:
        log(f"Monitor Signal Error: {e}")

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
    # --- คำนวณ ATR ในหน่วยราคา (Price) สำหรับใช้ใน ADD-ON Logic ---
    pt = mt5.symbol_info(SYMBOL).point
    atr_price = market_context.get('atr_points', 0) * pt
    
    # === ใช้ Logic จาก send_semi_signal_addon ===
    if side == "BUY":
        tp1 = price + (atr_price * 1.0)
        tp2 = price + (atr_price * 2.0)
        sl  = price - (atr_price * 1.5)
    else:
        tp1 = price - (atr_price * 1.0)
        tp2 = price - (atr_price * 2.0)
        sl  = price + (atr_price * 1.5)
        
    current_signal = {'side': side, 'tp1': tp1, 'tp2': tp2, 'sl': sl, 'alerted': []}
    
    # --- ปรับรูปแบบข้อความเป็น SEMI TRADE PLAN ---
    msg = (
        "📣 <b>SEMI TRADE PLAN</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"{'🟢 BUY' if side=='BUY' else '🔴 SELL'} {SYMBOL}\n"
        f"📍 Entry: {price:.2f}\n\n"
        f"🎯 TP1: {tp1:.2f}\n"
        f"🎯 TP2: {tp2:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💡 {detail}"
    )
    
    tg_send(msg)
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

        # --- ระบบคำนวณถอนกำไรแบบ Dynamic ---
        try:
            acc = mt5.account_info()
            if acc is not None:
                if last_capital == 0: last_capital = acc.balance
                total_profit = acc.balance - last_capital
                
                if total_profit >= MIN_PROFIT_TO_ADVISE and not has_notified_withdraw:
                    withdraw_amount = total_profit * (WITHDRAW_PERCENT / 100)
                    remain_in_port = acc.balance - withdraw_amount
                    msg = (
                        "💰 <b>แจ้งเตือนบริหารกำไร (Dynamic)</b>\n"
                        f"📈 กำไรสะสม: <b>${total_profit:,.2f}</b>\n"
                        f"💸 <b>ควรพิจารณาถอน: ${withdraw_amount:,.2f}</b>\n"
                        f"🛡️ ทุนคงเหลือ: ${remain_in_port:,.2f}\n"
                        "💡 กด <code>/resetcapital</code> หลังถอนเสร็จ"
                    )
                    tg_send(msg)
                    has_notified_withdraw = True
            
            if datetime.now().strftime("%H:%M") == "00:00": has_notified_withdraw = False
        except: pass

        # --- 2. ส่งรายงานอัตโนมัติ --- (ของเดิมที่มีอยู่แล้ว)
        
        # --- 2. ส่งรายงานอัตโนมัติ ---
        now = datetime.now()
        if now.strftime("%H:%M") == AUTO_REPORT_TIME and last_summary_date != now.date():
            tg_send(get_daily_report()); last_summary_date = now.date()

        # --- 3. คำสั่ง Telegram ---
        # --- 3. คำสั่ง Telegram ---
        if "ใส่" not in TELEGRAM_TOKEN:
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
                r = requests.get(url, params={"offset": last_update_id + 1}, timeout=1).json()
                for u in r.get("result", []):
                    last_update_id = u["update_id"]
                    if "message" in u and "text" in u["message"]:
                        cmd = u["message"]["text"].lower()
                        
                        # ================= เช็คคำสั่ง Telegram =================
                        if cmd == "/chart": 
                            tg_send("📸 กำลังโหลดกราฟ...")
                            img = generate_chart(); tg_send_photo(img) if img else tg_send("❌ สร้างกราฟไม่สำเร็จ")
                        
                        elif cmd == "/buy":
                            tg_send("⚡ รับคำสั่ง: เปิดไม้ BUY เดี๋ยวนี้!")
                            res = execute_trade("BUY", BASE_LOT, "Manual Telegram /buy")
                            if res.retcode != mt5.TRADE_RETCODE_DONE:
                                tg_send(f"❌ เปิดไม่สำเร็จ Error: {res.comment}")

                        elif cmd == "/sell":
                            tg_send("⚡ รับคำสั่ง: เปิดไม้ SELL เดี๋ยวนี้!")
                            res = execute_trade("SELL", BASE_LOT, "Manual Telegram /sell")
                            if res.retcode != mt5.TRADE_RETCODE_DONE:
                                tg_send(f"❌ เปิดไม่สำเร็จ Error: {res.comment}")

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

                        elif cmd == "/resetcapital":
                            acc = mt5.account_info()
                            if acc:
                                last_capital = acc.balance
                                has_notified_withdraw = False 
                                tg_send(f"🔄 <b>รีเซ็ตทุนเริ่มต้นสำเร็จ!</b>\n💰 ทุนใหม่ตั้งต้นที่: ${last_capital:,.2f}")
                            else:
                                tg_send("❌ ไม่สามารถดึงข้อมูลบัญชีได้")
                        
                        elif cmd == "/status":
                            # === ส่วนที่ปรับปรุงใหม่ (Status Addon) ===
                            acc = mt5.account_info()
                            pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)
                            trend = market_context.get("trend_h1", "N/A")
                            atr = market_context.get("atr_points", 0)
                            
                            dd = 0
                            if acc and acc.balance > 0:
                                dd = (acc.balance - acc.equity) / acc.balance * 100
                            
                            msg = (
                                "📊 UTOPIA STATUS\n"
                                "━━━━━━━━━━━━━━\n"
                                f"🕹️ Mode: {MODE}\n"
                                f"📈 Trend H1: {'BUY 🟢' if trend == 1 else 'SELL 🔴'}\n"
                                f"📏 ATR: {atr:.0f} pts\n\n"
                                f"💰 Balance: ${acc.balance:,.2f}\n"
                                f"📊 Equity:  ${acc.equity:,.2f}\n"
                                f"📉 Drawdown: {dd:.2f}%\n"
                                f"🧮 Positions: {len(pos) if pos else 0}"
                            )
                            tg_send(msg)
                            # ========================================
                        
                        elif cmd == "/report": tg_send(get_daily_report())
                        elif cmd == "/auto": MODE="AUTO"; tg_send("🤖 เปลี่ยนเป็นโหมด: AUTO")
                        elif cmd == "/semi": MODE="SEMI"; tg_send("🖐️ เปลี่ยนเป็นโหมด: SEMI")
                        elif cmd == "/closeall": close_all_positions(); tg_send("⛔ ปิดรวบทุกไม้แล้ว")
                        # ====================================================
            except Exception as e:
                log(f"Telegram Error: {e}")
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
            
           # B. ระบบโหวตหาจังหวะเข้าใหม่ (Scoring Vote System - 6 Factors)
            else:
                deep_news_analysis() # เช็คข่าว
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
                            
                            score = 0; side = ""; pt = mt5.symbol_info(SYMBOL).point
                            curr_close = df['close'].iloc[-1]; curr_rsi = df[c_rsi].iloc[-1]

                            # 🗳️ 1-2. เริ่มการโหวต Technical (2 คะแนน)
                            if curr_close < df[c_bbl].iloc[-1] and curr_rsi < 30: score += 2; side = "BUY"
                            elif curr_close > df[c_bbu].iloc[-1] and curr_rsi > 70: score += 2; side = "SELL"

                            if score >= 2:
                                # 🗳️ 3. โหวต Trend H1 (1 คะแนน)
                                if (side == "BUY" and market_context.get('trend_h1') == 1) or (side == "SELL" and market_context.get('trend_h1') == -1): score += 1
                                # 🗳️ 4. โหวต Distance EMA20 (1 คะแนน)
                                if (abs(curr_close - df[c_ema20].iloc[-1]) / pt) > 400: score += 1
                                # 🗳️ 5. โหวต SR Buffer (1 คะแนน)
                                if (side == "BUY" and (market_context['resistance'] - tick.ask)/pt >= SR_BUFFER) or (side == "SELL" and (tick.bid - market_context['support'])/pt >= SR_BUFFER): score += 1
                                
                                # 🗳️ 6. โหวต News Sentiment (เพิ่มคะแนนที่ 6)
                                if side == "BUY" and cached_news_score > 0: score += 1
                                elif side == "SELL" and cached_news_score < 0: score += 1

                            # --- ตัดสินใจผลการโหวต (ใช้เกณฑ์ 5/6 คะแนน) ---
                            if score >= 5:
                                conf_percent = (score / 6) * 100
                                detail = f"มั่นใจสูง: {conf_percent:.1f}% | โหวต: {score}/6"
                                
                                if MODE == "AUTO": execute_trade(side, BASE_LOT, detail)
                                else: 
                                    send_signal_only(side, tick.ask if side=="BUY" else tick.bid, detail)
                                    next_trade_time = time.time() + SIGNAL_PAUSE_SEC
                        except: pass
        time.sleep(1)

except KeyboardInterrupt: pass
finally: mt5.shutdown()

# =====================================================================
# ================= ADD-ON MODULE (NO TOUCH CORE ABOVE) ================
# =====================================================================

# -----------------------------
# 1) TELEGRAM /status OVERRIDE
# -----------------------------
def telegram_status_addon():
    acc = mt5.account_info()
    pos = mt5.positions_get(symbol=SYMBOL, magic=MAGIC)

    trend = market_context.get("trend_h1", "N/A")
    atr   = market_context.get("atr_points", 0)

    dd = 0
    if acc and acc.balance > 0:
        dd = (acc.balance - acc.equity) / acc.balance * 100

    msg = (
        "📊 UTOPIA STATUS\n"
        "━━━━━━━━━━━━━━\n"
        f"🔌 Mode: {MODE}\n"
        f"📈 Trend H1: {'BUY' if trend == 1 else 'SELL'}\n"
        f"📐 ATR: {atr:.0f} pts\n\n"
        f"💰 Balance: ${acc.balance:,.2f}\n"
        f"📊 Equity:  ${acc.equity:,.2f}\n"
        f"📉 DD: {dd:.2f}%\n"
        f"🧮 Positions: {len(pos) if pos else 0}"
    )
    tg_send(msg)


# -----------------------------
# 2) SEMI SIGNAL (ONE MESSAGE)
# -----------------------------
def send_semi_signal_addon(side, entry_price, atr_price):
    if side == "BUY":
        tp1 = entry_price + atr_price * 1.0
        tp2 = entry_price + atr_price * 2.0
        sl  = entry_price - atr_price * 1.5
    else:
        tp1 = entry_price - atr_price * 1.0
        tp2 = entry_price - atr_price * 2.0
        sl  = entry_price + atr_price * 1.5

    tg_send(
        "📣 SEMI TRADE PLAN\n"
        "━━━━━━━━━━━━━━\n"
        f"{'🟢 BUY' if side=='BUY' else '🔴 SELL'} {SYMBOL}\n"
        f"📍 Entry: {entry_price:.2f}\n\n"
        f"🎯 TP1: {tp1:.2f}\n"
        f"🎯 TP2: {tp2:.2f}\n"
        f"🛑 SL: {sl:.2f}"
    )


# --------------------------------------------------
# 3) AUTO EXECUTION ALERT (TP / SL HIT REAL PRICE)
# --------------------------------------------------
def auto_execution_alert_addon(avg_price, side, atr_price, tick_price):
    if side == "BUY":
        if tick_price >= avg_price + atr_price * 1.0:
            tg_send(f"🎯 AUTO TP1 HIT\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
        if tick_price >= avg_price + atr_price * 2.0:
            tg_send(f"🎯 AUTO TP2 HIT\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
        if tick_price <= avg_price - atr_price * FIRST_ORDER_SL_ATR:
            tg_send(f"🛑 AUTO SL HIT\nBUY {SYMBOL}\nPrice: {tick_price:.2f}")
    else:
        if tick_price <= avg_price - atr_price * 1.0:
            tg_send(f"🎯 AUTO TP1 HIT\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")
        if tick_price <= avg_price - atr_price * 2.0:
            tg_send(f"🎯 AUTO TP2 HIT\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")
        if tick_price >= avg_price + atr_price * FIRST_ORDER_SL_ATR:
            tg_send(f"🛑 AUTO SL HIT\nSELL {SYMBOL}\nPrice: {tick_price:.2f}")


# --------------------------------------------------
# 4) TELEGRAM COMMAND HOOK (NO CORE CHANGE)
# --------------------------------------------------
def telegram_command_addon(cmd):
    if cmd == "/status":
        telegram_status_addon()
        return True
    return False

# ==================================================
# END ADD-ON

# ==================================================

