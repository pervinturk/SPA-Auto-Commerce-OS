import os
import time
import threading
import re
import json
from core import database as db
from core.api_key_pool import (get_pool, call_with_rotation,
                                  PRIMARY_MODEL, SECONDARY_MODEL)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = PRIMARY_MODEL

_SYSTEM = (
    "Sen EaaS Auto-Commerce OS yapay zeka asistanısın. Adın: Akıl Hocası. "
    "Endüstri Muhendisi ve e-ticaret CFO'su gibi düşünürsün. "
    "Kısa, profesyonel, eylem odakli Türkçe yanıtlar verirsin. "
    "ROI, NPV, emniyet stoğu, pazar yeri optimizasyonu terimlerini doğal kullanırsın. "
    "Mümkün olan her durumda somut sayısal öneri verirsin."
)

_MOCK = {
    "iade": "İade oranlarınızda SN-014 öneme cikiyor: son 7 gunde %15 (normal %4). İade notları "
            "%68 'beden sorunu', %22 'görsel uyuşmazlığı'. Ürün açıklamasina beden kılavuzu "
            "ekleyin, model üzerinde ölçü fotoğrafı koyun. Bu adımlarla iade oranı %5 altina "
            "düşmesi bekleniyor — yıllık 12.600 TL tasarruf.",
    "stok": "SN-014 ve GY-101 için yeniden sipariş noktasına ulaşıldı. (s,Q) politikasına göre: "
            "SN-014 için 50 adet (19.000 TL), GY-101 için 30 adet (21.600 TL). Tedarik sürelerini "
            "hesaba katarak bugün sipariş verilmesi gerekiyor.",
    "fiyat": "TS-001 tişört için fiyat esnekliği analizi: 250 TL'den 275 TL'ye çıkarmak "
             "(%10 artış) talepte yaklaşık %12 düşüşe neden olur. Net kar etkisi: +1.840 TL/ay. "
             "Artış önerilir.",
    "kargo": "Bugün İstanbul/Kadıköy'e giden 2 sipariş tespit edildi. Tek poset ile gondermek "
             "kargo maliyetini 45 TL düşürur. Onaylarsaniz TY-99102 ve HB-44231 siparişlerini "
             "birleştirebilirsiniz.",
    "amazon": "Urunlerinizin Amazon Avrupa pazarindaki rekabet potansiyeli yüksek. TS-001 ve "
              "GY-220 kategorisinde Amazon.de'de benzer ürünler 15-25 EUR bandinda satiliyor. "
              "Başlangıç maliyeti aylık 39.99 USD + %10 komisyon. 3 aylık NPV pozitif.",
    "bayram": "Kurban Bayramı'na 35 gun kaldi. Geçmiş Trendyol verileri: bayram öncesi 10. gunde "
              "giyim satislari %45 artiyor. Bugün %10 indirim baslatin. Tahmini ciro artisi: %32, "
              "net kâr artisi: %18.",
    "default": "Sistemin ana riskleri: SN-014 iade oranı yüksek, GY-101 stok kritik. Bu iki sorunu "
               "cozdugunuzde aylık ~8.000 TL ek kar saglanir. Hangi konuyu derinlestirelim?",
}

_PRICE_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(tl|lira|usd|eur|\$)?", re.I)
_PCT_RE = re.compile(r"%\s*(\d+(?:[\.,]\d+)?)|(\d+(?:[\.,]\d+)?)\s*%")
_COLOR_RE = re.compile(
    r"\b(mavi|kirmizi|kırmızı|siyah|beyaz|yesil|yeşil|sari|sarı|mor|pembe|gri|turuncu|"
    r"blue|red|black|white|green|yellow|purple|pink|gray|grey|orange)\b", re.I)


