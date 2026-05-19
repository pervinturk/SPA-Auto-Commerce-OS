# -*- coding: utf-8 -*-
import os
import time
import threading
from typing import Optional, Callable, Any


GEMINI_KEYS_DEFAULT: list[str] = []

PRIMARY_MODEL  = os.environ.get("GEMINI_MODEL_PRIMARY",  "gemini-2.5-flash")
SECONDARY_MODEL = os.environ.get("GEMINI_MODEL_SECONDARY", "gemini-2.5-pro")
EXPERIMENTAL_MODEL = os.environ.get("GEMINI_MODEL_EXP", "gemini-2.0-flash")

DEFAULT_COOLDOWN_SECONDS = 60
DEFAULT_RETRY_DELAY      = 0.5
DEFAULT_MAX_RETRIES      = 4


class KeyPool:
    def __init__(self, keys: Optional[list[str]] = None):
        env_keys = os.environ.get("GEMINI_API_KEYS", "")
        if env_keys.strip():
            self._keys = [k.strip() for k in env_keys.split(",") if k.strip()]
        else:
            self._keys = list(keys or GEMINI_KEYS_DEFAULT)
        self._idx = 0
        self._lock = threading.RLock()
        self._cooldowns: dict[str, float] = {}
        self._stats: dict[str, dict] = {
            k: {"calls": 0, "errors": 0, "last_used": 0.0} for k in self._keys
        }

    @property
    def size(self) -> int:
        return len(self._keys)

    def current(self) -> str:
        with self._lock:
            return self._keys[self._idx]

    def get_available(self) -> Optional[str]:
        now = time.time()
        with self._lock:
            for _ in range(len(self._keys)):
                k = self._keys[self._idx]
                cd = self._cooldowns.get(k, 0.0)
                if cd <= now:
                    self._stats[k]["last_used"] = now
                    return k
                self._idx = (self._idx + 1) % len(self._keys)
            soonest_k, soonest_t = min(self._cooldowns.items(),
                                          key=lambda kv: kv[1])
            wait = max(0.0, soonest_t - now)
            return None if wait > 30 else soonest_k

    def advance(self) -> str:
        with self._lock:
            self._idx = (self._idx + 1) % len(self._keys)
            return self._keys[self._idx]

    def mark_rate_limited(self, key: str,
                            cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS):
        with self._lock:
            self._cooldowns[key] = time.time() + cooldown_seconds
            self._stats.setdefault(key, {"calls": 0, "errors": 0,
                                            "last_used": 0.0})
            self._stats[key]["errors"] += 1
            self.advance()

    def mark_success(self, key: str):
        with self._lock:
            self._stats.setdefault(key, {"calls": 0, "errors": 0,
                                            "last_used": 0.0})
            self._stats[key]["calls"] += 1
            self._cooldowns.pop(key, None)

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            return {
                "size":        len(self._keys),
                "current_idx": self._idx,
                "available":   sum(1 for k in self._keys
                                    if self._cooldowns.get(k, 0) <= now),
                "cooling":     sum(1 for k in self._keys
                                    if self._cooldowns.get(k, 0) > now),
                "by_key":      [
                    {
                        "key_suffix":  k[-6:],
                        "calls":       self._stats.get(k, {}).get("calls", 0),
                        "errors":      self._stats.get(k, {}).get("errors", 0),
                        "cooldown_in": max(0, self._cooldowns.get(k, 0) - now),
                    }
                    for k in self._keys
                ],
            }


_pool: Optional[KeyPool] = None
_pool_lock = threading.Lock()


def get_pool() -> KeyPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = KeyPool()
    return _pool


def _is_rate_limit_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(t in s for t in ("429", "rate limit", "quota", "exhausted",
                                  "resource_exhausted", "too many"))


def call_with_rotation(prompt_fn: Callable[[str, str], Any],
                          model: str = PRIMARY_MODEL,
                          max_retries: int = DEFAULT_MAX_RETRIES,
                          delay_between: float = DEFAULT_RETRY_DELAY
                          ) -> Any:
    pool = get_pool()
    if pool.size == 0:
        raise RuntimeError("Gemini key pool boş")
    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        key = pool.get_available()
        if key is None:
            time.sleep(3.0)
            key = pool.current()
        try:
            result = prompt_fn(key, model)
            pool.mark_success(key)
            return result
        except Exception as exc:
            last_error = exc
            if _is_rate_limit_error(exc):
                pool.mark_rate_limited(key, DEFAULT_COOLDOWN_SECONDS)
                time.sleep(delay_between)
                continue
            raise
    raise last_error if last_error else RuntimeError("Rotation tükendi")


def call_with_rotation_async(prompt_fn: Callable[[str, str], Any],
                                callback: Callable[[Any, Optional[str]], None],
                                model: str = PRIMARY_MODEL,
                                max_retries: int = DEFAULT_MAX_RETRIES):
    def _run():
        try:
            result = call_with_rotation(prompt_fn, model=model,
                                          max_retries=max_retries)
            callback(result, None)
        except Exception as exc:
            callback(None, str(exc))
    threading.Thread(target=_run, daemon=True).start()


__all__ = [
    "KeyPool", "get_pool", "call_with_rotation", "call_with_rotation_async",
    "PRIMARY_MODEL", "SECONDARY_MODEL", "EXPERIMENTAL_MODEL",
    "GEMINI_KEYS_DEFAULT",
]
