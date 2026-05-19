# -*- coding: utf-8 -*-
import os
import time
import json
import base64
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, Any

import requests

from core import database as db
from core.data_mode import get_manager

log = logging.getLogger("trendyol_sync")


def _get_creds() -> dict:
    try:
        from core.credentials import get_credentials, PLATFORM_TRENDYOL
        c = get_credentials(PLATFORM_TRENDYOL) or {}
    except Exception:
        c = {}
    return {
        "seller_id":  int(c.get("seller_id") or
                          os.environ.get("TRENDYOL_SELLER_ID") or 0),
        "api_key":    c.get("api_key") or os.environ.get("TRENDYOL_API_KEY") or "",
        "api_secret": c.get("api_secret") or os.environ.get("TRENDYOL_API_SECRET") or "",
        "brand_id":   c.get("brand_id"),
        "brand_name": c.get("brand_name"),
    }


def is_configured() -> bool:
    c = _get_creds()
    return bool(c["seller_id"] and c["api_key"] and c["api_secret"])


SELLER_ID  = int(os.environ.get("TRENDYOL_SELLER_ID")  or 0)
API_KEY    = os.environ.get("TRENDYOL_API_KEY")        or ""
API_SECRET = os.environ.get("TRENDYOL_API_SECRET")     or ""

BASE_INTEGRATION = "https://api.trendyol.com/integration"
BASE_SAPIGW      = "https://api.trendyol.com/sapigw"

REQUEST_TIMEOUT  = 25
MAX_RETRIES      = 3
RETRY_BACKOFF_S  = 2.5

RECOVERABLE_HTTP = {500, 502, 503, 504, 556, 599}


def _auth_headers() -> dict:
    creds = _get_creds()
    key = creds["api_key"] or API_KEY
    secret = creds["api_secret"] or API_SECRET
    seller = creds["seller_id"] or SELLER_ID
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "User-Agent":    f"{seller} - SPA_Center",
        "Accept":        "application/json",
        "Content-Type":  "application/json",
    }


def _seller_id() -> int:
    return _get_creds()["seller_id"] or SELLER_ID


class TrendyolSyncError(Exception):
    def __init__(self, message: str, status: int = 0,
                  recoverable: bool = False, body: Any = None):
        super().__init__(message)
        self.status = status
        self.recoverable = recoverable
        self.body = body


def _request(method: str, url: str, params: dict = None,
                json_body: Any = None) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.request(
                method=method, url=url, params=params, json=json_body,
                headers=_auth_headers(), timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_exc = TrendyolSyncError(f"Ağ hatası: {exc}", 0,
                                            recoverable=True)
            time.sleep(RETRY_BACKOFF_S * (attempt + 1))
            continue
        if 200 <= resp.status_code < 300:
            try:
                return resp.json() if resp.content else {}
            except ValueError:
                return {"raw_text": resp.text[:500]}
        if resp.status_code in RECOVERABLE_HTTP:
            try:
                body = resp.json()
            except ValueError:
                body = {"raw_text": resp.text[:500]}
            last_exc = TrendyolSyncError(
                f"Trendyol sunucu hatası ({resp.status_code}). "
                f"Bu hata bizim koddan değil, Trendyol sunucusundan kaynaklı "
                f"(genelde geçici). Detay: {body}",
                status=resp.status_code, recoverable=True, body=body)
            time.sleep(RETRY_BACKOFF_S * (attempt + 1))
            continue
        try:
            body = resp.json()
        except ValueError:
            body = {"raw_text": resp.text[:500]}
        raise TrendyolSyncError(
            f"Trendyol kalıcı hata ({resp.status_code}): {body}",
            status=resp.status_code, recoverable=False, body=body)
    raise last_exc or TrendyolSyncError("Bilinmeyen hata", 0, True)


def fetch_orders(start: datetime, end: datetime,
                    status: Optional[str] = None,
                    limit: int = 50) -> list[dict]:
    url = f"{BASE_INTEGRATION}/order/sellers/{_seller_id()}/orders"
    params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate":   int(end.timestamp() * 1000),
        "size":      limit,
        "page":      0,
        "orderByField":      "PackageLastModifiedDate",
        "orderByDirection":  "DESC",
    }
    if status:
        params["status"] = status
    data = _request("GET", url, params=params)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_settlements(start: datetime, end: datetime) -> dict:
    url = f"{BASE_INTEGRATION}/finance/cheques/details"
    params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate":   int(end.timestamp() * 1000),
    }
    return _request("GET", url, params=params)