def _detect_action(user_input: str) -> dict:
    """Parse intent from free text. Returns {action, target_sku, payload, confirm_text}.
    Returns None if no actionable intent found."""
    text = user_input.lower().strip()
    products = db.fetch_all("SELECT sku, name, category, price FROM products")

    target = None
    for p in products:
        if p["sku"].lower() in text:
            target = p
            break
    if not target:
        for p in products:
            name_lower = p["name"].lower()
            tokens = [w for w in re.split(r"\W+", name_lower) if len(w) > 3]
            for tok in tokens:
                if tok in text:
                    target = p
                    break
            if target:
                break

    color_match = _COLOR_RE.search(user_input)
    if color_match and ("renk" in text or "rengi" in text or "color" in text or
                         "yap" in text or "değiştir" in text or "degistir" in text):
        return {
            "action": "update_color",
            "target_sku": target["sku"] if target else None,
            "payload": {"color": color_match.group(0)},
            "confirm_text": (f"{target['name'] if target else 'Ürün'} rengi "
                             f"'{color_match.group(0)}' olarak guncellensin mi?"),
        }

    if any(k in text for k in ["fiyat", "fiyati", "price"]) and any(
            k in text for k in ["yap", "ayarla", "güncel", "değiştir", "degistir", "set"]):
        pm = _PRICE_RE.search(user_input)
        if pm and target:
            new_price = float(pm.group(1).replace(",", "."))
            return {
                "action": "update_price",
                "target_sku": target["sku"],
                "payload": {"price": new_price},
                "confirm_text": f"{target['name']} fiyati {new_price:.2f} TL olarak guncellensin mi? "
                                f"(Mevcut: {target['price']:.2f} TL)",
            }

    if any(k in text for k in ["sipariş ver", "stok al", "yeniden sipariş", "reorder"]) and target:
        return {
            "action": "create_reorder",
            "target_sku": target["sku"],
            "payload": {},
            "confirm_text": f"{target['name']} icin yeniden siparis emri olusturulsun mu?",
        }

    if "indirim" in text or "kampanya" in text:
        pct_m = _PCT_RE.search(user_input)
        pct = 10
        if pct_m:
            grp = pct_m.group(1) or pct_m.group(2)
            try:
                pct = float(grp.replace(",", "."))
            except Exception:
                pass
        return {
            "action": "create_campaign",
            "target_sku": target["sku"] if target else None,
            "payload": {"discount_pct": pct},
            "confirm_text": (f"%{pct:.0f} indirim kampanyasi "
                             f"{('('+ target['name'] +')') if target else '(tüm portfoy)'} "
                             "oluşturulsun mu?"),
        }

    return None


def apply_action(action: dict) -> str:
    a = action["action"]
    sku = action.get("target_sku")
    p = action.get("payload", {})
    if a == "update_color" and sku:
        prod = db.get_product(sku)
        name = prod["name"]
        new_color = p["color"].capitalize()
        new_name = re.sub(r"-\s*[A-Za-zĞÜŞİÖÇğüşıöç]+\s*$", f"- {new_color}", name)
        if new_name == name:
            new_name = f"{name} ({new_color})"
        db.update_product(sku, name=new_name)
        db.log_agent_action(a, sku, p, "applied")
        return f"Tamam, {sku} urununu '{new_name}' olarak guncelledim."
    if a == "update_price" and sku:
        db.update_product(sku, price=p["price"])
        db.log_agent_action(a, sku, p, "applied")
        return f"Tamam, {sku} fiyatini {p['price']:.2f} TL olarak guncelledim."
    if a == "create_reorder" and sku:
        prod = db.get_product(sku)
        db.add_notification(8, "success", f"Siparis Emri: {sku}",
                             f"{prod['name']} icin {prod['reorder_qty']} adet "
                             f"siparis emri olusturuldu.", target_sku=sku, action="Takip Et")
        db.log_agent_action(a, sku, p, "applied")
        return f"Tamam, {sku} icin {prod['reorder_qty']} adet siparis emri olusturdum."
    if a == "create_campaign":
        db.add_notification(6, "info", "Kampanya Oluşturuldu",
                             f"%{p['discount_pct']:.0f} indirim kampanyasi aktif edildi.",
                             target_sku=sku)
        db.log_agent_action(a, sku or "ALL", p, "applied")
        return f"Tamam, %{p['discount_pct']:.0f} indirim kampanyasini aktif ettim."
    return "Aksiyon uygulanamadi."


