# -*- coding: utf-8 -*-
import os
import json
import base64
import hashlib
import threading
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

from core import database as db


PLATFORM_TRENDYOL    = "trendyol"
PLATFORM_HEPSIBURADA = "hepsiburada"
PLATFORM_AMAZON      = "amazon"
PLATFORM_N11         = "n11"
PLATFORM_ETSY        = "etsy"

PLATFORM_LABELS = {
    PLATFORM_TRENDYOL:    "Trendyol",
    PLATFORM_HEPSIBURADA: "Hepsiburada",
    PLATFORM_AMAZON:      "Amazon",
    PLATFORM_N11:         "N11",
    PLATFORM_ETSY:        "Etsy",
}

PLATFORM_FIELDS = {
    PLATFORM_TRENDYOL: [
        ("seller_id",  "Satıcı ID (Cari ID) *",
         "Trendyol Partner panelinizdeki Cari ID. Zorunlu. Örn: 0"),
        ("api_key",    "API Anahtarı *",
         "Entegrasyon > API Bilgileri sekmesinden 20 karakterlik API Key. Zorunlu."),
        ("api_secret", "API Secret *",
         "API Anahtarınızla birlikte verilen Secret. Zorunlu."),
        ("integration_ref", "Entegrasyon Referans Kodu",
         "Trendyol panelinizdeki entegrasyon referans kodu (UUID formatı). "
         "İsteğe bağlı — bizim için audit/log amacıyla saklanır."),
        ("brand_id",   "Marka ID",
         "Marka Yönetimi sayfasından alınan ID. Boş bırakılırsa Cari ID kullanılır."),
        ("brand_name", "Marka Adı",
         "Görünür marka adı. Trendyol'da kayıtlı olan."),
    ],
    PLATFORM_HEPSIBURADA: [
        ("merchant_id", "Mağaza / Merchant ID",
         "Hepsiburada Mağaza Yönetiminden alınan ID"),
        ("username",    "Kullanıcı Adı",
         "Entegrasyon kullanıcı adı"),
        ("password",    "Şifre / API Token",
         "Entegrasyon şifresi veya API token"),
    ],
    PLATFORM_AMAZON: [
        ("seller_id",     "Seller Central ID",
         "Amazon Seller Central'dan alınan satıcı kimliği"),
        ("marketplace_id", "Marketplace ID",
         "A33AVAJ2PDY3EV (TR), A1PA6795UKMFR9 (DE), vb."),
        ("access_key",    "AWS Access Key",
         "SP-API IAM kullanıcı erişim anahtarı"),
        ("secret_key",    "AWS Secret Key",
         "AWS Access Key ile eşleşen Secret"),
        ("refresh_token", "LWA Refresh Token",
         "Login With Amazon refresh token"),
    ],
    PLATFORM_N11: [
        ("api_key",    "API Anahtarı",
         "N11.com Magaza Yönetiminden alınan anahtar"),
        ("api_secret", "API Secret",
         "API anahtarıyla birlikte verilen Secret"),
        ("store_code", "Mağaza Kodu",
         "N11 mağaza kodunuz"),
    ],
    PLATFORM_ETSY: [
        ("api_key",     "API Key",
         "Etsy Developer Portal'dan oluşturulan API Key"),
        ("shared_secret", "Shared Secret",
         "API Key ile birlikte verilen Secret"),
        ("shop_id",     "Shop ID",
         "Etsy mağaza ID'niz"),
    ],
}


_FERNET_AVAILABLE = False
_xor_master = None


def _derive_xor_key(passphrase: str = "spa-center-local-v1") -> bytes:
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def _xor_encode(plaintext: str, key: bytes = None) -> str:
    if key is None:
        key = _derive_xor_key()
    data = plaintext.encode("utf-8")
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    return base64.b64encode(bytes(out)).decode("ascii")


def _xor_decode(ciphertext: str, key: bytes = None) -> str:
    if key is None:
        key = _derive_xor_key()
    try:
        data = base64.b64decode(ciphertext.encode("ascii"))
    except Exception:
        return ""
    out = bytearray(len(data))
    for i, b in enumerate(data):
        out[i] = b ^ key[i % len(key)]
    try:
        return bytes(out).decode("utf-8")
    except UnicodeDecodeError:
        return ""


_lock = threading.RLock()


