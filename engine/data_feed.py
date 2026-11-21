import os
import glob
import zipfile
import pandas as pd

def to_unix_seconds(series):
    return (pd.to_datetime(series, utc=True).astype("int64") // 10**9).astype(int)

def load_ftmo_file(filepath: str) -> pd.DataFrame:
    """อ่านไฟล์ ZIP (หรือ CSV) ของ FTMO MT5 อัตโนมัติ (ใช้เฉพาะ OHLC ไม่ใช้ Volume)"""
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
        raise ValueError(f"ไม่สามารถอ่านไฟล์ CSV ภายใน {filepath} ได้")

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

    # แปลงเวลา Server MT5 (FTMO = NY+7h) -> True UTC -> Australia/Sydney Clock (ตรงกับไฟล์ 58)
    if "date" in df.columns and "time" in df.columns:
        dt_series = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
        ny_naive = dt_series - pd.Timedelta(hours=7)
        true_utc = (
            ny_naive
            .dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
            .dt.tz_convert("UTC")
        )
        df["true_utc"] = true_utc
        # ปรับนาฬิกาให้ตรงกับฐานเวลาของไฟล์ 58 (Australia/Sydney labeled as UTC)
        df["datetime"] = (
            true_utc
            .dt.tz_convert("Australia/Sydney")
            .dt.tz_localize(None)
            .dt.tz_localize("UTC")
        )
        df = df.dropna(subset=["datetime", "true_utc"]).reset_index(drop=True)
    else:
        time_col = next((c for c in ["datetime", "timestamp", "time", "date"] if c in df.columns), None)
        if time_col is None:
            raise ValueError(f"ไม่พบคอลัมน์เวลาในไฟล์ (คอลัมน์ที่มี: {list(df.columns)})")
        df["datetime"] = pd.to_datetime(df[time_col], utc=True)
        df["true_utc"] = df["datetime"]

    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[["datetime", "true_utc", "open", "high", "low", "close"]].dropna()
    df["ts"] = to_unix_seconds(df["datetime"])
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    # ตัดเฉพาะวันเสาร์-อาทิตย์ตามเวลาตลาดจริง (true_utc) เพื่อไม่ให้ตัดคืนวันศุกร์ทิ้ง
    df = df[df["true_utc"].dt.dayofweek < 5].reset_index(drop=True)
    return df

def fetch_market_data(custom_file_path=None):
    """บังคับโหลดข้อมูลจากไฟล์ .zip เท่านั้น (ปิดการเชื่อมต่อ TwelveData / Yahoo 100%)"""
    target_path = custom_file_path

    if not target_path or not os.path.exists(target_path):
        zip_files = glob.glob("data/*.zip")
        if zip_files:
            target_path = zip_files[0]
        else:
            raise FileNotFoundError(
                f"ไม่พบไฟล์ .zip ในโฟลเดอร์ data/ (พาธที่ค้นหา: {target_path}) กรุณานำไฟล์ .zip ไปวางในโฟลเดอร์ data/"
            )

    print(f"กำลังโหลดข้อมูลกราฟจากไฟล์ ZIP: {target_path} ...")
    df = load_ftmo_file(target_path)
    source_name = f"FTMO ZIP ({os.path.basename(target_path)})"
    print(f"โหลดสำเร็จ! จำนวนทั้งหมด {len(df):,} แท่ง ({df.iloc[0]['datetime']} ถึง {df.iloc[-1]['datetime']})")
    return df, source_name