def _call_gemini_rotated(prompt: str) -> str:
    def _do_call(api_key: str, model_name: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name, system_instruction=_SYSTEM)
        resp = model.generate_content(prompt)
        return getattr(resp, "text", "") or ""
    return call_with_rotation(_do_call, model=GEMINI_MODEL)


def get_response(user_input: str, callback: callable) -> None:
    def _worker():
        time.sleep(0.3)
        action = _detect_action(user_input)
        if action:
            callback({"type": "action_proposal", "action": action,
                       "text": action["confirm_text"]})
            return

        pool = get_pool()
        if pool.size > 0:
            try:
                text = _call_gemini_rotated(user_input)
                callback({"type": "text", "text": text})
                return
            except Exception as exc:
                err = str(exc)
                callback({"type": "text",
                           "text": f"API yanıt vermiyor (anahtar havuzunda hata): "
                                   f"{err[:150]}\n\nYerel mock yanıta düşülüyor:\n" +
                                   _fallback_mock(user_input)})
                return

        callback({"type": "text", "text": _fallback_mock(user_input)})

    threading.Thread(target=_worker, daemon=True).start()


def _fallback_mock(user_input: str) -> str:
    low = user_input.lower()
    if any(w in low for w in ["iade", "return", "sorun", "sikayet"]):
        return _MOCK["iade"]
    if any(w in low for w in ["stok", "emniyet"]):
        return _MOCK["stok"]
    if any(w in low for w in ["fiyat", "indirim", "zam", "price"]):
        return _MOCK["fiyat"]
    if any(w in low for w in ["kargo", "birleş", "poset"]):
        return _MOCK["kargo"]
    if any(w in low for w in ["amazon", "etsy", "global"]):
        return _MOCK["amazon"]
    if any(w in low for w in ["bayram", "kampanya", "özel"]):
        return _MOCK["bayram"]
    return _MOCK["default"]


def review_reply(review_text: str, rating: int) -> str:
    if rating <= 2:
        return ("Sayin müşterimiz, yasamis oldugunuz olumsuz deneyim için üzgünuz. "
                "İletişim numaramizdan size ulasarak özel çözüm sunmayi çok isteriz. "
                "Geri bildiriminiz ürün kalitemizi iyilestirmemiz için çok degerli.")
    if rating == 3:
        return ("Yorumunuz için tesekkur ederiz. Daha iyi bir deneyim için önerilerinizi "
                "müşteri hizmetlerimize iletebilirsiniz. Sizi memnun etmek onceligimiz.")
    return ("Güzel yorumunuz için çok tesekkur ederiz! Memnuniyetiniz bizim için en büyük "
            "motivasyon kaynagi. Yeni urunlerimizden haberdar olmak için magazamizi takipte kalin.")


_VISION_PROMPT = """Bu ürün fotografini incele ve SADECE asagidaki JSON semasinda yanit ver.
Hiçbir açıklama, markdown, baska metin ekleme. Sadece gecerli JSON dondur.

{
  "name": "Detayli ürün adı (Türkçe, max 60 karakter)",
  "category": "Giyim | Ayakkabi | Aksesuar | Ev | Elektronik | Kozmetik",
  "subcategory": "Spesifik alt kategori (ornek: Tişört, Sneaker, Cüzdan)",
  "color": "Ana renk (Türkçe)",
  "size": "Tahmini beden/boyut",
  "description": "SEO uyumlu, 2-3 cumlelik ürün açıklamasi (Türkçe)",
  "suggested_price_try": tahmini perakende fiyat sayısal (TL),
  "suggested_cost_try": tahmini maliyet sayısal (TL),
  "weight_g": tahmini ağırlik gram,
  "material": "Tahmini malzeme",
  "seo_title": "60 karakter SEO basligi"
}
"""


