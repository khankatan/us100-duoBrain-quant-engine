import os
import time
import zipfile
import requests
import pandas as pd
import yfinance as yf
from engine.config import HISTORY_CSV

def to_unix_seconds(series):
    return (pd.to_datetime(series, utc=True).astype("int64") // 10**9).astype(int)

def load_ftmo_file(filepath: str, mt5_server_tz: str = 'Europe/Athens') -> pd.DataFrame:
    """อ่านไฟล์ CSV หรือ ZIP ของ FTMO MT5 อัตโนมัติ และจัดฟอร์แมตให้ตรงกับ DuoBrain"""
    def _read_csv_robust(file_obj):
        for enc in ('utf-8-sig', 'utf-16', 'latin1'):
            for sep in ('\t', ',', ';'):
                try:
                    if hasattr(file_obj, 'seek'):
                        file_obj.seek(0)
                    tmp = pd.read_csv(file_obj, sep=sep, encoding=enc)
                    if tmp.shape[1] >= 5:
                        return tmp
                except Exception:
                    continue
        raise ValueError(f"ไม่สามารถอ่านไฟล์ CSV จาก {filepath} ได้")

    if str(filepath).lower().endswith('.zip'):
        with zipfile.ZipFile(filepath, 'r') as z:
            csv_names = [
                n for n in z.namelist()
                if n.lower().endswith('.csv') and '__MACOSX' not in n and not n.split('/')[-1].startswith('._')
            ]
            if not csv_names:
                raise ValueError(f"ไม่พบไฟล์ .csv ใน {filepath}")
            with z.open(csv_names[0]) as f:
                df = _read_csv_robust(f)
    else:
        df = _read_csv_robust(filepath)

    df.columns = [c.strip().strip('<>').lower() for c in df.columns]

    if 'date' in df.columns and 'time' in df.columns:
        dt_series = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
        df['datetime'] = (
            dt_series
            .dt.tz_localize(mt5_server_tz, ambiguous='NaT', nonexistent='shift_forward')
            .dt.tz_convert('UTC')
        )
        df = df.dropna(subset=['datetime']).reset_index(drop=True)
    else:
        time_col = next((c for c in ['datetime', 'timestamp', 'time', 'date'] if c in df.columns), None)
        if time_col is None:
            raise ValueError(f"ไม่พบคอลัมน์เวลาในไฟล์ (คอลัมน์ที่มี: {list(df.columns)})")
        df['datetime'] = pd.to_datetime(df[time_col], utc=True)

    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df[['datetime', 'open', 'high', 'low', 'close']].dropna()
    df['ts'] = to_unix_seconds(df['datetime'])
    df = df.drop_duplicates(subset=['ts']).sort_values('ts').reset_index(drop=True)
    df = df[df['datetime'].dt.dayofweek < 5].reset_index(drop=True)
    return df

def fetch_market_data(custom_file_path=None):
    # หากระบุไฟล์ FTMO (ทั้ง .csv หรือ .zip) ให้โหลดจากไฟล์นั้นโดยตรงทันที
    if custom_file_path and os.path.exists(custom_file_path):
        df = load_ftmo_file(custom_file_path)
        return df, f"FTMO Local File ({os.path.basename(custom_file_path)})"

    # --- โค้ดดึงข้อมูลเดิมของโปรเจค DuoBrain (เผื่อใช้รัน Live บน VPS) ---
    os.makedirs(os.path.dirname(HISTORY_CSV), exist_ok=True)
    # ... (คงโค้ดส่วนดึง TwelveData เดิมไว้ด้านล่างนี้ได้เลย) ...
