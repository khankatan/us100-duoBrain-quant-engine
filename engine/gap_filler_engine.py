def evaluate_gap_filler(bar, prev, trades_today=0, lon_open=None, lon_close=None):
    utc_hour = int(bar["thai_hour"]) - 7
    if utc_hour < 0:
        utc_hour += 24

    utc_mins = utc_hour * 60 + int(bar["thai_minute"])
    close_p = float(bar["close"])
    open_p = float(bar["open"])
    vwap_p = float(bar["vwap"])
    atr_val = float(bar["atr"])
    atr_ratio = float(bar.get("atr_ratio", 1.0))
    chop_bar = float(bar.get("chop", 50.0))

    h1_bull = float(bar["h1_close"]) >= float(bar["h1_ema"])
    h1_bear = float(bar["h1_close"]) < float(bar["h1_ema"])
    h4_bull = float(bar["h4_close"]) >= float(bar["h4_ema"])
    h4_bear = float(bar["h4_close"]) < float(bar["h4_ema"])

    strong_uptrend = h1_bull and h4_bull and (chop_bar < 50.0)
    strong_downtrend = h1_bear and h4_bear and (chop_bar < 50.0)

    # 1. FLIP-SESSION: จบที่ 15:45, บล็อกชั่วโมง 14 และห้ามสวนเทรนด์แข็งแกร่ง (H1+H4 & CHOP < 50)
    if (13 * 60 + 30) <= utc_mins <= (15 * 60 + 45) and (utc_hour != 14) and chop_bar < 54.0:
        if lon_open is not None and lon_close is not None and atr_val > 0:
            lon_move = (lon_close - lon_open) / atr_val
            if (not strong_uptrend) and lon_move >= 1.0 and close_p < vwap_p and float(prev["close"]) >= float(prev["vwap"]) and close_p < open_p:
                return "SELL", "FLIP-SESSION"
            if (not strong_downtrend) and lon_move <= -1.0 and close_p > vwap_p and float(prev["close"]) <= float(prev["vwap"]) and close_p > open_p:
                return "BUY", "FLIP-SESSION"

    # 2. GAP-DAILY (London Open Continuation): เฉพาะ 16:00-16:45 (ลอนดอนเปิด) + H1&H4 ทิศทางเดียวกัน + ตลาดมีวอลุ่ม (atr_ratio >= 0.80)
    if trades_today == 0 and (16 * 60 + 0) <= utc_mins <= (16 * 60 + 45) and (atr_ratio >= 0.80):
        if h1_bull and h4_bull and close_p >= vwap_p and close_p > open_p:
            return "BUY", "GAP-DAILY"
        if h1_bear and h4_bear and close_p <= vwap_p and close_p < open_p:
            return "SELL", "GAP-DAILY"

    return None, ""