def analyze_product_image(image_path: str, callback) -> None:
    """Gemini Vision ile fotograftan ürün analizi. Thread'de çalışir,
    callback'e (sonuç_dict, hata_str_or_None) doner."""
    def _worker():
        pool = get_pool()
        if pool.size == 0:
            callback(None, "Gemini key pool boş.")
            return
        try:
            from PIL import Image
            img = Image.open(image_path)
            def _do_call(api_key: str, model_name: str):
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(model_name)
                return model.generate_content([_VISION_PROMPT, img])
            resp = call_with_rotation(_do_call, model=GEMINI_MODEL)
            text = (getattr(resp, "text", "") or "").strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```\s*$", "", text)
            data = json.loads(text)
            result = {
                "name":        str(data.get("name", ""))[:80],
                "category":    str(data.get("category", "Giyim")),
                "subcategory": str(data.get("subcategory", ""))[:40],
                "color":       str(data.get("color", ""))[:30],
                "size":        str(data.get("size", "Standart"))[:20],
                "description": str(data.get("description", ""))[:500],
                "price":       float(data.get("suggested_price_try", 0) or 0),
                "cost":        float(data.get("suggested_cost_try", 0) or 0),
                "weight_g":    float(data.get("weight_g", 200) or 200),
                "material":    str(data.get("material", "")),
                "seo_title":   str(data.get("seo_title", ""))[:80],
            }
            callback(result, None)
        except json.JSONDecodeError as exc:
            callback(None, f"AI cevabi JSON degil: {exc}")
        except Exception as exc:
            callback(None, f"Vision hatasi: {exc}")
    threading.Thread(target=_worker, daemon=True).start()


def marketplace_feasibility(marketplace: dict, current_monthly_revenue: float = 0) -> dict:
    """Kilitli pazar yeri için AI fizibilite. ROI, breakeven, beklenen kazanç."""
    unlock = marketplace.get("unlock_fee", "")
    rev_lift = float(marketplace.get("expected_rev_lift") or 0)
    profit_lift = float(marketplace.get("expected_profit_lift") or 0)
    days = int(marketplace.get("avg_unlock_days") or 14)
    current_profit = current_monthly_revenue * 0.34

    incremental_rev = current_monthly_revenue * rev_lift
    incremental_profit = current_profit * profit_lift

    fixed_monthly = 0
    if "39.99" in unlock or "39,99" in unlock:
        fixed_monthly = 39.99 * 34.5
    elif "Ücretsiz" in unlock or "ücretsiz" in unlock:
        fixed_monthly = 0
    elif "0.20" in unlock or "0,20" in unlock:
        fixed_monthly = 200

    net_monthly = incremental_profit - fixed_monthly
    breakeven = None
    if net_monthly > 0 and fixed_monthly > 0:
        breakeven = max(1, round(fixed_monthly / net_monthly, 1))
    elif net_monthly > 0 and fixed_monthly == 0:
        breakeven = 0

    if net_monthly > 500:
        verdict = "ÖNERİLİR"
    elif net_monthly > 0:
        verdict = "ARAŞTIR"
    else:
        verdict = "RİSKLİ"

    return {
        "marketplace":         marketplace.get("name", ""),
        "incremental_revenue": incremental_rev,
        "incremental_profit":  incremental_profit,
        "fixed_monthly_cost":  fixed_monthly,
        "net_monthly":         net_monthly,
        "breakeven_months":    breakeven,
        "avg_unlock_days":     days,
        "roi_pct_12mo":        (net_monthly * 12 / fixed_monthly * 100) if fixed_monthly else 999,
        "verdict":             verdict,
        "rev_lift_pct":        rev_lift * 100,
    }


def packaging_recommendation(product: dict) -> str:
    cat = (product.get("category") or "").lower()
    weight = product.get("weight_kg", 0)
    if "ayakkabi" in cat or weight > 0.5:
        return ("Tavsiye: Sert karton kutu + dolgu kagidi + opsiyönel hediye karti. "
                "Kutu üzerine 'Kirilgan' etiketi koymayin (açgözlülük algisi). "
                "İade oranı: %15 — uygun ambalaj iadeyi %3 azaltabilir.")
    if weight < 0.2:
        return ("Tavsiye: Kraft karton poset + ince selefon. Maliyet: 1.20 TL/poset. "
                "Mat finish müşteri algisinda %18 daha premium hissi yaratiyor.")
    return ("Tavsiye: Orta boy karton poset + açılış sirit + 'Tesekkurler' karti. "
            "Karton katma degeri: müşteri yorum puani ortalama +0.4 yildiz.")