def _ensure_schema():
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS platform_credentials (
                platform     TEXT PRIMARY KEY,
                payload_enc  TEXT NOT NULL,
                configured   INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                last_verified TEXT,
                last_error   TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def save_credentials(platform: str, fields: dict,
                       verify_callback: Optional[Callable] = None) -> dict:
    platform = (platform or "").lower()
    if platform not in PLATFORM_FIELDS:
        return {"ok": False, "error": f"Bilinmeyen platform: {platform}"}
    _ensure_schema()
    payload = {k: str(v) for k, v in fields.items() if v not in (None, "")}
    enc = _xor_encode(json.dumps(payload, ensure_ascii=False))
    now = datetime.utcnow().isoformat()
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    with _lock:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute("""
                INSERT INTO platform_credentials(platform, payload_enc,
                    configured, created_at, updated_at)
                VALUES(?, ?, 1, ?, ?)
                ON CONFLICT(platform) DO UPDATE SET
                    payload_enc = excluded.payload_enc,
                    configured = 1,
                    updated_at = excluded.updated_at,
                    last_error = NULL
            """, (platform, enc, now, now))
            conn.commit()
        finally:
            conn.close()

    if verify_callback:
        try:
            verified, msg = verify_callback(payload)
            _record_verification(platform, verified, None if verified else msg)
            return {"ok": True, "saved": True,
                     "verified": bool(verified),
                     "message": msg or "",
                     "verify_error": None if verified else (msg or "")}
        except Exception as exc:
            _record_verification(platform, False, str(exc))
            return {"ok": True, "saved": True, "verified": False,
                     "message": str(exc), "verify_error": str(exc)}
    return {"ok": True, "saved": True, "verified": False,
             "message": "Kaydedildi (doğrulama yapılmadı)",
             "verify_error": None}


def get_credentials(platform: str) -> Optional[dict]:
    platform = (platform or "").lower()
    if platform not in PLATFORM_FIELDS:
        return None
    _ensure_schema()
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    with _lock:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            row = conn.execute(
                "SELECT payload_enc, configured FROM platform_credentials "
                "WHERE platform=?", (platform,)).fetchone()
        finally:
            conn.close()
    if not row or not row[1]:
        return None
    decoded = _xor_decode(row[0])
    if not decoded:
        return None
    try:
        return json.loads(decoded)
    except Exception:
        return None


def is_configured(platform: str) -> bool:
    return get_credentials(platform) is not None


def get_status(platform: str) -> dict:
    platform = (platform or "").lower()
    _ensure_schema()
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    with _lock:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            row = conn.execute(
                "SELECT configured, created_at, updated_at, last_verified, "
                "last_error FROM platform_credentials WHERE platform=?",
                (platform,)).fetchone()
        finally:
            conn.close()
    if not row:
        return {"platform": platform, "configured": False}
    return {
        "platform":      platform,
        "configured":    bool(row[0]),
        "created_at":    row[1],
        "updated_at":    row[2],
        "last_verified": row[3],
        "last_error":    row[4],
    }


def clear_credentials(platform: str) -> bool:
    platform = (platform or "").lower()
    _ensure_schema()
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    with _lock:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute("DELETE FROM platform_credentials WHERE platform=?",
                          (platform,))
            conn.commit()
        finally:
            conn.close()
    return True


def _record_verification(platform: str, ok: bool, error: Optional[str]):
    db_path = (getattr(db, "DB_PATH", None) or
                getattr(db, "_DB_PATH", None) or "eaas.db")
    now = datetime.utcnow().isoformat()
    with _lock:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            conn.execute(
                "UPDATE platform_credentials SET last_verified=?, last_error=? "
                "WHERE platform=?",
                (now if ok else None, error, platform))
            conn.commit()
        finally:
            conn.close()


def any_configured() -> bool:
    for p in PLATFORM_FIELDS.keys():
        if is_configured(p):
            return True
    return False


def list_configured() -> list[str]:
    return [p for p in PLATFORM_FIELDS.keys() if is_configured(p)]


def list_all() -> list[dict]:
    out = []
    for p in PLATFORM_FIELDS.keys():
        st = get_status(p)
        st["label"] = PLATFORM_LABELS.get(p, p)
        out.append(st)
    return out


__all__ = [
    "PLATFORM_TRENDYOL", "PLATFORM_HEPSIBURADA", "PLATFORM_AMAZON",
    "PLATFORM_N11", "PLATFORM_ETSY",
    "PLATFORM_LABELS", "PLATFORM_FIELDS",
    "save_credentials", "get_credentials", "is_configured",
    "get_status", "clear_credentials",
    "any_configured", "list_configured", "list_all",
]
