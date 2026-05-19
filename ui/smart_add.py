# -*- coding: utf-8 -*-
"""Trendyol Smart Add penceresi (CustomTkinter).

Akış (Streamlit yerine masaüstü CTk uyarlaması):
    SOL kolon  : Görsel yükleme + AI durum + preview
    SAĞ kolon  : Otonom doldurulan form alanları
    ALT bölge  : Canlı Net Kâr metrik kartı + Kargo seçimi + Trendyol Yükle butonu
"""
from __future__ import annotations
import os
import json
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

from ui.theme import *
from ui.widgets import Pill
from core import database as db
from core.trendyol_api import (TrendyolClient, get_default_client,
                                 estimate_net_profit, SUGGESTED_CATEGORIES,
                                 DEFAULT_CARGO_COMPANIES, BRAND_NAME, BRAND_ID)
from core.ai_vision_agent import (analyze_product_image_async,
                                    vision_to_trendyol_payload,
                                    DEFAULT_BRAND)


class TrendyolSmartAddWindow(ctk.CTkToplevel):
    """Görsel-temelli otonom ürün yükleme penceresi."""

    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Trendyol Smart Add — Canlı API Entegrasyonu")
        self.geometry("1100x780")
        self.minsize(960, 660)
        self.configure(fg_color=BG_DARK)
        self.grab_set()

        self._image_path: str | None = None
        self._image_preview: ctk.CTkImage | None = None
        self._cargo_list = DEFAULT_CARGO_COMPANIES
        self._cargo_id   = 10
        self._fields: dict[str, ctk.CTkEntry | ctk.CTkTextbox | ctk.CTkOptionMenu] = {}
        self._profit_labels: dict[str, ctk.CTkLabel] = {}
        self._submitting = False
        self._client = get_default_client()

        self._build()
        # Kargo listesini arka planda çek
        self._client.get_cargo_companies_async(
            lambda lst: self.after(0, lambda: self._on_cargo_loaded(lst)))

    # --------- layout ---------
    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0,
                           height=64, border_width=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        left_h = ctk.CTkFrame(hdr, fg_color="transparent")
        left_h.pack(side="left", padx=20)
        ctk.CTkLabel(left_h, text="🛒  Trendyol Smart Add",
                     font=FONT_H1, text_color=TEXT_PRI).pack(side="left", pady=18)
        Pill(hdr, f"  Marka: {BRAND_NAME}  ", ACCENT,
              ACCENT_DK).pack(side="left", padx=12, pady=20)
        Pill(hdr, "  CANLI API  ", DANGER, BG_DARK).pack(side="left", padx=4, pady=20)
        ctk.CTkLabel(hdr,
                      text=f"Seller ID: {self._client.seller_id}",
                      font=FONT_TINY, text_color=TEXT_MUT).pack(
            side="right", padx=20, pady=24)

        body = ctk.CTkFrame(self, fg_color=BG_DARK)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        body.grid_columnconfigure(0, weight=4, uniform="col")
        body.grid_columnconfigure(1, weight=6, uniform="col")
        body.grid_rowconfigure(0, weight=1)

        # SOL — Görsel & AI durumu
        left = ctk.CTkFrame(body, fg_color=BG_PANEL, corner_radius=14,
                            border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._build_left(left)

        # SAĞ — Form
        right = ctk.CTkScrollableFrame(body, fg_color=BG_PANEL,
                                        scrollbar_button_color=BORDER,
                                        corner_radius=14,
                                        border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._build_right(right)

        # ALT — submit
        footer = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0,
                               height=72, border_width=0)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self._status_lbl = ctk.CTkLabel(footer, text="Görsel bekleniyor…",
                                          font=FONT_SMALL, text_color=TEXT_SEC)
        self._status_lbl.pack(side="left", padx=20)
        self._submit_btn = ctk.CTkButton(
            footer, text="🚀  Trendyol'a Canlı Yükle",
            font=FONT_BODY_BOLD, height=44, width=260, corner_radius=10,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color=BG_DARK,
            command=self._submit_to_trendyol, state="disabled")
        self._submit_btn.pack(side="right", padx=20, pady=14)
        self._batch_btn = ctk.CTkButton(
            footer, text="Batch Durumu",
            font=FONT_SMALL_BOLD, height=44, width=130, corner_radius=10,
            fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
            command=self._check_last_batch, state="disabled")
        self._batch_btn.pack(side="right", padx=4, pady=14)
        self._last_batch_id: str | None = None

    def _build_left(self, parent):
        ctk.CTkLabel(parent, text="1) Ürün Görseli",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(parent,
                      text="Sadece görseli yükle — Gemini Vision diğer her şeyi doldursun.",
                      font=FONT_TINY, text_color=TEXT_SEC).pack(
            anchor="w", padx=20, pady=(0, 14))

        self._img_box = ctk.CTkFrame(parent, fg_color=BG_DARK, corner_radius=12,
                                       width=320, height=320,
                                       border_width=2, border_color=ACCENT)
        self._img_box.pack(padx=20, pady=(0, 14))
        self._img_box.pack_propagate(False)
        self._img_lbl = ctk.CTkLabel(self._img_box,
                                       text="📷\n\nGörsel Yükle",
                                       font=FONT_HEAD, text_color=TEXT_MUT)
        self._img_lbl.pack(expand=True)

        ctk.CTkButton(parent, text="📁  Görsel Seç",
                      font=FONT_BODY_BOLD, height=42, corner_radius=10,
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=BG_DARK,
                      command=self._pick_image).pack(fill="x", padx=20, pady=(0, 10))

        self._ai_status = ctk.CTkLabel(parent,
                                         text="• Vision çağrısı bekleniyor",
                                         font=FONT_SMALL, text_color=TEXT_MUT,
                                         wraplength=320, justify="left")
        self._ai_status.pack(anchor="w", padx=20, pady=(8, 16))

        # Kategori hint (RAG için)
        ctk.CTkLabel(parent, text="Kategori İpucu (RAG)",
                      font=FONT_SMALL_BOLD, text_color=TEXT_SEC).pack(
            anchor="w", padx=20)
        self._cat_hint = ctk.CTkOptionMenu(
            parent, values=["(Otomatik)"] + list(SUGGESTED_CATEGORIES.keys()),
            fg_color=BG_DARK, button_color=BG_CARD,
            button_hover_color=BG_HOVER, text_color=TEXT_PRI,
            font=FONT_SMALL, dropdown_font=FONT_SMALL,
            corner_radius=8)
        self._cat_hint.set("(Otomatik)")
        self._cat_hint.pack(fill="x", padx=20, pady=(4, 18))

    def _build_right(self, parent):
        ctk.CTkLabel(parent, text="2) Otonom Doldurulan Form",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=18, pady=(18, 4))
        ctk.CTkLabel(parent,
                      text="Tüm alanları AI öneri olarak doldurur. İstediğini değiştir.",
                      font=FONT_TINY, text_color=TEXT_SEC).pack(
            anchor="w", padx=18, pady=(0, 14))

        # Basic
        self._add_field(parent, "Ürün Başlığı (title)", "title", lines=1)
        self._add_field(parent, "Açıklama (description)", "description", lines=4)

        # Identifiers
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=2)
        row.grid_columnconfigure(0, weight=1, uniform="ids")
        row.grid_columnconfigure(1, weight=1, uniform="ids")
        self._add_field(row, "Stok Kodu / productMainId", "productMainId",
                        grid=(0, 0))
        self._add_field(row, "Barkod (boş = otomatik)", "barcode",
                        grid=(0, 1))

        # Kategori & Trendyol categoryId
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=2)
        row2.grid_columnconfigure(0, weight=1, uniform="cat")
        row2.grid_columnconfigure(1, weight=1, uniform="cat")
        self._add_field(row2, "Kategori (AI)", "category",
                         grid=(0, 0))
        self._add_field(row2, "Trendyol Category ID", "categoryId",
                         grid=(0, 1), default="522")

        # Fiyat
        prc_row = ctk.CTkFrame(parent, fg_color="transparent")
        prc_row.pack(fill="x", padx=18, pady=2)
        for i in range(3):
            prc_row.grid_columnconfigure(i, weight=1, uniform="prc")
        self._add_field(prc_row, "Liste Fiyatı (TL)", "listPrice",
                         grid=(0, 0), on_change=self._update_profit)
        self._add_field(prc_row, "Satış Fiyatı (TL)", "salePrice",
                         grid=(0, 1), on_change=self._update_profit)
        self._add_field(prc_row, "Stok Adedi", "quantity",
                         grid=(0, 2), default="50")

        # Maliyet & KDV
        cost_row = ctk.CTkFrame(parent, fg_color="transparent")
        cost_row.pack(fill="x", padx=18, pady=2)
        for i in range(3):
            cost_row.grid_columnconfigure(i, weight=1, uniform="cost")
        self._add_field(cost_row, "Birim Maliyet (TL)", "productCost",
                         grid=(0, 0), default="0", on_change=self._update_profit)
        self._add_field(cost_row, "KDV (%)", "vatRate",
                         grid=(0, 1), default="18", on_change=self._update_profit)
        self._add_field(cost_row, "Boyutsal Ağırlık (kg)", "dimensionalWeight",
                         grid=(0, 2), default="1.0")

        # Görsel URL
        self._add_field(parent, "Görsel URL'leri (virgülle ayırın)",
                         "imageUrls", lines=2,
                         default="https://cdn.example.com/placeholder.jpg")

        # Kargo
        crg_row = ctk.CTkFrame(parent, fg_color="transparent")
        crg_row.pack(fill="x", padx=18, pady=(4, 4))
        ctk.CTkLabel(crg_row, text="Kargo Firması", font=FONT_SMALL_BOLD,
                      text_color=TEXT_SEC, anchor="w").pack(anchor="w")
        self._cargo_menu = ctk.CTkOptionMenu(
            crg_row, values=[c["name"] for c in self._cargo_list],
            fg_color=BG_DARK, button_color=BG_CARD,
            button_hover_color=BG_HOVER, text_color=TEXT_PRI,
            font=FONT_SMALL_BOLD, dropdown_font=FONT_SMALL,
            corner_radius=8, command=self._on_cargo_pick)
        self._cargo_menu.set("Aras Kargo")
        self._cargo_menu.pack(fill="x", pady=(4, 14))

        # ----- CFO Eklentisi: Canlı Net Kâr -----
        profit_card = ctk.CTkFrame(parent, fg_color=BG_DARK, corner_radius=12,
                                     border_width=2, border_color=ACCENT)
        profit_card.pack(fill="x", padx=18, pady=(10, 14))
        ctk.CTkLabel(profit_card,
                      text="💰  CANLI NET KÂR HESABI",
                      font=FONT_SMALL_BOLD, text_color=ACCENT).pack(
            anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(profit_card,
                      text="Trendyol %21.5 komisyon + 100 TL kargo + KDV "
                           "düşülerek hesaplanır.",
                      font=FONT_TINY, text_color=TEXT_MUT).pack(
            anchor="w", padx=14, pady=(0, 10))

        grid = ctk.CTkFrame(profit_card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 14))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="profit")
        profit_items = [
            ("Brüt Satış",   "gross",       INFO),
            ("Komisyon",     "commission",  WARNING),
            ("Kargo + KDV",  "fixed",       WARNING),
            ("NET KÂR",      "net",         ACCENT),
        ]
        for i, (lbl, key, col) in enumerate(profit_items):
            cell = ctk.CTkFrame(grid, fg_color=BG_PANEL, corner_radius=8)
            cell.grid(row=0, column=i, padx=4, sticky="ew", ipady=6)
            ctk.CTkLabel(cell, text=lbl, font=FONT_TINY,
                          text_color=TEXT_MUT).pack(anchor="w", padx=10, pady=(8, 0))
            v = ctk.CTkLabel(cell, text="0.00 TL",
                              font=FONT_SUB, text_color=col)
            v.pack(anchor="w", padx=10, pady=(0, 8))
            self._profit_labels[key] = v
        self._margin_lbl = ctk.CTkLabel(profit_card,
                                          text="Marj: %0.0   ·   Başabaş: 0 TL",
                                          font=FONT_SMALL_BOLD,
                                          text_color=TEXT_SEC)
        self._margin_lbl.pack(anchor="w", padx=14, pady=(0, 12))

    def _add_field(self, parent, label, key, lines=1, default="",
                    grid=None, on_change=None):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        if grid is not None:
            wrap.grid(row=grid[0], column=grid[1], padx=4, sticky="ew")
        else:
            wrap.pack(fill="x", padx=18, pady=2)
        ctk.CTkLabel(wrap, text=label, font=FONT_SMALL_BOLD,
                      text_color=TEXT_SEC, anchor="w").pack(anchor="w")
        if lines > 1:
            w = ctk.CTkTextbox(wrap, fg_color=BG_DARK, border_color=BORDER,
                                text_color=TEXT_PRI, font=FONT_SMALL,
                                height=22 * lines, border_width=1)
            if default:
                w.insert("1.0", default)
            w.pack(fill="x", pady=(4, 6))
        else:
            w = ctk.CTkEntry(wrap, fg_color=BG_DARK, border_color=BORDER,
                              text_color=TEXT_PRI, font=FONT_SMALL, height=34)
            if default:
                w.insert(0, default)
            w.pack(fill="x", pady=(4, 6))
            if on_change is not None:
                w.bind("<KeyRelease>", lambda e: on_change())
        self._fields[key] = w

    # --------- form get/set helpers ---------
    def _get(self, key: str, default="") -> str:
        w = self._fields.get(key)
        if w is None:
            return default
        if isinstance(w, ctk.CTkTextbox):
            return w.get("1.0", "end").strip() or default
        return w.get().strip() or default

    def _set(self, key: str, value):
        w = self._fields.get(key)
        if w is None:
            return
        v = "" if value is None else str(value)
        if isinstance(w, ctk.CTkTextbox):
            w.delete("1.0", "end")
            w.insert("1.0", v)
        else:
            w.delete(0, "end")
            w.insert(0, v)

    # --------- image + AI flow ---------
    def _pick_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Görsel", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not path:
            return
        self._image_path = path
        try:
            img = Image.open(path)
            img.thumbnail((300, 300))
            self._image_preview = ctk.CTkImage(
                light_image=img, dark_image=img, size=img.size)
            self._img_lbl.configure(image=self._image_preview, text="")
        except Exception:
            self._img_lbl.configure(text="📷", image=None)

        # Vision kuyruğa
        self._ai_status.configure(text="🧠  Gemini Vision analizi başladı…",
                                    text_color=ACCENT)
        self._status_lbl.configure(text="AI analiz ediyor…", text_color=ACCENT)
        self._submit_btn.configure(state="disabled")

        hint = self._cat_hint.get()
        if hint == "(Otomatik)":
            hint = ""
        analyze_product_image_async(
            path,
            lambda res, err: self.after(0, lambda: self._on_vision_done(res, err)),
            category_hint=hint, brand=BRAND_NAME)

    def _on_vision_done(self, result, error):
        if error or not result:
            self._ai_status.configure(
                text=f"⚠  AI başarısız: {error or 'bilinmeyen'}\nFormu manuel doldurun.",
                text_color=DANGER)
            self._status_lbl.configure(text="AI başarısız", text_color=DANGER)
            # En azından bir productMainId üret
            if self._image_path and not self._get("productMainId"):
                base = os.path.splitext(os.path.basename(self._image_path))[0]
                code = "CTK-" + str(abs(hash(base)) % 100000)
                self._set("productMainId", code)
            self._submit_btn.configure(state="normal")
            return

        # Form alanlarını otomatik doldur
        self._set("title", result.get("title", ""))
        self._set("description", result.get("description", ""))
        self._set("category", result.get("category", ""))
        self._set("salePrice", f"{result.get('sale_price', 0):.2f}")
        self._set("listPrice", f"{result.get('list_price', 0):.2f}")
        self._set("dimensionalWeight", f"{result.get('weight_kg', 1.0):.2f}")
        # Trendyol category id öner
        cat = result.get("category", "")
        cid = SUGGESTED_CATEGORIES.get(cat, {}).get("id", 522)
        vat = SUGGESTED_CATEGORIES.get(cat, {}).get("vat", 18)
        self._set("categoryId", str(cid))
        self._set("vatRate", str(vat))

        # productMainId otomatik
        base = os.path.splitext(os.path.basename(self._image_path or "X"))[0]
        code = "CTK-" + str(abs(hash(base)) % 100000)
        self._set("productMainId", code)

        self._ai_status.configure(
            text=f"✓  AI doldurma tamamlandı (kategori: {cat or '?'})\n"
                  f"    {len(result.get('attributes') or {})} öznitelik tespit edildi.",
            text_color=ACCENT)
        self._status_lbl.configure(text="Form hazır — yüklemeye hazırız",
                                     text_color=ACCENT)
        self._submit_btn.configure(state="normal")
        self._last_vision = result
        self._update_profit()

    # --------- cargo ---------
    def _on_cargo_loaded(self, lst):
        if lst:
            self._cargo_list = lst
            names = [c.get("name", str(c.get("id"))) for c in lst]
            self._cargo_menu.configure(values=names)
            if "Aras Kargo" in names:
                self._cargo_menu.set("Aras Kargo")
                self._on_cargo_pick("Aras Kargo")

    def _on_cargo_pick(self, name):
        for c in self._cargo_list:
            if c.get("name") == name:
                self._cargo_id = int(c.get("id", 10))
                break

    # --------- live profit ---------
    def _update_profit(self):
        try:
            sp = float(self._get("salePrice", "0") or 0)
        except ValueError:
            sp = 0
        try:
            cost = float(self._get("productCost", "0") or 0)
        except ValueError:
            cost = 0
        try:
            vat = float(self._get("vatRate", "18") or 18) / 100
        except ValueError:
            vat = 0.18

        r = estimate_net_profit(sale_price=sp, commission_pct=0.215,
                                  cargo_cost=100, vat_rate=vat,
                                  product_cost=cost)
        sym = "TL"
        self._profit_labels["gross"].configure(text=f"{r['gross']:,.2f} {sym}")
        self._profit_labels["commission"].configure(
            text=f"{r['commission']:,.2f} {sym}")
        self._profit_labels["fixed"].configure(
            text=f"{r['cargo']+r['kdv']:,.2f} {sym}")
        net_col = ACCENT if r["net"] > 0 else DANGER
        self._profit_labels["net"].configure(text=f"{r['net']:,.2f} {sym}",
                                                text_color=net_col)
        self._margin_lbl.configure(
            text=f"Marj: %{r['margin_pct']:.1f}   ·   "
                  f"Başabaş: {r['breakeven']:,.0f} {sym}",
            text_color=ACCENT if r["margin_pct"] > 10 else WARNING)

    # --------- submit to Trendyol ---------
    def _submit_to_trendyol(self):
        if self._submitting:
            return
        try:
            payload = self._build_payload()
        except ValueError as exc:
            messagebox.showerror("Eksik Alan", str(exc), parent=self)
            return

        confirm = messagebox.askyesno(
            "Onay — Canlı Yükleme",
            f"Bu ürün gerçek Trendyol mağazasına gönderilecek.\n\n"
            f"• Başlık: {payload['title']}\n"
            f"• Stok kodu: {payload['productMainId']}\n"
            f"• Satış fiyatı: {payload['salePrice']} TL\n"
            f"• Stok: {payload['quantity']} adet\n"
            f"• Kargo: {self._cargo_menu.get()}\n\n"
            "Devam edilsin mi?",
            parent=self)
        if not confirm:
            return

        self._submitting = True
        self._submit_btn.configure(state="disabled", text="Gönderiliyor…")
        self._status_lbl.configure(text="Trendyol'a POST atılıyor…",
                                     text_color=WARNING)
        self._client.create_product_async(
            payload,
            lambda res, err: self.after(0, lambda: self._on_submit_done(res, err, payload)))

    def _build_payload(self) -> dict:
        title = self._get("title")
        if not title:
            raise ValueError("Başlık (title) zorunlu.")
        try:
            sp = float(self._get("salePrice"))
            lp = float(self._get("listPrice", str(sp * 1.15)))
            qty = int(float(self._get("quantity", "1") or 1))
            cid = int(float(self._get("categoryId", "522")))
            vat = int(float(self._get("vatRate", "18")))
            dw  = float(self._get("dimensionalWeight", "1.0"))
        except ValueError:
            raise ValueError("Sayısal alanları kontrol edin (fiyat/stok/kategori).")
        pmid = self._get("productMainId") or ("CTK-" + str(abs(hash(title)) % 100000))
        barcode = self._get("barcode") or ("869" +
            str(abs(hash(pmid)) % 10000000000).zfill(10))

        urls = [u.strip() for u in self._get("imageUrls", "").split(",")
                if u.strip()]
        if not urls:
            raise ValueError("En az 1 görsel URL gerekli.")

        # Vision'dan attributes varsa kullan
        attrs_dict = {}
        if hasattr(self, "_last_vision"):
            attrs_dict = self._last_vision.get("attributes") or {}
        attrs_list = [{"attributeName": k, "attributeValue": v}
                       for k, v in attrs_dict.items()]

        return TrendyolClient.build_payload(
            barcode=barcode, title=title, product_main_id=pmid,
            category_id=cid, quantity=qty, list_price=lp, sale_price=sp,
            description=self._get("description") or title,
            images=urls, attributes=attrs_list, stock_code=pmid,
            cargo_company_id=self._cargo_id, vat_rate=vat,
            dimensional_weight=dw, brand_id=BRAND_ID)

    def _on_submit_done(self, result, error, payload):
        self._submitting = False
        if error:
            self._submit_btn.configure(state="normal",
                                         text="🚀  Trendyol'a Canlı Yükle")
            self._status_lbl.configure(text=f"Hata: {error[:80]}",
                                         text_color=DANGER)
            messagebox.showerror("Trendyol Hatası",
                                  f"Yükleme başarısız:\n\n{error}", parent=self)
            return

        batch_id = (result or {}).get("batchRequestId", "?")
        self._last_batch_id = batch_id
        self._submit_btn.configure(state="normal",
                                     text="✓ Yüklendi — Yeni Ekle",
                                     fg_color=ACCENT)
        self._status_lbl.configure(
            text=f"✓ batchRequestId={batch_id}",
            text_color=ACCENT)
        self._batch_btn.configure(state="normal")

        # Lokal DB'ye de ekle
        try:
            db.add_product({
                "sku": payload["productMainId"],
                "name": payload["title"],
                "category": self._get("category") or "Genel",
                "stock": payload["quantity"],
                "price": payload["salePrice"],
                "cost": float(self._get("productCost", "0") or 0),
                "supplier_id": 1,
                "barcode": payload["barcode"],
                "reorder_point": max(10, payload["quantity"] // 5),
                "reorder_qty": payload["quantity"],
                "lead_time": 7,
                "platforms": ["Trendyol"],
                "return_rate": 0.04,
                "status": "Satışta",
                "image_path": self._image_path,
                "monthly_sales": [0] * 12,
                "weight_kg": float(self._get("dimensionalWeight", "1.0") or 1),
            })
            db.add_notification(7, "success",
                                 f"Trendyol Yüklendi: {payload['productMainId']}",
                                 f"'{payload['title']}' canlı mağazaya gönderildi. "
                                 f"Batch ID: {batch_id}",
                                 target_sku=payload["productMainId"],
                                 action="Takip Et")
        except Exception as exc:
            print("DB kaydı atlandı:", exc)

        messagebox.showinfo(
            "Başarılı",
            f"Ürün Trendyol'a gönderildi.\n\n"
            f"Batch ID: {batch_id}\n\n"
            "Yayına geçişi kontrol etmek için 'Batch Durumu' butonunu kullanın.",
            parent=self)
        if self.on_save:
            try:
                self.on_save()
            except Exception:
                pass

    def _check_last_batch(self):
        if not self._last_batch_id:
            return
        def _run():
            try:
                status = self._client.get_batch_status(self._last_batch_id)
                self.after(0, lambda: self._show_batch_status(status))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Hata", f"Batch sorgulanamadı: {exc}", parent=self))
        threading.Thread(target=_run, daemon=True).start()

    def _show_batch_status(self, status):
        items = status.get("items", []) if isinstance(status, dict) else []
        msg = f"Batch: {self._last_batch_id}\n\n"
        if not items:
            msg += json.dumps(status, indent=2, ensure_ascii=False)[:600]
        else:
            for it in items[:5]:
                st = it.get("status", "?")
                code = it.get("requestItem", {}).get("item", {}).get("productMainId", "")
                msg += f"• {code}: {st}\n"
                fail = it.get("failureReasons") or []
                for f in fail[:2]:
                    msg += f"    └ {f}\n"
        messagebox.showinfo("Batch Durumu", msg, parent=self)


