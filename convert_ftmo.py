import pandas as pd

# 1. ระบุชื่อไฟล์ที่โหลดมาจาก FTMO MT5
ftmo_file = "XAUUSD_M15_202501020100_202611202345.csv"
output_file = "data/xauusd_m15_history.csv"

# 2. อ่านไฟล์ (MT5 Export ใช้ Tab คั่น)
df = pd.read_csv(ftmo_file, sep="\t")

# ล้างเครื่องหมาย < > ออกจากชื่อคอลัมน์และทำเป็นตัวพิมพ์เล็ก
df.columns = [c.strip("<>").lower() for c in df.columns]

# 3. รวม date และ time เป็น datetime
dt_str = df["date"].astype(str) + " " + df["time"].astype(str)
dt_server = pd.to_datetime(dt_str, format="%Y.%m.%d %H:%M:%S")

# 4. แปลงเวลาเซิร์ฟเวอร์ FTMO (Europe/Athens = GMT+2/GMT+3 อัตโนมัติ) เป็น UTC 
# เพื่อให้ indicators.py (+7 ชม. เป็นเวลาไทย) คำนวณ Session และเวลาเทรดได้ตรงเป๊ะ
df["datetime"] = dt_server.dt.tz_localize("Europe/Athens", ambiguous="infer").dt.tz_convert("UTC")

# 5. จัดเรียงคอลัมน์ให้ตรงกับ data_feed.py และเพิ่มป้ายกำกับ source
df["ts"] = (df["datetime"].astype("int64") // 10**9).astype(int)
df["source"] = "FTMO MT5 History (2-Year)"

cols = ["datetime", "ts", "open", "high", "low", "close", "source"]
df_clean = df[cols].dropna().drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)

df_clean.to_csv(output_file, index=False)
print(f"แปลงไฟล์สำเร็จ! จำนวนแท่งเทียนทั้งหมด: {len(df_clean):,} แท่ง -> บันทึกที่ {output_file}")
