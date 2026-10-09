import time
from datetime import datetime, timezone
import MetaTrader5 as mt5

TIMEFRAME_INFO = {
    'M1': (mt5.TIMEFRAME_M1, 60, "1 Minute"),
    'M2': (mt5.TIMEFRAME_M2, 120, "2 Minutes"),
    'M3': (mt5.TIMEFRAME_M3, 180, "3 Minutes"),
    'M4': (mt5.TIMEFRAME_M4, 240, "4 Minutes"),
    'M5': (mt5.TIMEFRAME_M5, 300, "5 Minutes"),
    'M6': (mt5.TIMEFRAME_M6, 360, "6 Minutes"),
    'M10': (mt5.TIMEFRAME_M10, 600, "10 Minutes"),
    'M12': (mt5.TIMEFRAME_M12, 720, "12 Minutes"),
    'M15': (mt5.TIMEFRAME_M15, 900, "15 Minutes"),
    'M20': (mt5.TIMEFRAME_M20, 1200, "20 Minutes"),
    'M30': (mt5.TIMEFRAME_M30, 1800, "30 Minutes"),
    'H1': (mt5.TIMEFRAME_H1, 3600, "1 Hour"),
    'H2': (mt5.TIMEFRAME_H2, 7200, "2 Hours"),
    'H3': (mt5.TIMEFRAME_H3, 10800, "3 Hours"),
    'H4': (mt5.TIMEFRAME_H4, 14400, "4 Hours"),
    'H6': (mt5.TIMEFRAME_H6, 21600, "6 Hours"),
    'H8': (mt5.TIMEFRAME_H8, 28800, "8 Hours"),
    'H12': (mt5.TIMEFRAME_H12, 43200, "12 Hours"),
    'D1': (mt5.TIMEFRAME_D1, 86400, "1 Day"),
    'W1': (mt5.TIMEFRAME_W1, 604800, "1 Week"),
    'MN1': (mt5.TIMEFRAME_MN1, 2592000, "1 Month"),
}

TIMEFRAME_ALIASES = {
    '1M': 'M1', 'M1': 'M1', '1MIN': 'M1', '1': 'M1',
    '2M': 'M2', 'M2': 'M2',
    '3M': 'M3', 'M3': 'M3',
    '4M': 'M4', 'M4': 'M4',
    '5M': 'M5', 'M5': 'M5', '5MIN': 'M5', '5': 'M5',
    '6M': 'M6', 'M6': 'M6',
    '10M': 'M10', 'M10': 'M10',
    '12M': 'M12', 'M12': 'M12',
    '15M': 'M15', 'M15': 'M15', '15MIN': 'M15', '15': 'M15',
    '20M': 'M20', 'M20': 'M20',
    '30M': 'M30', 'M30': 'M30', '30MIN': 'M30', '30': 'M30',
    '1H': 'H1', 'H1': 'H1', '60M': 'H1', '60': 'H1',
    '2H': 'H2', 'H2': 'H2',
    '3H': 'H3', 'H3': 'H3',
    '4H': 'H4', 'H4': 'H4', '240M': 'H4', '240': 'H4',
    '6H': 'H6', 'H6': 'H6',
    '8H': 'H8', 'H8': 'H8',
    '12H': 'H12', 'H12': 'H12',
    '1D': 'D1', 'D1': 'D1', 'DAY': 'D1', 'DAILY': 'D1', 'D': 'D1',
    '1W': 'W1', 'W1': 'W1', 'WEEK': 'W1', 'WEEKLY': 'W1', 'W': 'W1',
    '1MN': 'MN1', 'MN1': 'MN1', 'MN': 'MN1', 'MONTH': 'MN1', 'MONTHLY': 'MN1'
}

TIMEFRAME_MAP = {k: v[0] for k, v in TIMEFRAME_INFO.items()}

def parse_timeframe(tf_str):
    if not tf_str:
        return 'M1', mt5.TIMEFRAME_M1, 60
    cleaned = str(tf_str).strip().upper()
    canonical = TIMEFRAME_ALIASES.get(cleaned, cleaned)
    if canonical in TIMEFRAME_INFO:
        const, secs, _ = TIMEFRAME_INFO[canonical]
        return canonical, const, secs
    supported = ", ".join(TIMEFRAME_INFO.keys())
    raise ValueError(f"Unsupported timeframe '{tf_str}'. Supported timeframes: {supported}")