def fetch_products(limit: int = 100) -> list[dict]:
    url = f"{BASE_SAPIGW}/suppliers/{_seller_id()}/products"
    params = {"size": limit, "page": 0}
    data = _request("GET", url, params=params)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_seller_info() -> dict:
    url = f"{BASE_SAPIGW}/suppliers/{_seller_id()}/addresses"
    data = _request("GET", url)
    info = {}
    addresses = []
    if isinstance(data, dict):
        addresses = data.get("supplierAddresses") or []
        if not addresses:
            addresses = data.get("content") or []
    elif isinstance(data, list):
        addresses = data
    primary = next((a for a in addresses if a.get("isDefault")), None) or \
                (addresses[0] if addresses else {})
    if primary:
        info["company_name"]  = primary.get("fullName", "")
        info["address"]       = primary.get("address", "")
        info["city"]          = (primary.get("city") or {}).get("name", "")
        info["district"]      = (primary.get("district") or {}).get("name", "")
        info["zip"]           = primary.get("postCode", "")
        info["email"]         = primary.get("email", "")
        info["phone"]         = primary.get("phone", "")
    info["seller_id"] = _seller_id()
    info["address_count"] = len(addresses)
    info["raw_addresses"] = addresses
    return info


def verify_credentials() -> tuple[bool, str]:
    sid = _seller_id()
    if not sid:
        return False, "Satıcı ID (Cari ID) boş — bu alan zorunludur."

    probes = [
        ("Ürünler",          f"{BASE_SAPIGW}/suppliers/{sid}/products",
         {"size": 1, "page": 0}),
        ("Sipariş listesi",  f"{BASE_INTEGRATION}/order/sellers/{sid}/orders",
         {"size": 1, "page": 0,
          "startDate": int((datetime.utcnow() -
                             timedelta(days=7)).timestamp() * 1000),
          "endDate":   int(datetime.utcnow().timestamp() * 1000)}),
        ("Adresler",         f"{BASE_SAPIGW}/suppliers/{sid}/addresses", None),
        ("Kargo firmaları",  f"{BASE_SAPIGW}/suppliers/{sid}/shipment-providers", None),
    ]

    successful: list[str] = []
    server_errors: list[str] = []
    permission_errors: list[str] = []
    auth_error: Optional[str] = None
    last_error: Optional[str] = None

    for label, url, params in probes:
        try:
            _request("GET", url, params=params)
            successful.append(label)
        except TrendyolSyncError as exc:
            last_error = f"{label}: {exc.status or 'no-status'}"
            if exc.status == 401:
                auth_error = (
                    "Trendyol 401 Unauthorized — API Key veya API Secret "
                    "hatalı, ya da Cari ID API Key ile eşleşmiyor. "
                    "Trendyol Partner > Entegrasyon Bilgilerim sayfasından "
                    "bilgileri yeniden kopyalayın.")
                break
            elif exc.status == 403:
                permission_errors.append(label)
            elif exc.status == 404:
                permission_errors.append(f"{label} (404)")
            elif exc.status in RECOVERABLE_HTTP:
                server_errors.append(f"{label} ({exc.status})")
            else:
                last_error = str(exc)[:240]
        except Exception as exc:
            last_error = str(exc)[:240]

    if successful:
        return True, (f"Bağlandı · Satıcı ID: {sid} · Erişilebilen "
                       f"endpoint'ler: {', '.join(successful)}")

    if auth_error:
        return False, auth_error

    if permission_errors and not server_errors:
        return False, (
            f"Bilgiler doğru ama hesabınız test endpoint'lerine "
            f"erişimi kısıtlı. Trendyol Partner > Entegrasyon Bilgilerim'den "
            f"rol/izinleri kontrol edin. (Reddedilenler: "
            f"{', '.join(permission_errors)})")

    if server_errors:
        return False, (
            f"Bilgiler kaydedildi ama Trendyol sunucusu geçici olarak yanıt "
            f"vermiyor: {', '.join(server_errors)}. Birkaç dakika sonra "
            "senkronizasyonu deneyin — bu Trendyol cephesindeki sorundur, "
            "sizin kodunuzdan değil.")

    return False, (last_error or "Bilinmeyen hata")


