import os
import time
import zipfile
import requests
import pandas as pd
import yfinance as yf
from engine.config import HISTORY_CSV

def to_unix_seconds(series):
    return (pd.to_datetime(series, utc=True).astype("int64") // 10**9).astype(int)

def load_ftmo_file(filepath: str, mt5_server_tz: str = "Europe/Athens") -> pd.DataFrame:
    """อ่านไฟล์ CSV หรือ ZIP ของ FTMO MT5 อัตโนมัติ (ใช้เฉพาะ OHLC ไม่ใช้ Volume)"""
    def _read_csv_robust(file_obj):
        for enc in ("utf-8-sig", "utf-16", "latin1"):
            for sep in ("\t", ",", ";"):
                try:
                    if hasattr(file_obj, "seek"):
                        file_obj.seek(0)
                    tmp = pd.read_csv(file_obj, sep=sep, encoding=enc)
                    if tmp.shape[1] >= 5:
                        return tmp
                except Exception:
                    continue
        raise ValueError(f"ไม่สามารถอ่านไฟล์ CSV จาก {filepath} ได้")

    if str(filepath).lower().endswith(".zip"):
        with zipfile.ZipFile(filepath, "r") as z:
            csv_names = [
                n for n in z.namelist()
                if n.lower().endswith(".csv") and "__MACOSX" not in n and not n.split("/")[-1].startswith("._")
            ]
            if not csv_names:
                raise ValueError(f"ไม่พบไฟล์ .csv ใน {filepath}")
            with z.open(csv_names[0]) as f:
                df = _read_csv_robust(f)
    else:
        df = _read_csv_robust(filepath)

    # ล้างช่องว่างและเครื่องหมาย < > ออกจากหัวตาราง
    df.columns = [c.strip().strip("<>").lower() for c in df.columns]

    # แปลงเวลา Server MT5 (Europe/Athens) เป็น UTC+0
    if "date" in df.columns and "time" in df.columns:
        dt_series = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
        df["datetime"] = (
            dt_series
            .dt.tz_localize(mt5_server_tz, ambiguous="NaT", nonexistent="shift_forward")
            .dt.tz_convert("UTC")
        )
        df = df.dropna(subset=["datetime"]).reset_index(drop=True)
    else:
        time_col = next((c for c in ["datetime", "timestamp", "time", "date"] if c in df.columns), None)
        if time_col is None:
            raise ValueError(f"ไม่พบคอลัมน์เวลาในไฟล์ (คอลัมน์ที่มี: {list(df.columns)})")
        df["datetime"] = pd.to_datetime(df[time_col], utc=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # คัดเฉพาะ OHLC ไม่นำคอลัมน์ tickvol/vol มาใช้
    df = df[["datetime", "open", "high", "low", "close"]].dropna()
    df["ts"] = to_unix_seconds(df["datetime"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    df = df[df["datetime"].dt.dayofweek < 5].reset_index(drop=True)
    return df

def fetch_twelvedata_page(api_key, end_date_str=None, outputsize=5000):
    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval=15min&outputsize={outputsize}&apikey={api_key}"
    if end_date_str:
        url += f"&end_date={end_date_str}"
    res = requests.get(url, timeout=30).json()
    if "values" not in res:
        print(f"TwelveData Note: {res.get('message', res)}")
        return pd.DataFrame()
    df_p = pd.DataFrame(res["values"])
    df_p["datetime"] = pd.to_datetime(df_p["datetime"], utc=True)
    for col in ["open", "high", "low", "close"]:
        df_p[col] = pd.to_numeric(df_p[col], errors="coerce")
    return df_p[["datetime", "open", "high", "low", "close"]].dropna()

def fetch_market_data(custom_file_path=None):
    # หากระบุไฟล์ FTMO (ทั้ง .csv หรือ .zip) ให้โหลดจากไฟล์นั้นโดยตรงทันที
    if custom_file_path and os.path.exists(custom_file_path):
        df = load_ftmo_file(custom_file_path)
        return df, f"FTMO Local File ({os.path.basename(custom_file_path)})"

    os.makedirs(os.path.dirname(HISTORY_CSV), exist_ok=True)
    api_key = os.getenv("TWELVE_DATA_KEY", "").strip()
    new_df = pd.DataFrame()
    source_name = "Yahoo Finance (Free Feed)"

    existing_rows = 0
    if os.path.exists(HISTORY_CSV):
        try:
            tmp_old = pd.read_csv(HISTORY_CSV)
            existing_rows = len(tmp_old)
        except Exception:
            existing_rows = 0

    if api_key:
        try:
            if existing_rows >= 18000:
                df_page = fetch_twelvedata_page(api_key, None, outputsize=30)
                if not df_page.empty:
                    new_df = df_page
                    source_name = "TwelveData Spot XAU/USD (Live Real-Time Sync)"
            else:
                pages_to_fetch = 5
                all_pages = []
                end_cursor = None

                for p in range(pages_to_fetch):
                    df_page = fetch_twelvedata_page(api_key, end_cursor, outputsize=5000)
                    if df_page.empty:
                        break
                    all_pages.append(df_page)
                    oldest_dt = df_page["datetime"].min()
                    end_cursor = (oldest_dt - pd.Timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
                    if p < pages_to_fetch - 1:
                        time.sleep(8.5)

                if all_pages:
                    new_df = pd.concat(all_pages, ignore_index=True)
                    source_name = "TwelveData Spot XAU/USD (1-Year Deep History)"
        except Exception as e:
            print(f"Warning Twelve Data Request Failed: {e}")

    if new_df.empty and os.path.exists(HISTORY_CSV):
        old_df = pd.read_csv(HISTORY_CSV)
        old_df["datetime"] = pd.to_datetime(old_df["datetime"], utc=True)
        for col in ["open", "high", "low", "close"]:
            old_df[col] = pd.to_numeric(old_df[col], errors="coerce")
        new_df = old_df[["datetime", "open", "high", "low", "close"]].dropna()
        source_name = str(old_df["source"].iloc[-1]) if "source" in old_df.columns else "Cached Spot XAU/USD"

    if new_df.empty:
        ticker = yf.Ticker("GC=F")
        df_y = ticker.history(period="60d", interval="15m").reset_index()
        time_col = "Datetime" if "Datetime" in df_y.columns else "Date"
        df_y["datetime"] = pd.to_datetime(df_y[time_col], utc=True)
        new_df = df_y.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close"})[["datetime", "open", "high", "low", "close"]].dropna()
        source_name = "Yahoo Finance GC=F (Fallback)"

    new_df["ts"] = to_unix_seconds(new_df["datetime"])

    if os.path.exists(HISTORY_CSV):
        try:
            old_df = pd.read_csv(HISTORY_CSV)
            if "source" in old_df.columns and "TwelveData" in str(old_df["source"].iloc[-1]) and "TwelveData" in source_name:
                old_df["datetime"] = pd.to_datetime(old_df["datetime"], utc=True)
                old_df["ts"] = to_unix_seconds(old_df["datetime"])
                combined = pd.concat([old_df[["datetime", "ts", "open", "high", "low", "close"]], new_df], ignore_index=True)
            else:
                combined = new_df
        except Exception:
            combined = new_df
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    combined = combined[combined["datetime"].dt.dayofweek < 5].reset_index(drop=True)
    combined["source"] = source_name
    combined.to_csv(HISTORY_CSV, index=False)
    return combined, source_name
