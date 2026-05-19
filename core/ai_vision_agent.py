# -*- coding: utf-8 -*-
"""Gemini Vision otonom ürün doldurucu (RAG + Pydantic).

Akış:
    1) Kullanıcı sadece görsel yükler.
    2) Vision modeli ürünü analiz eder.
    3) İlgili kategoriye ait kısıt CSV'sini bağlama enjekte ederiz
       (örn. Bebek Arabası → yaş grubu, taşıma kapasitesi, renk).
    4) Model SADECE izinli özniteliklerden seçer.
    5) Çıktı Pydantic ile parse edilip dict döner — Trendyol payload'una
       doğrudan beslenebilir.

Çağrı:
    from core.ai_vision_agent import analyze_product_image
    result = analyze_product_image(image_bytes, category="Bebek Arabası")
"""
from __future__ import annotations
import os
import io
import re
import json
import logging
import threading
from pathlib import Path
from typing import Callable, Any

log = logging.getLogger("ai_vision_agent")

GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-1.5-flash"
DEFAULT_BRAND = "Your Brand"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# --- Pydantic / dataclass yedek modeli ---
try:
    from pydantic import BaseModel, Field, validator
    HAS_PYDANTIC = True

    class ProductSuggestion(BaseModel):
        title:        str = Field(..., max_length=100)
        description:  str = Field(..., max_length=1500)
        sale_price:   float = Field(..., gt=0)
        list_price:   float = Field(..., gt=0)
        category:     str
        color:        str = ""
        material:     str = ""
        size:         str = ""
        weight_kg:    float = 0.5
        age_group:    str = ""
        gender:       str = "Unisex"
        seo_keywords: list[str] = []
        brand:        str = DEFAULT_BRAND
        attributes:   dict[str, str] = {}

        @validator("list_price", always=True)
        def _list_ge_sale(cls, v, values):
            sp = values.get("sale_price", 0)
            if v < sp:
                return sp * 1.15  # liste >= satış
            return v
except ImportError:
    HAS_PYDANTIC = False

    class ProductSuggestion:
        def __init__(self, **kw):
            self.title = str(kw.get("title", ""))[:100]
            self.description = str(kw.get("description", ""))[:1500]
            self.sale_price = float(kw.get("sale_price", 0))
            self.list_price = max(float(kw.get("list_price", 0)),
                                    self.sale_price * 1.15)
            self.category = str(kw.get("category", ""))
            self.color = str(kw.get("color", ""))
            self.material = str(kw.get("material", ""))
            self.size = str(kw.get("size", ""))
            self.weight_kg = float(kw.get("weight_kg", 0.5))
            self.age_group = str(kw.get("age_group", ""))
            self.gender = str(kw.get("gender", "Unisex"))
            self.seo_keywords = list(kw.get("seo_keywords", []))
            self.brand = str(kw.get("brand", DEFAULT_BRAND))
            self.attributes = dict(kw.get("attributes", {}))

        def dict(self):
            return self.__dict__.copy()


# --- Kategori kısıt kuralları (CSV destekli + fallback inline) ---
# Beklenen CSV: data/category_rules.csv
#   columns: category, attribute, allowed_values, required
CATEGORY_RULES_INLINE = {
    "Bebek Arabası": {
        "Yaş Grubu":          ["0-6 ay", "6-12 ay", "1-3 yaş", "3+ yaş"],
        "Taşıma Kapasitesi":  ["10 kg", "15 kg", "20 kg", "25 kg"],
        "Renk":               ["Siyah", "Lacivert", "Gri", "Bordo", "Bej", "Pembe", "Mavi"],
        "Katlanabilir":       ["Evet", "Hayır"],
        "Kullanım Şekli":     ["Tek Yönlü", "Çift Yönlü", "Dönüşümlü"],
    },
    "Bebek Oto Koltuğu": {
        "Yaş Grubu":          ["0-15 ay", "9 ay-4 yaş", "4-12 yaş", "0-12 yaş"],
        "Kilo Aralığı":       ["0-13 kg", "9-18 kg", "15-36 kg", "0-36 kg"],
        "Isofix":             ["Evet", "Hayır"],
        "Renk":               ["Siyah", "Gri", "Bordo", "Mavi"],
    },
    "Mama Sandalyesi": {
        "Yaş Grubu":          ["6-12 ay", "1-3 yaş", "6 ay-3 yaş"],
        "Katlanabilir":       ["Evet", "Hayır"],
        "Yükseklik Ayarı":    ["Evet", "Hayır"],
        "Renk":               ["Beyaz", "Gri", "Mavi", "Pembe"],
    },
    "Çocuk Giyim": {
        "Yaş Grubu":          ["0-3 ay", "3-6 ay", "6-12 ay", "1-2 yaş",
                                "3-4 yaş", "5-6 yaş", "7-8 yaş", "9-10 yaş"],
        "Cinsiyet":           ["Erkek", "Kız", "Unisex"],
        "Renk":               ["Beyaz", "Siyah", "Mavi", "Pembe", "Sarı",
                                "Yeşil", "Kırmızı", "Mor", "Gri"],
        "Malzeme":            ["Pamuk", "Polyester", "Karışım", "Penye"],
        "Beden":              ["XS", "S", "M", "L", "XL"],
    },
    "Çocuk Ayakkabı": {
        "Numara":             ["19", "20", "21", "22", "23", "24", "25",
                                "26", "27", "28", "29", "30", "31", "32"],
        "Cinsiyet":           ["Erkek", "Kız", "Unisex"],
        "Renk":               ["Beyaz", "Siyah", "Mavi", "Pembe", "Kırmızı"],
        "Taban":               ["Kauçuk", "EVA", "Polyester"],
    },
    "Oyuncak": {
        "Yaş Grubu":          ["0-1 yaş", "1-3 yaş", "3-5 yaş", "5-7 yaş", "7+ yaş"],
        "Tip":                ["Eğitici", "Peluş", "Yapboz", "Lego", "Bebek",
                                "Araba", "Müzikli"],
        "Cinsiyet":           ["Erkek", "Kız", "Unisex"],
    },
    "Bebek Bakım Ürünleri": {
        "Tip":                ["Şampuan", "Krem", "Yağ", "Pudra", "Mendil"],
        "Yaş Grubu":          ["0+ ay", "6+ ay", "12+ ay"],
        "Hacim":              ["100 ml", "200 ml", "250 ml", "500 ml"],
    },
}