def parse_datetime_flexible(val):
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        ts = float(val)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts)
    val_str = str(val).strip()
    try:
        ts = float(val_str)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse datetime '{val}'. Use ISO 8601 (e.g. 2026-10-09T08:00:00) or UNIX timestamp.")

def fetch_rates_advanced(symbol, timeframe="M1", count=500, start_pos=0, start_time=None, end_time=None, include_forming=True):
    tf_name, tf_const, tf_seconds = parse_timeframe(timeframe)
    count = max(1, int(count))
    start_pos = max(0, int(start_pos))
    dt_start = parse_datetime_flexible(start_time)
    dt_end = parse_datetime_flexible(end_time)

    mt5.symbol_select(symbol, True)

    raw_rates = None
    query_mode = "position"

    if dt_start and dt_end:
        query_mode = "range"
        raw_rates = mt5.copy_rates_range(symbol, tf_const, dt_start, dt_end)
    elif dt_start and not dt_end:
        query_mode = "time_from"
        raw_rates = mt5.copy_rates_from(symbol, tf_const, dt_start, count)
    else:
        query_mode = "position"
        if count <= 50000:
            raw_rates = mt5.copy_rates_from_pos(symbol, tf_const, start_pos, count)
        else:
            chunks = []
            remaining = count
            current_offset = start_pos
            while remaining > 0:
                fetch_n = min(remaining, 50000)
                sub_rates = mt5.copy_rates_from_pos(symbol, tf_const, current_offset, fetch_n)
                if sub_rates is None or len(sub_rates) == 0:
                    break
                chunks.append(sub_rates)
                current_offset += len(sub_rates)
                remaining -= len(sub_rates)
                if len(sub_rates) < fetch_n:
                    break
            if chunks:
                import numpy as np
                raw_rates = np.concatenate(chunks)
            else:
                raw_rates = None

    if raw_rates is None or len(raw_rates) == 0:
        return {
            "status": "ok",
            "symbol": symbol,
            "timeframe": tf_name,
            "timeframe_seconds": tf_seconds,
            "query_mode": query_mode,
            "count": 0,
            "offset": start_pos,
            "has_more": False,
            "next_offset": start_pos,
            "time_start": None,
            "time_end": None,
            "forming_bar": None,
            "data": []
        }

    tick = mt5.symbol_info_tick(symbol)
    market_time = int(tick.time) if tick else int(time.time())

    total_len = len(raw_rates)
    records = []
    for i, r in enumerate(raw_rates):
        bar_time = int(r['time'])
        is_closed = (i < total_len - 1) or ((bar_time + tf_seconds) <= market_time)
        o = float(r['open'])
        h = float(r['high'])
        l = float(r['low'])
        c = float(r['close'])
        change = round(c - o, 6)
        change_pct = round((change / o) * 100, 4) if o > 0 else 0.0
        amplitude = round(h - l, 6)

        records.append({
            "time": datetime.fromtimestamp(bar_time).strftime('%Y-%m-%d %H:%M:%S'),
            "timestamp": bar_time,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "tick_volume": int(r['tick_volume']),
            "spread": int(r['spread']),
            "real_volume": int(r['real_volume']) if 'real_volume' in r.dtype.names else 0,
            "is_closed": is_closed,
            "change": change,
            "change_pct": change_pct,
            "amplitude": amplitude
        })

    if not include_forming and records and not records[-1]['is_closed']:
        records.pop()

    has_more = (len(records) == count and query_mode == "position")
    next_offset = (start_pos + len(records)) if query_mode == "position" else None
    forming_bar = records[-1] if (records and not records[-1]['is_closed']) else None

    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": tf_name,
        "timeframe_seconds": tf_seconds,
        "query_mode": query_mode,
        "count": len(records),
        "offset": start_pos,
        "has_more": has_more,
        "next_offset": next_offset,
        "time_start": records[0]['time'] if records else None,
        "time_end": records[-1]['time'] if records else None,
        "forming_bar": forming_bar,
        "data": records
    }