def fetch_supplier_addresses() -> list[dict]:
    url = f"{BASE_INTEGRATION}/sellers/{_seller_id()}/addresses"
    data = _request("GET", url)
    if isinstance(data, dict):
        return data.get("supplierAddresses") or data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_brands() -> list[dict]:
    url = f"{BASE_SAPIGW}/suppliers/{_seller_id()}/brands"
    data = _request("GET", url)
    if isinstance(data, dict):
        return data.get("brands") or data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_returns(start: datetime, end: datetime, limit: int = 50) -> list[dict]:
    url = f"{BASE_INTEGRATION}/order/sellers/{_seller_id()}/claims"
    params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate":   int(end.timestamp() * 1000),
        "size":      limit,
        "page":      0,
    }
    data = _request("GET", url, params=params)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_questions(start: datetime, end: datetime,
                      limit: int = 50) -> list[dict]:
    url = f"{BASE_INTEGRATION}/qna/sellers/{_seller_id()}/questions/filter"
    params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate":   int(end.timestamp() * 1000),
        "size":      limit,
        "page":      0,
        "status":    "WAITING_FOR_ANSWER",
    }
    data = _request("GET", url, params=params)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_shipment_providers() -> list[dict]:
    url = f"{BASE_INTEGRATION}/sellers/{_seller_id()}/shipment-providers"
    data = _request("GET", url)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def fetch_reviews(start: datetime, end: datetime,
                    limit: int = 50) -> list[dict]:
    url = (f"{BASE_INTEGRATION}/product/sellers/{_seller_id()}/"
           f"product-reviews")
    params = {
        "startDate": int(start.timestamp() * 1000),
        "endDate":   int(end.timestamp() * 1000),
        "size":      limit,
        "page":      0,
    }
    data = _request("GET", url, params=params)
    if isinstance(data, dict):
        return data.get("content") or []
    return data if isinstance(data, list) else []


def _normalize_order(raw: dict) -> dict:
    return {
        "id":             str(raw.get("orderNumber") or raw.get("id") or ""),
        "platform":       "Trendyol",
        "platform_color": "#F97316",
        "product":        ((raw.get("lines") or [{}])[0].get("productName") or ""),
        "sku":             ((raw.get("lines") or [{}])[0].get("merchantSku") or ""),
        "qty":             int((raw.get("lines") or [{}])[0].get("quantity") or 1),
        "total":           float(raw.get("totalPrice") or 0),
        "status":          str(raw.get("status") or "Bekliyor"),
        "customer":        f"{raw.get('customerFirstName','')} "
                            f"{raw.get('customerLastName','')}".strip() or "—",
        "city":            raw.get("shipmentAddress", {}).get("city", "—"),
        "district":        raw.get("shipmentAddress", {}).get("district", "—"),
        "address":         raw.get("shipmentAddress", {}).get("address", ""),
        "note":             raw.get("customerNote") or "",
        "cargo":            raw.get("cargoProviderName") or "—",
        "tracking":         raw.get("cargoTrackingNumber"),
        "est_days":         2,
        "deadline_hours":   46,
        "tracking_url":     raw.get("cargoTrackingLink") or "",
        "invoice":          str(raw.get("invoiceNumber") or ""),
        "commission":       0.18,
        "cargo_cost":       float(raw.get("totalDiscount") or 29.99),
        "kdv":              0.20,
        "date":             datetime.fromtimestamp(
                              (raw.get("orderDate") or 0) / 1000).strftime(
                                  "%d.%m.%Y %H:%M") if raw.get("orderDate") else "",
        "reviews":          [],
    }


