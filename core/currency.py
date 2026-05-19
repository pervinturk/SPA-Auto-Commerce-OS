import json
import threading
import urllib.request
from datetime import datetime, timedelta
from core import database as db

_observers = []
_current = "TRY"
_rate_usd_try = 34.50
_last_fetch = None
_lock = threading.Lock()


def load():
    global _current, _rate_usd_try, _last_fetch
    _current = db.get_setting("currency", "TRY") or "TRY"
    cached = db.get_setting("usd_try_rate")
    cached_at = db.get_setting("usd_try_rate_at")
    if cached:
        try:
            _rate_usd_try = float(cached)
        except Exception:
            pass
    if cached_at:
        try:
            _last_fetch = datetime.fromisoformat(cached_at)
        except Exception:
            pass
    threading.Thread(target=_refresh_async, daemon=True).start()


def _refresh_async():
    global _rate_usd_try, _last_fetch
    if _last_fetch and (datetime.now() - _last_fetch) < timedelta(hours=6):
        return
    rate = _fetch_rate()
    if rate:
        with _lock:
            _rate_usd_try = rate
            _last_fetch = datetime.now()
            db.set_setting("usd_try_rate", str(rate))
            db.set_setting("usd_try_rate_at", _last_fetch.isoformat())
        for cb in _observers:
            try:
                cb()
            except Exception:
                pass


def _fetch_rate():
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d.get("rates", {}).get("TRY")),
        ("https://api.exchangerate-api.com/v4/latest/USD", lambda d: d.get("rates", {}).get("TRY")),
    ]
    for url, parser in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            r = parser(data)
            if r and 10 < float(r) < 200:
                return float(r)
        except Exception:
            continue
    return None


def get() -> str:
    return _current


def set(code: str):
    global _current
    if code not in ("TRY", "USD"):
        return
    _current = code
    db.set_setting("currency", code)
    for cb in _observers:
        try:
            cb()
        except Exception:
            pass


def subscribe(cb):
    _observers.append(cb)


def rate_usd_try() -> float:
    return _rate_usd_try


def format(amount_try: float, decimals: int = 2) -> str:
    if _current == "USD":
        v = amount_try / _rate_usd_try if _rate_usd_try else 0
        return f"${v:,.{decimals}f}"
    return f"{amount_try:,.{decimals}f} TL"


def symbol() -> str:
    return "$" if _current == "USD" else "TL"


def to_current(amount_try: float) -> float:
    if _current == "USD":
        return amount_try / _rate_usd_try if _rate_usd_try else 0
    return amount_try
