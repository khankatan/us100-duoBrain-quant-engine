def evaluate_gap_filler(bar, prev, trades_today=0, lon_open=None, lon_close=None):
    utc_hour = int(bar["thai_hour"]) - 7
    if utc_hour < 0:
        utc_hour += 24

    utc_mins = utc_hour * 60 + int(bar["thai_minute"])
    close_p = float(bar["close"])
    open_p = float(bar["open"])
    vwap_p = float(bar["vwap"])
    atr_val = float(bar["atr"])
    chop_bar = float(bar.get("chop", 50.0))

    h1_bull = float(bar["h1_close"]) >= float(bar["h1_ema"])
    h1_bear = float(bar["h1_close"]) < float(bar["h1_ema"])

    # 1. FLIP-SESSION: จบที่ 15:45 (ตัดช่วง 16:00-16:30 ที่ขาดทุนหนักทั้ง 2 ปีออก)
    if (13 * 60 + 30) <= utc_mins <= (15 * 60 + 45) and chop_bar < 54.0:
        if lon_open is not None and lon_close is not None and atr_val > 0:
            lon_move = (lon_close - lon_open) / atr_val
            if lon_move >= 1.0 and close_p < vwap_p and float(prev["close"]) >= float(prev["vwap"]) and close_p < open_p:
                return "SELL", "FLIP-SESSION"
            if lon_move <= -1.0 and close_p > vwap_p and float(prev["close"]) <= float(prev["vwap"]) and close_p > open_p:
                return "BUY", "FLIP-SESSION"

    # 2. GAP-DAILY: เริ่ม 16:00 - 17:45 และปลดล็อกวัน ATR สูงเพื่อให้ออกไม้ครบทุกวัน (คุม Risk 0.12% ใน risk_manager)
    if trades_today == 0 and (16 * 60 + 0) <= utc_mins <= (17 * 60 + 45):
        if h1_bull and close_p >= vwap_p and close_p > open_p:
            return "BUY", "GAP-DAILY"
        if h1_bear and close_p <= vwap_p and close_p < open_p:
            return "SELL", "GAP-DAILY"

    return None, ""
