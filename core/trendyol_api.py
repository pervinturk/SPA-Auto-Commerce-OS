# -*- coding: utf-8 -*-
"""Trendyol Production API entegrasyonu — REST client.

Endpoint'ler:
    - GET  /sapigw/suppliers/{sellerId}/addresses
    - GET  /sapigw/cargo-providers
    - GET  /sapigw/product-categories
    - GET  /sapigw/product-categories/{id}/attributes
    - GET  /sapigw/brands?name=
    - POST /sapigw/suppliers/{sellerId}/v2/products
    - GET  /sapigw/suppliers/{sellerId}/products/batch-requests/{batchId}
    - POST /sapigw/suppliers/{sellerId}/products/price-and-inventory

Auth: Basic base64(API_KEY:API_SECRET)
Doğrudan import edilebilir; UI framework'ünden bağımsız."""
from __future__ import annotations
import os
import base64
import json
import logging
import threading
from typing import Any, Callable
from urllib.parse import quote

import requests

log = logging.getLogger("trendyol_api")

# --- PRODUCTION CREDENTIALS (env-override mümkün) ---
SELLER_ID  = int(os.environ.get("TRENDYOL_SELLER_ID",  "0"))
API_KEY    = os.environ.get("TRENDYOL_API_KEY",        "")
API_SECRET = os.environ.get("TRENDYOL_API_SECRET",     "")
BRAND_ID   = int(os.environ.get("TRENDYOL_BRAND_ID",   "0"))
BRAND_NAME = os.environ.get("TRENDYOL_BRAND_NAME",     "Your Brand")

BASE_URL = "https://api.trendyol.com/sapigw"
TIMEOUT  = 30


class TrendyolError(Exception):
    """API'den 4xx/5xx + işleme hataları için tek tip."""
    def __init__(self, message: str, status_code: int = 0,
                 response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self):
        base = super().__str__()
        if self.status_code:
            return f"[HTTP {self.status_code}] {base}"
        return base