def load_category_rules() -> dict:
    """data/category_rules.csv varsa onu yükler, yoksa inline default."""
    csv_path = DATA_DIR / "category_rules.csv"
    if not csv_path.exists():
        return CATEGORY_RULES_INLINE
    rules = {}
    try:
        import csv
        with open(csv_path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                cat = row.get("category", "").strip()
                attr = row.get("attribute", "").strip()
                allowed = [v.strip() for v in
                            row.get("allowed_values", "").split("|") if v.strip()]
                if cat and attr and allowed:
                    rules.setdefault(cat, {})[attr] = allowed
        if rules:
            return rules
    except Exception as exc:
        log.warning("category_rules.csv okunamadı: %s", exc)
    return CATEGORY_RULES_INLINE


def _build_prompt(category_hint: str = "", brand: str = DEFAULT_BRAND) -> str:
    """RAG-tabanlı prompt — model SADECE izinli değerlerden seçebilir."""
    rules = load_category_rules()
    if category_hint and category_hint in rules:
        active_rules = {category_hint: rules[category_hint]}
    else:
        active_rules = rules

    rules_block_lines = []
    for cat, attrs in active_rules.items():
        rules_block_lines.append(f"\n=== Kategori: {cat} ===")
        for attr_name, allowed in attrs.items():
            rules_block_lines.append(
                f"  - {attr_name}: {' | '.join(allowed)}")
    rules_block = "\n".join(rules_block_lines)

    return f"""Sen profesyonel bir e-ticaret içerik uzmanısın. Marka: "{brand}".

GÖREV: Bu ürün fotoğrafını analiz et. AŞAĞIDAKİ JSON ŞEMASINA TAM UYUMLU
çıktı üret. SADECE GEÇERLİ JSON dön, başka açıklama YAZMA, ```json bloğu KULLANMA.

JSON ŞEMASI (her alan zorunlu):
{{
  "title":        "SEO uyumlu kısa başlık (en fazla 100 karakter, Türkçe)",
  "description":  "Detaylı, SEO uyumlu açıklama (3-5 cümle, Türkçe)",
  "sale_price":   sayisal satış fiyatı (TL),
  "list_price":   sayisal liste fiyatı (TL, sale_price * 1.15 kabul edilebilir),
  "category":     "Aşağıdaki listeden TAM olarak seç",
  "color":        "Aşağıdaki listeden seç",
  "material":     "Malzeme adı (Türkçe)",
  "size":         "Beden/Boyut",
  "weight_kg":    sayisal ağırlık (kg),
  "age_group":    "Yaş grubu (varsa)",
  "gender":       "Erkek | Kız | Unisex",
  "seo_keywords": ["3-7 anahtar kelime"],
  "brand":        "{brand}",
  "attributes":   {{ "öznitelik_adı": "izinli_değer", ... }}
}}

İZİNLİ KATEGORİ VE ÖZNİTELİK DEĞERLERİ (RAG):
{rules_block}

KURALLAR:
1) attributes anahtarları yukarıdaki "attribute" isimleriyle EŞLEŞMELİ.
2) Her attribute değeri yukarıda listelenen "izinli değerlerden biri" OLMALI.
3) brand alanı her zaman "{brand}".
4) Fiyat tahminini Türkiye e-ticaret piyasası bazında ver (ortalama Trendyol fiyatı).
5) JSON dışında HİÇBİR ŞEY yazma — sadece JSON döndür.
"""


def _extract_json(text: str) -> dict:
    """Modelin döndürdüğü metinden JSON'u güvenli ayıkla."""
    if not text:
        raise ValueError("Boş yanıt")
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s)
    # JSON gövdesini bul
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("JSON bulunamadı")
    return json.loads(s[start:end + 1])


