import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests
import time

# ==========================================
# ⚙️ ตั้งค่า Telegram (ใส่ของจริงตรงนี้)
# ==========================================
TELEGRAM_TOKEN    = "8268781368:AAEf7PFO84pX4G_5b6h_xasHe-MBu2zCLWU" # ใส่Tokenของคุณ
TELEGRAM_CHAT_ID  = "-1003531261082"  # ใส่ChatIDของคุณ

# ==========================================
# ⚙️ Simulation Settings
# ==========================================
np.random.seed(42)
START_PRICE = 2000.0
LOT_SIZE = 0.05
COMMISSION = 0.07

# Logic V31 (Relaxed)
ADX_THRESHOLD = 15
EMA_PERIOD = 200
SL_BUFFER = 0.5
TRAIL_STEP_MULT = 0.5

# ==========================================
# 🛠️ ฟังก์ชันส่ง Telegram
# ==========================================
def tg_send(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        print(f"Send Error: {e}")

print("📡 กำลังเชื่อมต่อ Telegram...")
tg_send("🚀 <b>START BACKTEST SIMULATION</b>\nเริ่มการทดสอบระบบส่งข้อความ...")

# ==========================================
# 1. สร้างข้อมูลจำลอง
# ==========================================
print("🔄 สร้างข้อมูลตลาด...")
phase1 = np.random.normal(0, 1.0, 800)    
phase2 = np.random.normal(2.5, 3.0, 800)  
phase3 = np.random.normal(-0.5, 4.0, 600) 
phase4 = np.random.normal(-3.0, 3.5, 800) 

changes = np.concatenate([phase1, phase2, phase3, phase4])
prices = START_PRICE + np.cumsum(changes) 
real_periods = len(prices)

data = {
    'close': prices,
    'open': prices + np.random.normal(0, 1.0, real_periods),
    'high': prices + np.abs(np.random.normal(0, 2.0, real_periods)),
    'low': prices - np.abs(np.random.normal(0, 2.0, real_periods))
}
df = pd.DataFrame(data)
df['high'] = df[['open', 'close', 'high']].max(axis=1)
df['low'] = df[['open', 'close', 'low']].min(axis=1)

# ==========================================
# 2. คำนวณอินดิเคเตอร์
# ==========================================
df['EMA_200'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
df['tr0'] = abs(df['high'] - df['low'])
df['tr1'] = abs(df['high'] - df['close'].shift(1))
df['tr2'] = abs(df['low'] - df['close'].shift(1))
df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
df['ATR'] = df['tr'].rolling(window=14).mean()

df['up'] = df['high'] - df['high'].shift(1)
df['down'] = df['low'].shift(1) - df['low']
df['posDM'] = np.where((df['up'] > df['down']) & (df['up'] > 0), df['up'], 0)
df['negDM'] = np.where((df['down'] > df['up']) & (df['down'] > 0), df['down'], 0)
window = 14
df['S_TR'] = df['tr'].ewm(alpha=1/window, adjust=False).mean()
df['S_posDM'] = df['posDM'].ewm(alpha=1/window, adjust=False).mean()
df['S_negDM'] = df['negDM'].ewm(alpha=1/window, adjust=False).mean()
df['posDI'] = (df['S_posDM'] / df['S_TR']) * 100
df['negDI'] = (df['S_negDM'] / df['S_TR']) * 100
df['DX'] = (abs(df['posDI'] - df['negDI']) / (df['posDI'] + df['negDI'])) * 100
df['ADX'] = df['DX'].ewm(alpha=1/window, adjust=False).mean()

df.dropna(inplace=True)
df.reset_index(drop=True, inplace=True)

# ==========================================
# 3. Backtest Loop (With Notification)
# ==========================================
print("🚀 เริ่มรันพร้อมส่งแจ้งเตือน (อาจใช้เวลานานนิดนึง)...")

balance = 1000.0
active_trade = None
trade_count = 0

# เพื่อไม่ให้รอนานเกินไป จะจำลองแค่ 500 แท่งแรกพอนะครับ (ถ้าจะเอาหมดให้แก้เป็น len(df))
# หรือถ้าอยากเทสแค่ว่าส่งได้ไหม ลองแก้เป็น range(2, 100)
limit_candles = len(df) 

for i in range(2, limit_candles):
    curr = df.iloc[i]
    prev = df.iloc[i-1]
    
    # --- A. Exit Logic ---
    if active_trade:
        t = active_trade
        closed = False
        result = 0
        reason = ""
        atr = t['atr']
        
        if t['side'] == 'BUY':
            if (curr['high'] - t['entry']) >= (atr * 1.0):
                new_sl = curr['high'] - (atr * TRAIL_STEP_MULT)
                if new_sl > t['sl']: t['sl'] = new_sl
            
            if curr['low'] <= t['sl']:
                result = (t['sl'] - t['entry']) * LOT_SIZE * 100 
                closed = True
                reason = "Trailing Win" if t.get('status') else "SL Cut"

        else: # SELL
            if (t['entry'] - curr['low']) >= (atr * 1.0):
                new_sl = curr['low'] + (atr * TRAIL_STEP_MULT)
                if new_sl < t['sl']: t['sl'] = new_sl
            
            if curr['high'] >= t['sl']:
                result = (t['entry'] - t['sl']) * LOT_SIZE * 100
                closed = True
                reason = "Trailing Win" if t.get('status') else "SL Cut"
        
        if closed:
            net_profit = result - COMMISSION
            balance += net_profit
            emoji = "✅" if net_profit > 0 else "❌"
            
            # 🔥 แจ้งเตือนปิดออเดอร์
            msg = (f"{emoji} <b>SIMULATION: Closed {t['side']}</b>\n"
                   f"Price: {t['entry']:.2f} -> {t['sl']:.2f}\n"
                   f"Profit: ${net_profit:.2f}\n"
                   f"Reason: {reason}")
            print(f"Send Close: {net_profit:.2f}")
            tg_send(msg)
            
            active_trade = None
            time.sleep(0.1) # ⚠️ หน่วงเวลาป้องกันโดนบล็อค

    # --- B. Entry Logic ---
    if active_trade is None:
        if curr['ADX'] > ADX_THRESHOLD:
            # BUY
            if (curr['close'] > curr['EMA_200']) and (curr['close'] > prev['high']):
                sl = curr['low'] - SL_BUFFER
                active_trade = {'side': 'BUY', 'entry': curr['close'], 'sl': sl, 'atr': curr['ATR']}
                
                # 🔥 แจ้งเตือนเปิดออเดอร์
                msg = (f"🔵 <b>SIMULATION: Open BUY</b>\n"
                       f"Price: {curr['close']:.2f}\n"
                       f"SL: {sl:.2f}\n"
                       f"ADX: {curr['ADX']:.1f}")
                print("Send Open BUY")
                tg_send(msg)
                trade_count += 1
                time.sleep(0.1) # ⚠️ หน่วงเวลา

            # SELL
            elif (curr['close'] < curr['EMA_200']) and (curr['close'] < prev['low']):
                sl = curr['high'] + SL_BUFFER
                active_trade = {'side': 'SELL', 'entry': curr['close'], 'sl': sl, 'atr': curr['ATR']}
                
                # 🔥 แจ้งเตือนเปิดออเดอร์
                msg = (f"🔴 <b>SIMULATION: Open SELL</b>\n"
                       f"Price: {curr['close']:.2f}\n"
                       f"SL: {sl:.2f}\n"
                       f"ADX: {curr['ADX']:.1f}")
                print("Send Open SELL")
                tg_send(msg)
                trade_count += 1
                time.sleep(0.1) # ⚠️ หน่วงเวลา

# สรุปจบ
tg_send(f"🏁 <b>BACKTEST FINISHED</b>\nTotal Trades: {trade_count}\nFinal Balance: ${balance:,.2f}")
print("Done.")