# -*- coding: utf-8 -*-
import os
import threading
from typing import Callable, Optional

from core import database as db


MODE_MOCK     = "MOCK"
MODE_LIVE     = "LIVE"
MODE_HYBRID   = "HYBRID"

_DEFAULT_MODE = os.environ.get("EAAS_DATA_MODE", MODE_LIVE).upper()
if _DEFAULT_MODE not in (MODE_MOCK, MODE_LIVE, MODE_HYBRID):
    _DEFAULT_MODE = MODE_LIVE


class DataModeManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._mode = _DEFAULT_MODE
        self._subscribers: list[Callable[[str], None]] = []
        self._last_sync: dict[str, str] = {}
        self._sync_errors: dict[str, str] = {}

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def set_mode(self, mode: str):
        mode = (mode or "").upper()
        if mode not in (MODE_MOCK, MODE_LIVE, MODE_HYBRID):
            return
        with self._lock:
            if self._mode == mode:
                return
            self._mode = mode
        self._notify()

    def subscribe(self, callback: Callable[[str], None]):
        with self._lock:
            self._subscribers.append(callback)

    def _notify(self):
        with self._lock:
            subs = list(self._subscribers)
            m = self._mode
        for s in subs:
            try:
                s(m)
            except Exception:
                pass

    def record_sync(self, source: str, ts: str,
                       error: Optional[str] = None):
        with self._lock:
            self._last_sync[source] = ts
            if error:
                self._sync_errors[source] = error
            else:
                self._sync_errors.pop(source, None)

    def sync_status(self) -> dict:
        with self._lock:
            return {
                "mode":      self._mode,
                "last_sync": dict(self._last_sync),
                "errors":    dict(self._sync_errors),
            }


_manager: Optional[DataModeManager] = None
_manager_lock = threading.Lock()


def get_manager() -> DataModeManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = DataModeManager()
    return _manager


def is_live_mode() -> bool:
    return get_manager().mode in (MODE_LIVE, MODE_HYBRID)


def is_mock_mode() -> bool:
    return get_manager().mode == MODE_MOCK


def clear_local_inventory() -> dict:
    """Lokal envanteri ve finansal mock verisini sıfırla. FK kapatılıp tek
    transaction'da silinir. Marketplace, profil, tedarikçi, materials,
    bildirim AYARLARI korunur."""
    import sqlite3
    counts: dict = {}
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        conn.execute("PRAGMA foreign_keys = OFF")
        cur = conn.cursor()
        tables_to_clear = [
            "transactions", "agent_actions",
            "order_items", "order_reviews", "orders",
            "bom", "products",
        ]
        for t in tables_to_clear:
            try:
                cur.execute(f"DELETE FROM {t}")
                counts[t] = cur.rowcount
            except sqlite3.OperationalError as exc:
                counts[f"{t}_skip"] = str(exc)[:80]
        try:
            cur.execute("DELETE FROM notifications WHERE target_sku IS NOT NULL")
            counts["notifications_targeted"] = cur.rowcount
        except sqlite3.OperationalError as exc:
            counts["notifications_skip"] = str(exc)[:80]
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()
        counts["ok"] = True
    except Exception as exc:
        counts["error"] = str(exc)[:160]
        counts["ok"] = False
    return counts


def empty_state_message(source: str, hint: str = "") -> str:
    base = (f"Henüz {source} verisi yok. ")
    if hint:
        base += hint
    else:
        base += ("Üst kısımdaki 'Trendyol'dan Senkronize Et' "
                  "butonuna basarak gerçek satıcı paneli verilerinizi "
                  "çekebilirsiniz.")
    return base


__all__ = [
    "MODE_MOCK", "MODE_LIVE", "MODE_HYBRID",
    "DataModeManager", "get_manager",
    "is_live_mode", "is_mock_mode",
    "clear_local_inventory", "empty_state_message",
]