def analyze_product_image(image_bytes: bytes,
                           category_hint: str = "",
                           brand: str = DEFAULT_BRAND) -> dict:
    """SENKRON Vision çağrısı. Pydantic-validated dict döner.

    Args:
        image_bytes: Görsel ikili veri (PNG/JPG/WebP).
        category_hint: Bilinen kategori (örn. "Bebek Arabası") — RAG için.
        brand: Üretici marka adı (zorla doldurulur).

    Returns:
        ProductSuggestion.dict() — anahtarlar yukarıdaki şema.

    Raises:
        RuntimeError: Vision çağrısı başarısız olursa.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        raise RuntimeError("Gemini API anahtarı ayarlı değil.")
    try:
        import google.generativeai as genai
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(f"Eksik kütüphane: {exc}")

    genai.configure(api_key=GEMINI_API_KEY)
    img = Image.open(io.BytesIO(image_bytes))
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = _build_prompt(category_hint, brand)

    try:
        resp = model.generate_content([prompt, img])
    except Exception as exc:
        raise RuntimeError(f"Vision API hatası: {exc}")

    text = getattr(resp, "text", "") or ""
    try:
        data = _extract_json(text)
    except Exception as exc:
        raise RuntimeError(f"AI cevabı parse edilemedi: {exc}\nHam: {text[:200]}")

    # RAG doğrulama — izinli olmayan attribute değerlerini ayıkla
    rules = load_category_rules()
    cat = data.get("category", "")
    cat_rules = rules.get(cat, {})
    attrs = data.get("attributes") or {}
    if isinstance(attrs, dict) and cat_rules:
        cleaned = {}
        for k, v in attrs.items():
            allowed = cat_rules.get(k, [])
            if not allowed or v in allowed:
                cleaned[k] = v
        data["attributes"] = cleaned

    # Marka zorla doldur
    data["brand"] = brand
    if "seo_keywords" in data and not isinstance(data["seo_keywords"], list):
        data["seo_keywords"] = []

    try:
        if HAS_PYDANTIC:
            return ProductSuggestion(**data).dict()
        return ProductSuggestion(**data).dict()
    except Exception as exc:
        raise RuntimeError(f"Pydantic validation hatası: {exc}\nVeri: {data}")


def analyze_product_image_async(image_path: str,
                                  callback: Callable[[dict | None, str | None], None],
                                  category_hint: str = "",
                                  brand: str = DEFAULT_BRAND):
    """UI thread'i kilitlememek için arka planda çalışır.
    callback(result_dict, error_str) ile döner."""
    def _run():
        try:
            with open(image_path, "rb") as fh:
                data = fh.read()
            result = analyze_product_image(data, category_hint, brand)
            callback(result, None)
        except Exception as exc:
            callback(None, str(exc))
    threading.Thread(target=_run, daemon=True).start()


# Vision sonucundan Trendyol payload'u oluşturma yardımcı
def vision_to_trendyol_payload(vision: dict,
                                 trendyol_category_id: int,
                                 quantity: int,
                                 cargo_company_id: int,
                                 image_urls: list[str],
                                 product_main_id: str,
                                 barcode: str = None,
                                 vat_rate: int = 18) -> dict:
    """Vision sonucunu Trendyol create_product payload'una çevirir."""
    from core.trendyol_api import TrendyolClient
    if not barcode:
        barcode = "869" + str(abs(hash(product_main_id)) % 10000000000).zfill(10)

    attrs_list = []
    for k, v in (vision.get("attributes") or {}).items():
        attrs_list.append({"attributeName": k, "attributeValue": v})

    return TrendyolClient.build_payload(
        barcode=barcode,
        title=vision["title"],
        product_main_id=product_main_id,
        category_id=trendyol_category_id,
        quantity=quantity,
        list_price=float(vision.get("list_price") or vision["sale_price"] * 1.15),
        sale_price=float(vision["sale_price"]),
        description=vision["description"],
        images=image_urls,
        attributes=attrs_list,
        stock_code=product_main_id,
        cargo_company_id=cargo_company_id,
        vat_rate=vat_rate,
        dimensional_weight=float(vision.get("weight_kg", 0.5)),
    )