def _normalize_product(raw: dict) -> dict:
    return {
        "sku":             str(raw.get("stockCode") or raw.get("productMainId") or ""),
        "name":            str(raw.get("title") or "")[:200],
        "category":        str(raw.get("categoryName") or "Genel"),
        "stock":           int(raw.get("quantity") or 0),
        "price":           float(raw.get("salePrice") or 0),
        "cost":            0.0,
        "reorder_point":   max(10, int(raw.get("quantity") or 0) // 4),
        "reorder_qty":     max(20, int(raw.get("quantity") or 0) // 2),
        "lead_time":       7,
        "supplier_id":     1,
        "platforms":       ["Trendyol"],
        "return_rate":     0.04,
        "status":          "Satışta" if int(raw.get("quantity") or 0) > 0
                            else "Kritik Stok",
        "image_path":      ((raw.get("images") or [{}])[0].get("url")
                            if raw.get("images") else None),
        "weight_kg":       float(raw.get("dimensionalWeight") or 0.3),
        "barcode":         str(raw.get("barcode") or ""),
        "monthly_sales":   [0] * 12,
    }


def sync_products(callback: Optional[Callable] = None) -> dict:
    mgr = get_manager()
    try:
        raw_products = fetch_products(limit=100)
    except TrendyolSyncError as exc:
        mgr.record_sync("products", datetime.utcnow().isoformat(),
                         error=str(exc))
        if callback:
            callback({"ok": False, "error": str(exc),
                       "recoverable": exc.recoverable})
        return {"ok": False, "error": str(exc),
                 "recoverable": exc.recoverable}

    saved = 0
    skipped = 0
    for raw in raw_products:
        norm = _normalize_product(raw)
        if not norm["sku"]:
            skipped += 1
            continue
        existing = db.get_product(norm["sku"])
        try:
            if existing:
                db.update_product(norm["sku"], **{k: v for k, v in norm.items()
                                                     if k != "sku"})
            else:
                db.add_product(norm)
            saved += 1
        except Exception as exc:
            log.warning("Product save failed for %s: %s", norm["sku"], exc)
            skipped += 1

    result = {"ok": True, "fetched": len(raw_products),
               "saved": saved, "skipped": skipped}
    mgr.record_sync("products", datetime.utcnow().isoformat())
    if callback:
        callback(result)
    return result


def sync_orders(days_back: int = 30,
                  callback: Optional[Callable] = None) -> dict:
    mgr = get_manager()
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    try:
        raw_orders = fetch_orders(start, end, limit=50)
    except TrendyolSyncError as exc:
        mgr.record_sync("orders", datetime.utcnow().isoformat(),
                         error=str(exc))
        if callback:
            callback({"ok": False, "error": str(exc),
                       "recoverable": exc.recoverable})
        return {"ok": False, "error": str(exc),
                 "recoverable": exc.recoverable}

    saved = 0
    for raw in raw_orders:
        norm = _normalize_order(raw)
        if not norm["id"]:
            continue
        try:
            existing = db.fetch_one("SELECT id FROM orders WHERE id=?",
                                       (norm["id"],))
            if existing:
                continue
            db.execute(
                "INSERT INTO orders(id,platform,platform_color,product,sku,qty,"
                "total,status,customer,city,district,address,note,cargo,"
                "tracking,est_days,deadline_hours,tracking_url,invoice,"
                "commission,cargo_cost,kdv,date) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (norm["id"], norm["platform"], norm["platform_color"],
                 norm["product"], norm["sku"], norm["qty"], norm["total"],
                 norm["status"], norm["customer"], norm["city"],
                 norm["district"], norm["address"], norm["note"],
                 norm["cargo"], norm["tracking"], norm["est_days"],
                 norm["deadline_hours"], norm["tracking_url"],
                 norm["invoice"], norm["commission"], norm["cargo_cost"],
                 norm["kdv"], norm["date"]))
            saved += 1
        except Exception as exc:
            log.warning("Order save failed for %s: %s", norm["id"], exc)

    result = {"ok": True, "fetched": len(raw_orders), "saved": saved}
    mgr.record_sync("orders", datetime.utcnow().isoformat())
    if callback:
        callback(result)
    return result


def sync_settlements(days_back: int = 30,
                        callback: Optional[Callable] = None) -> dict:
    mgr = get_manager()
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    try:
        raw = fetch_settlements(start, end)
    except TrendyolSyncError as exc:
        mgr.record_sync("settlements", datetime.utcnow().isoformat(),
                         error=str(exc))
        msg = str(exc)
        is_556 = exc.status == 556
        result = {"ok": False, "error": msg, "recoverable": exc.recoverable,
                   "is_556": is_556,
                   "user_message": (
                       "Trendyol Finans / Hakediş endpoint'i şu anda 556 "
                       "(Service Unavailable) dönüyor. Bu bizim kodumuzdan "
                       "kaynaklı değil — Trendyol cephesindeki mikroservis "
                       "geçici olarak yanıt vermiyor. Trendyol entegrasyon "
                       "destek talebimiz açık, yanıt bekliyoruz."
                       if is_556 else msg)}
        if callback:
            callback(result)
        return result

    result = {"ok": True, "data": raw}
    mgr.record_sync("settlements", datetime.utcnow().isoformat())
    if callback:
        callback(result)
    return result


def sync_all_async(days_back: int = 90,
                       callback: Optional[Callable] = None,
                       progress: Optional[Callable] = None):
    def _do(label: str, fn, *args, **kw):
        if progress:
            try: progress(f"Çekiliyor: {label}…")
            except Exception: pass
        try:
            return fn(*args, **kw)
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:240]}

    def _safe_fetch(label: str, fn, *args, **kw):
        if progress:
            try: progress(f"Çekiliyor: {label}…")
            except Exception: pass
        try:
            data = fn(*args, **kw)
            return {"ok": True, "count": len(data) if isinstance(data, list) else 1,
                     "data": data}
        except TrendyolSyncError as exc:
            return {"ok": False, "error": str(exc)[:280], "status": exc.status,
                     "is_556": exc.status == 556}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:280]}

    def _run():
        end = datetime.utcnow()
        start = end - timedelta(days=days_back)
        out = {
            "seller_info":    _safe_fetch("Satıcı bilgileri", fetch_seller_info),
            "addresses":      _safe_fetch("Depo/iade adresleri",
                                            fetch_supplier_addresses),
            "brands":         _safe_fetch("Marka listesi", fetch_brands),
            "shipment_prov":  _safe_fetch("Kargo firmaları",
                                            fetch_shipment_providers),
            "products":       _do("Ürünler", sync_products),
            "orders":         _do("Siparişler",
                                    sync_orders, days_back=days_back),
            "returns":        _safe_fetch("İadeler / claims",
                                            fetch_returns, start, end),
            "questions":      _safe_fetch("Müşteri soruları",
                                            fetch_questions, start, end),
            "reviews":        _safe_fetch("Yorumlar",
                                            fetch_reviews, start, end),
            "settlements":    _do("Hakediş / settlements",
                                    sync_settlements, days_back=days_back),
        }
        if callback:
            callback(out)
    threading.Thread(target=_run, daemon=True).start()


__all__ = [
    "TrendyolSyncError",
    "fetch_orders", "fetch_settlements", "fetch_products",
    "sync_products", "sync_orders", "sync_settlements",
    "sync_all_async",
]