class TrendyolClient:
    """Trendyol Marketplace REST client.

    Kullanım:
        cli = TrendyolClient()
        cargos = cli.get_cargo_companies()
        result = cli.create_product(payload)
    """

    def __init__(self,
                 seller_id: int = SELLER_ID,
                 api_key:   str = API_KEY,
                 api_secret: str = API_SECRET,
                 base_url:  str = BASE_URL,
                 timeout:   int = TIMEOUT):
        self.seller_id  = seller_id
        self.base_url   = base_url.rstrip("/")
        self.timeout    = timeout
        token_raw = f"{api_key}:{api_secret}".encode("utf-8")
        token_b64 = base64.b64encode(token_raw).decode("ascii")
        self._headers = {
            "Authorization": f"Basic {token_b64}",
            "User-Agent":    f"{seller_id} - SelfIntegration",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        self._session = requests.Session()

    # ----- low-level -----
    def _request(self, method: str, path: str, params: dict = None,
                  json_body: Any = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(
                method=method, url=url,
                headers=self._headers, params=params,
                json=json_body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TrendyolError(f"Ağ hatası: {exc}", 0, None)

        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"raw_text": resp.text[:500]}

        if 200 <= resp.status_code < 300:
            return body

        msg = body.get("errors") or body.get("message") or body
        raise TrendyolError(
            f"Trendyol API hatası: {msg}",
            status_code=resp.status_code, response_body=body)

    # ----- discovery endpoints -----
    def get_cargo_companies(self) -> list[dict]:
        """Kargo firmalarını döner.
        Şema: [{'id': 4, 'name': 'Aras Kargo', 'code': 'ARAS', ...}, ...]"""
        try:
            data = self._request("GET", "/cargo-providers")
            if isinstance(data, list):
                return data
            return data.get("content") or data.get("data") or []
        except TrendyolError as exc:
            log.warning("Kargo listesi çekilemedi, varsayılan listeye düşülüyor: %s", exc)
            return DEFAULT_CARGO_COMPANIES

    def get_supplier_addresses(self) -> list[dict]:
        path = f"/suppliers/{self.seller_id}/addresses"
        try:
            data = self._request("GET", path)
            if isinstance(data, dict):
                return data.get("supplierAddresses") or data.get("content") or []
            return data
        except TrendyolError as exc:
            log.warning("Adres listesi alınamadı: %s", exc)
            return []

    def search_brand(self, name: str) -> list[dict]:
        try:
            data = self._request("GET", "/brands/by-name", params={"name": name})
            if isinstance(data, dict):
                return data.get("brands") or data.get("content") or []
            return data
        except TrendyolError:
            return []

    def get_categories(self) -> list[dict]:
        try:
            data = self._request("GET", "/product-categories")
            if isinstance(data, dict):
                return data.get("categories") or []
            return data
        except TrendyolError as exc:
            log.warning("Kategori ağacı alınamadı: %s", exc)
            return []

    def get_category_attributes(self, category_id: int) -> dict:
        path = f"/product-categories/{category_id}/attributes"
        try:
            return self._request("GET", path)
        except TrendyolError as exc:
            log.warning("Kategori öznitelikleri alınamadı (%s): %s",
                         category_id, exc)
            return {"categoryAttributes": []}

    # ----- product write -----
    def create_product(self, payload: dict | list[dict]) -> dict:
        """Tek ürün veya birden çok ürünü Trendyol'a gönderir.
        Dönüş: {'batchRequestId': '...'}"""
        items = payload if isinstance(payload, list) else [payload]
        self._validate_payload(items)
        body = {"items": items}
        path = f"/suppliers/{self.seller_id}/v2/products"
        return self._request("POST", path, json_body=body)

    def get_batch_status(self, batch_id: str) -> dict:
        path = (f"/suppliers/{self.seller_id}/products/batch-requests/"
                f"{quote(batch_id, safe='')}")
        return self._request("GET", path)

    def update_price_and_stock(self, items: list[dict]) -> dict:
        path = f"/suppliers/{self.seller_id}/products/price-and-inventory"
        return self._request("POST", path, json_body={"items": items})

    # ----- payload helpers -----
    REQUIRED_FIELDS = (
        "barcode", "title", "productMainId", "brandId", "categoryId",
        "quantity", "stockCode", "dimensionalWeight", "description",
        "currencyType", "listPrice", "salePrice", "vatRate",
        "cargoCompanyId", "images", "attributes",
    )

    @classmethod
    def _validate_payload(cls, items: list[dict]):
        for idx, it in enumerate(items):
            missing = [f for f in cls.REQUIRED_FIELDS if f not in it]
            if missing:
                raise TrendyolError(
                    f"Item #{idx}: eksik alan(lar): {missing}", 0,
                    {"item_index": idx, "missing_fields": missing})
            if not isinstance(it.get("images"), list) or not it["images"]:
                raise TrendyolError(
                    f"Item #{idx}: 'images' alanı boş olamaz (en az 1 URL)",
                    0, {"item_index": idx})
            if not isinstance(it.get("attributes"), list):
                raise TrendyolError(
                    f"Item #{idx}: 'attributes' bir liste olmalı", 0,
                    {"item_index": idx})
            if it.get("currencyType") != "TRY":
                raise TrendyolError(
                    f"Item #{idx}: 'currencyType' yalnızca 'TRY' desteklenir",
                    0, {"item_index": idx})

    @classmethod
    def build_payload(cls,
                      barcode:        str,
                      title:          str,
                      product_main_id: str,
                      category_id:    int,
                      quantity:       int,
                      list_price:     float,
                      sale_price:     float,
                      description:    str,
                      images:         list[str],
                      attributes:     list[dict] = None,
                      stock_code:     str = None,
                      brand_id:       int = BRAND_ID,
                      cargo_company_id: int = 10,
                      vat_rate:       int = 18,
                      dimensional_weight: float = 1.0,
                      currency:       str = "TRY") -> dict:
        """Trendyol v2 product payload oluşturur. Tüm zorunlu alanları
        defaultlu olarak doldurur."""
        return {
            "barcode":            str(barcode),
            "title":              str(title)[:100],
            "productMainId":      str(product_main_id),
            "brandId":            int(brand_id),
            "categoryId":         int(category_id),
            "quantity":           int(quantity),
            "stockCode":          str(stock_code or product_main_id),
            "dimensionalWeight":  float(dimensional_weight),
            "description":        str(description),
            "currencyType":       currency,
            "listPrice":          round(float(list_price), 2),
            "salePrice":          round(float(sale_price), 2),
            "vatRate":            int(vat_rate),
            "cargoCompanyId":     int(cargo_company_id),
            "images":             [{"url": u} for u in images],
            "attributes":         attributes or [],
        }

    # ----- async wrappers (UI thread'i kilitlememek için) -----
    def create_product_async(self, payload: dict | list[dict],
                              callback: Callable[[dict | None, str | None], None]):
        """Arka planda create_product çağırır. callback(result, error_str)."""
        def _run():
            try:
                res = self.create_product(payload)
                callback(res, None)
            except TrendyolError as exc:
                callback(None, str(exc))
            except Exception as exc:
                callback(None, f"Beklenmeyen hata: {exc}")
        threading.Thread(target=_run, daemon=True).start()

    def get_cargo_companies_async(self,
                                    callback: Callable[[list[dict]], None]):
        def _run():
            try:
                companies = self.get_cargo_companies()
            except Exception:
                companies = DEFAULT_CARGO_COMPANIES
            callback(companies)
        threading.Thread(target=_run, daemon=True).start()


# Fallback kargo listesi (API ulaşılamadığında)
DEFAULT_CARGO_COMPANIES = [
    {"id": 10, "name": "Aras Kargo",      "code": "ARAS"},
    {"id": 20, "name": "Yurtiçi Kargo",   "code": "YURTICI"},
    {"id": 17, "name": "MNG Kargo",       "code": "MNG"},
    {"id": 9,  "name": "PTT Kargo",       "code": "PTT"},
    {"id": 7,  "name": "Sürat Kargo",     "code": "SURAT"},
    {"id": 19, "name": "HepsiJet",        "code": "HEPSIJET"},
    {"id": 30, "name": "Trendyol Express","code": "TEX"},
]


# Kâr hesaplayıcı yardımcı — UI tarafında live kullanım için
def estimate_net_profit(sale_price: float, commission_pct: float = 0.215,
                         cargo_cost: float = 100.0,
                         vat_rate: float = 0.18,
                         product_cost: float = 0.0) -> dict:
    """Trendyol komisyon + kargo + (opsiyonel) KDV + maliyet düşümü ile
    net kâr ön-tahmini.

    Trendyol komisyon ortalaması: %21.5 (kategori bazlı %15-25 arası).
    Sabit kargo: 100 TL (kullanıcı override edebilir).

    Returns:
        {gross, commission, cargo, kdv, cost, net, margin_pct, breakeven}
    """
    sp = float(sale_price or 0)
    if sp <= 0:
        return {"gross": 0, "commission": 0, "cargo": cargo_cost,
                 "kdv": 0, "cost": product_cost, "net": -cargo_cost - product_cost,
                 "margin_pct": 0, "breakeven": cargo_cost + product_cost}
    commission = sp * commission_pct
    kdv = sp - (sp / (1 + vat_rate))
    net = sp - commission - cargo_cost - kdv - product_cost
    margin = (net / sp * 100) if sp else 0
    breakeven = commission + cargo_cost + kdv + product_cost
    return {
        "gross":      sp,
        "commission": commission,
        "cargo":      cargo_cost,
        "kdv":        kdv,
        "cost":       product_cost,
        "net":        net,
        "margin_pct": margin,
        "breakeven":  breakeven,
    }


# Trendyol kategori öneri haritası (Your Brand odaklı — bebek/çocuk ağırlıklı)
SUGGESTED_CATEGORIES = {
    "Bebek Arabası":        {"id": 411,  "name": "Bebek Arabası",          "vat": 18},
    "Bebek Oto Koltuğu":    {"id": 412,  "name": "Bebek Oto Koltuğu",      "vat": 18},
    "Mama Sandalyesi":      {"id": 413,  "name": "Mama Sandalyesi",        "vat": 18},
    "Bebek Beşik & Park":   {"id": 414,  "name": "Bebek Beşik & Park",     "vat": 18},
    "Çocuk Giyim":          {"id": 522,  "name": "Çocuk Giyim",            "vat": 8},
    "Çocuk Ayakkabı":       {"id": 1066, "name": "Çocuk Ayakkabı",         "vat": 8},
    "Oyuncak":              {"id": 763,  "name": "Oyuncak",                "vat": 18},
    "Bebek Bakım":          {"id": 421,  "name": "Bebek Bakım Ürünleri",   "vat": 8},
    "Genel - Diğer":        {"id": 1,    "name": "Genel",                  "vat": 18},
}


def get_default_client() -> TrendyolClient:
    """Singleton-stili default client (üretim kimlikleriyle)."""
    if not hasattr(get_default_client, "_inst"):
        get_default_client._inst = TrendyolClient()
    return get_default_client._inst
