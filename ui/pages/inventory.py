import customtkinter as ctk
from tkinter import filedialog, messagebox
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
import os
from PIL import Image
from ui.theme import *
from ui.widgets import Tooltip, Pill, ChartHover
from core import database as db
from core import i18n, currency, analytics
from core.mock_data import MONTHS, BOM, MATERIALS


class InventoryPage(ctk.CTkFrame):
    def __init__(self, parent, focus_sku: str = None):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self._tab = "products"
        self._focus = focus_sku
        self._build()
        if focus_sku:
            self.after(150, lambda: self._open_detail_by_sku(focus_sku))

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        sc = self._scroll

        hdr = ctk.CTkFrame(sc, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 4))
        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=i18n.t("inventory.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w")
        ctk.CTkLabel(left, text=i18n.t("inventory.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", pady=(2, 0))

        ctk.CTkButton(hdr, text="+ " + i18n.t("inventory.smart_add"),
                      font=FONT_BODY_BOLD, fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color=TEXT_PRI, height=42, corner_radius=10,
                      command=self._open_smart_add).pack(side="right")

        ctk.CTkButton(hdr, text="⟳ Trendyol'dan Senkronize Et",
                      font=FONT_SMALL_BOLD, fg_color=BG_CARD,
                      hover_color=BG_HOVER, text_color=INFO,
                      border_width=1, border_color=INFO,
                      height=42, width=210, corner_radius=10,
                      command=self._sync_from_trendyol).pack(side="right", padx=8)

        tabs = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=10,
                            border_width=1, border_color=BORDER)
        tabs.pack(anchor="w", padx=28, pady=(16, 12))
        self._tab_btns = {}
        for key, label in [("products", "Ürünler (Önem Sırasında)"),
                            ("materials", "Ortak Malzemeler"),
                            ("suppliers", i18n.t("inventory.supplier_health"))]:
            btn = ctk.CTkButton(tabs, text=label, height=36, corner_radius=8,
                                font=FONT_SMALL_BOLD,
                                fg_color=ACCENT if key == self._tab else "transparent",
                                hover_color=BG_HOVER,
                                text_color=TEXT_PRI if key == self._tab else TEXT_SEC,
                                command=lambda k=key: self._switch_tab(k))
            btn.pack(side="left", padx=4, pady=4)
            self._tab_btns[key] = btn

        summary_row = ctk.CTkFrame(sc, fg_color="transparent")
        summary_row.pack(fill="x", padx=22, pady=(0, 18))
        products = db.get_products()
        total = len(products)
        critical = sum(1 for p in products if p["stock"] <= p["reorder_point"])
        active = total - critical
        port_value = sum(p["stock"] * p["price"] for p in products)
        summaries = [
            (i18n.t("inventory.total_products"), str(total), TEXT_PRI),
            ("Satışta", str(active), ACCENT),
            (i18n.t("inventory.critical_stock"), str(critical), DANGER),
            (i18n.t("inventory.portfolio_value"), currency.format(port_value), INFO),
        ]
        for i, (lbl, val, col) in enumerate(summaries):
            summary_row.grid_columnconfigure(i, weight=1)
            c = ctk.CTkFrame(summary_row, fg_color=BG_PANEL, corner_radius=12,
                             border_width=1, border_color=BORDER)
            c.grid(row=0, column=i, padx=6, sticky="ew")
            ctk.CTkLabel(c, text=lbl, font=FONT_SMALL_BOLD,
                         text_color=TEXT_SEC).pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(c, text=val, font=FONT_KPI,
                         text_color=col).pack(anchor="w", padx=16, pady=(0, 14))

        self._body = ctk.CTkFrame(sc, fg_color="transparent")
        self._body.pack(fill="x", padx=22, pady=(0, 22))
        self._render_tab()

    def _switch_tab(self, key):
        self._tab = key
        for k, btn in self._tab_btns.items():
            btn.configure(fg_color=ACCENT if k == key else "transparent",
                          text_color=TEXT_PRI if k == key else TEXT_SEC)
        self._render_tab()

    def _render_tab(self):
        for w in self._body.winfo_children():
            w.destroy()
        if self._tab == "products":
            self._render_products()
        elif self._tab == "materials":
            self._render_materials()
        else:
            self._render_suppliers()

    def _render_products(self):
        products = db.get_products()
        for p in products:
            p["_importance"] = analytics.importance_score(p)
            p["_abc"] = analytics.abc_class(p["_importance"])
            p["_critical"] = p["stock"] <= p["reorder_point"]
        products.sort(key=lambda x: (not x["_critical"], -x["_importance"]))

        if not products:
            empty = ctk.CTkFrame(self._body, fg_color=BG_PANEL,
                                  corner_radius=14, border_width=2,
                                  border_color=INFO)
            empty.pack(fill="x", pady=10)
            ctk.CTkLabel(empty, text="📦  Envanter Boş",
                          font=FONT_HEAD,
                          text_color=INFO).pack(anchor="w", padx=22, pady=(20, 4))
            ctk.CTkLabel(empty,
                text="Trendyol Satıcı Panelinizdeki gerçek ürünleri çekmek için "
                       "yukarıdaki '⟳ Trendyol'dan Senkronize Et' butonuna basın. "
                       "Yeni bir ürün eklemek isterseniz '+ Akıllı Ürün Ekle' "
                       "butonunu kullanın (Gemini Vision ile fotoğraf analizi).",
                font=FONT_SMALL, text_color=TEXT_SEC, wraplength=900,
                justify="left").pack(anchor="w", padx=22, pady=(0, 22))
            return

        grid = ctk.CTkFrame(self._body, fg_color="transparent")
        grid.pack(fill="x")
        for col in range(2):
            grid.grid_columnconfigure(col, weight=1)
        for i, p in enumerate(products):
            self._product_card(grid, p, i // 2, i % 2)

    def _product_card(self, parent, p, r, c):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                            border_width=2,
                            border_color=DANGER if p["_critical"] else BORDER,
                            cursor="hand2")
        card.grid(row=r, column=c, padx=8, pady=8, sticky="ew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)

        img_box = ctk.CTkFrame(inner, fg_color=BG_DARK, corner_radius=10,
                               width=120, height=120)
        img_box.pack(side="left", padx=(0, 16))
        img_box.pack_propagate(False)
        try:
            if p.get("image_path") and os.path.exists(p["image_path"]):
                img = Image.open(p["image_path"]).resize((110, 110))
                ph = ctk.CTkImage(light_image=img, dark_image=img, size=(110, 110))
                ctk.CTkLabel(img_box, text="", image=ph).pack(expand=True)
            else:
                cat = (p.get("category") or "").lower()
                ic = "👕" if "giyim" in cat else "👟" if "ayakkabi" in cat else "🎀"
                ctk.CTkLabel(img_box, text=ic, font=("Segoe UI Symbol", 48),
                             text_color=TEXT_SEC).pack(expand=True)
        except Exception:
            ctk.CTkLabel(img_box, text="📦", font=("Segoe UI Symbol", 48),
                         text_color=TEXT_SEC).pack(expand=True)

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        top = ctk.CTkFrame(info, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=p["name"], font=FONT_HEAD,
                     text_color=TEXT_PRI, anchor="w").pack(side="left")
        abc_col = {"A": ACCENT, "B": INFO, "C": TEXT_MUT}[p["_abc"]]
        Pill(top, f"  {p['_abc']}  ", abc_col, BG_CARD).pack(side="right")

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(meta, text=p["sku"], font=FONT_TINY,
                     text_color=TEXT_MUT).pack(side="left")
        ctk.CTkLabel(meta, text="  ·  ", font=FONT_TINY,
                     text_color=TEXT_MUT).pack(side="left")
        ctk.CTkLabel(meta, text=p["category"], font=FONT_TINY,
                     text_color=TEXT_SEC).pack(side="left")
        ctk.CTkLabel(meta, text="  ·  ", font=FONT_TINY,
                     text_color=TEXT_MUT).pack(side="left")
        ctk.CTkLabel(meta, text=f"Önem %{p['_importance']*100:.0f}",
                     font=FONT_TINY, text_color=abc_col).pack(side="left")

        kpi = ctk.CTkFrame(info, fg_color="transparent")
        kpi.pack(fill="x", pady=(2, 10))

        stock_frame = ctk.CTkFrame(kpi, fg_color=BG_DARK, corner_radius=8,
                                    cursor="hand2")
        stock_frame.pack(side="left", padx=(0, 8))
        sf_inner = ctk.CTkFrame(stock_frame, fg_color="transparent")
        sf_inner.pack(padx=12, pady=8)
        stock_lbl = "Stok"
        sc_col = DANGER if p["_critical"] else TEXT_PRI
        ctk.CTkLabel(sf_inner, text=stock_lbl, font=FONT_TINY,
                     text_color=TEXT_SEC).pack(anchor="w")
        sline = ctk.CTkFrame(sf_inner, fg_color="transparent")
        sline.pack(anchor="w")
        ctk.CTkLabel(sline, text=str(p["stock"]),
                     font=FONT_SUB, text_color=sc_col).pack(side="left")
        if p["_critical"]:
            ctk.CTkLabel(sline, text="  !", font=FONT_HEAD,
                         text_color=DANGER).pack(side="left")
        for w in [stock_frame, sf_inner] + list(sf_inner.winfo_children()):
            w.bind("<Button-1>", lambda e, prod=p: self._open_mrp(prod), add="+")
        Tooltip(stock_frame, "Stok detayi ve MRP raporu için tiklayin")

        profit_frame = ctk.CTkFrame(kpi, fg_color=BG_DARK, corner_radius=8)
        profit_frame.pack(side="left", padx=(0, 8))
        margin = (p["price"] - p["cost"]) / p["price"] * 100 if p["price"] else 0
        ctk.CTkLabel(profit_frame, text=f"  Kar %  ",
                     font=FONT_TINY, text_color=TEXT_SEC).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(profit_frame, text=f"  %{margin:.0f}  ",
                     font=FONT_SUB, text_color=ACCENT).pack(anchor="w", padx=12, pady=(0, 8))

        status_frame = ctk.CTkFrame(kpi, fg_color=BG_DARK, corner_radius=8)
        status_frame.pack(side="left")
        status_col = DANGER if p["_critical"] else ACCENT
        status_txt = "Kritik Stok" if p["_critical"] else "Satışta"
        ctk.CTkLabel(status_frame, text=f"  Durum  ", font=FONT_TINY,
                     text_color=TEXT_SEC).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(status_frame, text=f"  {status_txt}  ",
                     font=FONT_SMALL_BOLD, text_color=status_col).pack(anchor="w", padx=12, pady=(0, 8))

        actions = ctk.CTkFrame(info, fg_color="transparent")
        actions.pack(fill="x")
        if p["_critical"]:
            ctk.CTkButton(actions, text=i18n.t("inventory.reorder_now"),
                          fg_color=WARNING, hover_color="#D97706",
                          text_color=BG_DARK, height=32, corner_radius=8,
                          font=FONT_SMALL_BOLD,
                          command=lambda prod=p: self._open_mrp(prod)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text=i18n.t("common.detail"),
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
                      height=32, corner_radius=8, font=FONT_SMALL_BOLD,
                      command=lambda prod=p: self._open_detail(prod)).pack(side="left")

        for w in [card, inner, info, top, meta]:
            try:
                w.bind("<Button-1>", lambda e, prod=p: self._open_detail(prod), add="+")
            except Exception:
                pass

    def _render_materials(self):
        card = ctk.CTkFrame(self._body, fg_color=BG_PANEL, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x")
        ctk.CTkLabel(card, text="Ortak Ambalaj & Etiket Malzemeleri (Ürün Ağaçları)",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card,
                     text="Malzeme stoğu kritiğe düştüğünde, bağımlı ürünlerinizin yayını "
                          "etkilenebilir. Aşağıdaki MRP önerilerine göre aksiyon alın.",
                     font=FONT_SMALL, text_color=TEXT_SEC,
                     wraplength=900, justify="left").pack(anchor="w", padx=18, pady=(0, 10))

        materials = db.get_materials()
        rows = []
        status_colors = {"KRİTİK": DANGER, "Yeterli": ACCENT}
        for m in materials:
            crit = m["stock"] <= m["reorder_point"]
            using_skus = [sku for sku, items in BOM.items()
                           if any(c == m["code"] for c, _ in items)]
            rows.append({
                "cells": [
                    m["code"],
                    m["name"],
                    int(m["stock"]),
                    int(m["reorder_point"]),
                    currency.format(m["unit_cost"]),
                    "KRİTİK" if crit else "Yeterli",
                    ", ".join(using_skus) if using_skus else "—",
                ],
                "data": m,
            })

        from ui.widgets import SortableTable
        wrap = ctk.CTkFrame(card, fg_color="transparent")
        wrap.pack(fill="x", padx=14, pady=(0, 14))
        SortableTable(
            wrap,
            columns=["Kod", "Malzeme", "Stok", "Yeniden Sip.",
                       "Birim Maliyet", "Durum", "Bağlı Ürünler"],
            rows=rows,
            column_widths=[90, 220, 70, 100, 120, 90, None],
            status_col=5,
            status_colors=status_colors,
            export_filename="ortak_malzemeler.csv",
        ).pack(fill="x")

    def _render_suppliers(self):
        suppliers = db.get_suppliers()
        for s in suppliers:
            self._supplier_card(self._body, s)

    def _supplier_card(self, parent, s):
        health = analytics.supplier_health(s)
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=12,
                            border_width=2, border_color=health["color"])
        card.pack(fill="x", padx=0, pady=6)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(top, text=s["name"], font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(side="left")
        Pill(top, f"  {health['rating']}  ",
             health["color"], BG_CARD).pack(side="right")
        ctk.CTkLabel(top, text=f"Skor: %{health['score']*100:.0f}",
                     font=FONT_BODY_BOLD,
                     text_color=health["color"]).pack(side="right", padx=12)

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(meta, text=f"{s['contact']}  ·  {s['phone']}  ·  {s['city']}",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w")

        metrics = ctk.CTkFrame(card, fg_color="transparent")
        metrics.pack(fill="x", padx=18, pady=(4, 8))
        m_items = [
            ("Zamanli Teslim", f"%{health['on_time']*100:.0f}",
             ACCENT if health['on_time'] >= 0.9 else (WARNING if health['on_time'] >= 0.8 else DANGER)),
            ("Defekt Orani", f"%{health['defect']*100:.1f}",
             ACCENT if health['defect'] <= 0.02 else (WARNING if health['defect'] <= 0.04 else DANGER)),
            ("Tedarik Süresi", f"{s['lead_time_actual']:.1f}g (hedef {s['lead_time_target']}g)",
             ACCENT if s['lead_time_actual'] <= s['lead_time_target'] else WARNING),
            ("Toplam Sipariş", str(s["total_orders"]), TEXT_PRI),
        ]
        for i, (lbl, val, col) in enumerate(m_items):
            metrics.grid_columnconfigure(i, weight=1)
            f = ctk.CTkFrame(metrics, fg_color=BG_DARK, corner_radius=8)
            f.grid(row=0, column=i, padx=4, sticky="ew")
            ctk.CTkLabel(f, text=lbl, font=FONT_TINY,
                         text_color=TEXT_SEC).pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(f, text=val, font=FONT_SUB,
                         text_color=col).pack(anchor="w", padx=10, pady=(0, 8))

        impact = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=10)
        impact.pack(fill="x", padx=18, pady=(4, 12))
        imp_inner = ctk.CTkFrame(impact, fg_color="transparent")
        imp_inner.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(imp_inner, text="Bu Tedarikçinin Size Etkisi (Tahmini):",
                     font=FONT_SMALL_BOLD, text_color=TEXT_PRI).pack(anchor="w")
        ctk.CTkLabel(imp_inner,
                     text=f"+ Yarattigi Deger: {currency.format(health['estimated_value_added'])}",
                     font=FONT_SMALL, text_color=ACCENT).pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(imp_inner,
                     text=f"- Tahmini Kayip Geliriniz: {currency.format(health['estimated_lost_revenue'])}",
                     font=FONT_SMALL, text_color=DANGER if health['estimated_lost_revenue'] > 1000 else TEXT_SEC).pack(anchor="w")
        if health["score"] < 0.7:
            ctk.CTkLabel(imp_inner,
                         text="• AI Tavsiyesi: Bu tedarikciye alternatif arayisi önerilir. "
                              "Sektör ortalamasi %90 zamanli teslimat.",
                         font=FONT_SMALL, text_color=WARNING,
                         wraplength=900, justify="left").pack(anchor="w", pady=(6, 0))

    def _open_detail(self, p):
        DetailWindow(self, p)

    def _open_detail_by_sku(self, sku):
        prod = db.get_product(sku)
        if prod:
            self._open_detail(prod)

    def _open_mrp(self, p):
        MRPWindow(self, p)

    def _open_smart_add(self):
        # Yeni: Trendyol canlı API + Gemini Vision (RAG)
        from ui.smart_add import TrendyolSmartAddWindow
        TrendyolSmartAddWindow(
            self, on_save=lambda: self._switch_tab(self._tab))

    def _sync_from_trendyol(self):
        from tkinter import messagebox
        from core import trendyol_sync
        confirm = messagebox.askyesno(
            "Trendyol Senkronizasyonu",
            "Trendyol Satıcı Panelinden gerçek ürün ve sipariş verileri çekilsin mi?\n\n"
            "• Ürünler (son 100)\n"
            "• Siparişler (son 30 gün)\n"
            "• Hakediş / Settlements (eğer 556 hatası alırsak Trendyol "
            "destek talebimiz mevcut)\n\n"
            "Bu işlem birkaç saniye sürebilir.",
            parent=self)
        if not confirm:
            return

        def _on_done(result):
            self.after(0, lambda: self._show_sync_result(result))

        trendyol_sync.sync_all_async(days_back=30, callback=_on_done)
        messagebox.showinfo(
            "Senkronizasyon Başladı",
            "Trendyol API'sine bağlanılıyor. Sonuç hazırlandığında "
            "bilgilendirme alacaksınız.",
            parent=self)

    def _show_sync_result(self, result: dict):
        from tkinter import messagebox
        lines = []
        for src, info in result.items():
            if not isinstance(info, dict):
                continue
            if info.get("ok"):
                lines.append(f"✓ {src}: {info.get('saved',0)}/{info.get('fetched',0)} kayıt")
            else:
                err = info.get("user_message") or info.get("error", "?")
                lines.append(f"✗ {src}: {err[:120]}")
        messagebox.showinfo("Senkronizasyon Tamamlandı",
                             "\n\n".join(lines), parent=self)
        try:
            self._switch_tab(self._tab)
        except Exception:
            pass


class DetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, product):
        super().__init__(parent)
        self.product = product
        self.fresh = db.get_product(product["sku"]) or product
        self.title(f"{self.fresh['sku']} — {self.fresh['name']}")
        self.geometry("980x780")
        self.configure(fg_color=BG_DARK)
        self.minsize(880, 680)
        self.grab_set()

        self._build()

    def _build(self):
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                     scrollbar_button_color=BORDER)
        sf.pack(fill="both", expand=True)
        p = self.fresh

        top = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                           border_width=1, border_color=BORDER)
        top.pack(fill="x", padx=18, pady=(18, 12))

        ti = ctk.CTkFrame(top, fg_color="transparent")
        ti.pack(fill="x", padx=18, pady=16)

        img_box = ctk.CTkFrame(ti, fg_color=BG_DARK, corner_radius=10,
                                width=180, height=180)
        img_box.pack(side="left", padx=(0, 18))
        img_box.pack_propagate(False)
        try:
            if p.get("image_path") and os.path.exists(p["image_path"]):
                img = Image.open(p["image_path"]).resize((170, 170))
                ph = ctk.CTkImage(light_image=img, dark_image=img, size=(170, 170))
                ctk.CTkLabel(img_box, text="", image=ph).pack(expand=True)
            else:
                cat = (p.get("category") or "").lower()
                ic = "👕" if "giyim" in cat else "👟" if "ayakkabi" in cat else "🎀"
                ctk.CTkLabel(img_box, text=ic, font=("Segoe UI Symbol", 72),
                             text_color=TEXT_SEC).pack(expand=True)
        except Exception:
            ctk.CTkLabel(img_box, text="📦", font=("Segoe UI Symbol", 72),
                         text_color=TEXT_SEC).pack(expand=True)

        info = ctk.CTkFrame(ti, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(info, text=p["name"], font=FONT_H1,
                     text_color=TEXT_PRI).pack(anchor="w")
        ctk.CTkLabel(info, text=f"SKU: {p['sku']}  ·  Barkod: {p.get('barcode', '-')}  ·  "
                                  f"Tedarikci: {p.get('supplier_name', '-')}",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w", pady=(4, 12))

        edit_row = ctk.CTkFrame(info, fg_color="transparent")
        edit_row.pack(anchor="w", fill="x")

        self._fields = {}
        for label, key in [("Fiyat (TL)", "price"), ("Maliyet (TL)", "cost"),
                            ("Stok", "stock"), ("Reorder Pt.", "reorder_point")]:
            cell = ctk.CTkFrame(edit_row, fg_color="transparent")
            cell.pack(side="left", padx=(0, 12))
            ctk.CTkLabel(cell, text=label, font=FONT_TINY,
                         text_color=TEXT_SEC).pack(anchor="w")
            e = ctk.CTkEntry(cell, width=110, height=34, fg_color=BG_DARK,
                             border_color=BORDER, text_color=TEXT_PRI,
                             font=FONT_SMALL_BOLD)
            e.insert(0, str(p.get(key, "")))
            e.pack(anchor="w")
            self._fields[key] = e
        ctk.CTkButton(edit_row, text=i18n.t("common.save"), fg_color=ACCENT,
                      hover_color=ACCENT_H, text_color=TEXT_PRI, height=34,
                      font=FONT_SMALL_BOLD, corner_radius=8,
                      command=self._save).pack(side="left", padx=(8, 0), pady=(14, 0))

        analytics_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                       border_width=1, border_color=BORDER)
        analytics_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(analytics_card, text="Performans & Talep Tahmini",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))

        sales = p.get("monthly_sales") or [0] * 12
        forecast = analytics.forecast(sales, horizon=3)

        fig, ax = plt.subplots(figsize=(8.4, 3.0), facecolor=BG_PANEL)
        ax.set_facecolor(BG_PANEL)
        ax.plot(range(len(sales)), sales, color=ACCENT, marker="o", linewidth=2,
                label="Gercek Satis")
        f_x = list(range(len(sales) - 1, len(sales) + len(forecast)))
        f_y = [sales[-1]] + forecast
        ax.plot(f_x, f_y, color=WARNING, marker="o", linewidth=2, linestyle="--",
                label="Tahmin (3 Ay)")
        ax.fill_between(range(len(sales)), sales, alpha=0.15, color=ACCENT)
        ax.set_xticks(range(len(sales) + len(forecast)))
        labels = MONTHS + ["+1", "+2", "+3"]
        ax.set_xticklabels(labels, color=TEXT_SEC, fontsize=9)
        ax.tick_params(colors=TEXT_SEC, labelsize=9)
        ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        ax.legend(facecolor=BG_CARD, labelcolor=TEXT_PRI, fontsize=9,
                  edgecolor=BORDER, framealpha=0.85)
        fig.tight_layout(pad=1.2)
        cv = FigureCanvasTkAgg(fig, analytics_card)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=14, pady=(4, 14))
        ChartHover(cv, ax,
                    fmt=lambda lbl, y: f"{lbl}  ·  {y:,.0f} adet",
                    x_labels=labels)
        plt.close(fig)

        mrp = analytics.mrp_report(p)
        kpi_row = ctk.CTkFrame(sf, fg_color="transparent")
        kpi_row.pack(fill="x", padx=18, pady=(0, 12))
        kpi_items = [
            ("Önem (ABC)", f"{analytics.abc_class(analytics.importance_score(p))}",
             ACCENT),
            ("Günlük Talep", f"{mrp['avg_daily_demand']:.1f} adet", INFO),
            ("Stok Yeterliligi", f"{mrp['days_of_stock_left']:.1f} gun",
             DANGER if mrp['days_of_stock_left'] < mrp['lead_time'] else ACCENT),
            ("Yeniden Sip. Pt.", f"{mrp['reorder_point']:.0f}", TEXT_PRI),
            ("EOQ", f"{mrp['eoq']:.0f} adet", TEXT_PRI),
            ("İade Orani", f"%{p.get('return_rate', 0)*100:.1f}",
             DANGER if p.get('return_rate', 0) > 0.08 else ACCENT),
        ]
        for i, (lbl, val, col) in enumerate(kpi_items):
            kpi_row.grid_columnconfigure(i, weight=1)
            cf = ctk.CTkFrame(kpi_row, fg_color=BG_PANEL, corner_radius=10,
                              border_width=1, border_color=BORDER)
            cf.grid(row=0, column=i, padx=4, sticky="ew")
            ctk.CTkLabel(cf, text=lbl, font=FONT_TINY,
                         text_color=TEXT_SEC).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(cf, text=val, font=FONT_SUB,
                         text_color=col).pack(anchor="w", padx=12, pady=(0, 10))

        sim_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                 border_width=1, border_color=BORDER)
        sim_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(sim_card, text="Fiyat & Reklam Simulasyonu (ML Parametre)",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(sim_card,
                     text="Parametreleri degistirin: AI elastikiyet modeli ile beklenen gelir/kar etkisini gosterir.",
                     font=FONT_SMALL, text_color=TEXT_SEC,
                     wraplength=900).pack(anchor="w", padx=18, pady=(0, 12))

        ctrl = ctk.CTkFrame(sim_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=18)

        self._price_slider = self._slider_row(ctrl, "Fiyat Degisimi", -30, 30, 0, "%")
        self._ad_slider = self._slider_row(ctrl, "Reklam Butce Degisimi", -50, 100, 0, "%")

        self._sim_result = ctk.CTkFrame(sim_card, fg_color=BG_DARK, corner_radius=10)
        self._sim_result.pack(fill="x", padx=18, pady=(12, 14))
        self._update_sim()

        if p.get("description"):
            d_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                   border_width=1, border_color=BORDER)
            d_card.pack(fill="x", padx=18, pady=(0, 16))
            ctk.CTkLabel(d_card, text="Açıklama", font=FONT_HEAD,
                         text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(14, 4))
            ctk.CTkLabel(d_card, text=p["description"], font=FONT_SMALL,
                         text_color=TEXT_PRI, wraplength=900,
                         justify="left").pack(anchor="w", padx=18, pady=(0, 14))

    def _slider_row(self, parent, label, mn, mx, default, suffix):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=4)
        ctk.CTkLabel(f, text=label, font=FONT_SMALL_BOLD,
                     text_color=TEXT_PRI, width=200, anchor="w").pack(side="left")
        val_lbl = ctk.CTkLabel(f, text=f"{default}{suffix}", font=FONT_SMALL_BOLD,
                                text_color=ACCENT, width=70)
        val_lbl.pack(side="right")
        slider = ctk.CTkSlider(f, from_=mn, to=mx, number_of_steps=mx - mn,
                                fg_color=BG_DARK, progress_color=ACCENT,
                                button_color=ACCENT, button_hover_color=ACCENT_H,
                                command=lambda v, lab=val_lbl, s=suffix: (
                                    lab.configure(text=f"{int(v)}{s}"),
                                    self._update_sim()))
        slider.set(default)
        slider.pack(side="left", fill="x", expand=True, padx=12)
        return slider

    def _update_sim(self):
        if not hasattr(self, "_sim_result"):
            return
        for w in self._sim_result.winfo_children():
            w.destroy()
        price_d = int(self._price_slider.get())
        ad_d = int(self._ad_slider.get())
        sim = analytics.parameter_simulation(self.fresh, price_d, ad_d)

        items = [
            ("Satis Adet Degisimi", f"{sim['qty_delta_pct']:+.1f}%",
             ACCENT if sim['qty_delta_pct'] >= 0 else DANGER),
            ("Gelir Degisimi", f"{currency.format(sim['revenue_delta']) if sim['revenue_delta'] >= 0 else '-' + currency.format(-sim['revenue_delta'])}",
             ACCENT if sim['revenue_delta'] >= 0 else DANGER),
            ("Kar Degisimi", f"{currency.format(sim['profit_delta']) if sim['profit_delta'] >= 0 else '-' + currency.format(-sim['profit_delta'])}",
             ACCENT if sim['profit_delta'] >= 0 else DANGER),
        ]
        inner = ctk.CTkFrame(self._sim_result, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)
        for i, (lbl, val, col) in enumerate(items):
            inner.grid_columnconfigure(i, weight=1)
            f = ctk.CTkFrame(inner, fg_color="transparent")
            f.grid(row=0, column=i, padx=12, sticky="w")
            ctk.CTkLabel(f, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC).pack(anchor="w")
            ctk.CTkLabel(f, text=val, font=FONT_HEAD,
                         text_color=col).pack(anchor="w")

    def _save(self):
        try:
            data = {}
            for k, e in self._fields.items():
                v = e.get().strip()
                if k in ("stock", "reorder_point"):
                    data[k] = int(v)
                else:
                    data[k] = float(v)
            db.update_product(self.fresh["sku"], **data)
            messagebox.showinfo("OK", i18n.t("profile.saved"), parent=self)
            self.destroy()
        except Exception as ex:
            messagebox.showerror("Hata", str(ex), parent=self)


class MRPWindow(ctk.CTkToplevel):
    def __init__(self, parent, product):
        super().__init__(parent)
        self.product = product
        self.title(f"MRP Raporu — {product['sku']}")
        self.geometry("780x720")
        self.configure(fg_color=BG_DARK)
        self.grab_set()
        self._build()

    def _build(self):
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                     scrollbar_button_color=BORDER)
        sf.pack(fill="both", expand=True)
        p = self.product
        mrp = analytics.mrp_report(p)

        head = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                            border_width=2, border_color=DANGER if mrp["is_critical"] else BORDER)
        head.pack(fill="x", padx=18, pady=18)
        ctk.CTkLabel(head, text="MRP RAPORU (Material Requirements Planning)",
                     font=FONT_TINY, text_color=DANGER if mrp["is_critical"] else ACCENT,
                     fg_color=BG_CARD, corner_radius=4).pack(
            anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(head, text=p["name"], font=FONT_H1,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18)
        ctk.CTkLabel(head, text=f"SKU: {p['sku']}  ·  Tedarikci: {p.get('supplier_name', '-')}",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w", padx=18, pady=(4, 16))

        rec = ctk.CTkFrame(sf, fg_color=ACCENT_DK if mrp["is_critical"] else BG_PANEL,
                           corner_radius=14, border_width=2,
                           border_color=ACCENT if mrp["is_critical"] else BORDER)
        rec.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(rec, text="AKSIYON ONERISI",
                     font=FONT_TINY, text_color=ACCENT).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(rec, text=f"{mrp['suggested_qty']} adet siparis verin",
                     font=FONT_H1, text_color=TEXT_PRI).pack(anchor="w", padx=18)
        ctk.CTkLabel(rec, text=f"Tahmini Maliyet: {currency.format(mrp['estimated_cost'])}",
                     font=FONT_HEAD, text_color=WARNING).pack(anchor="w", padx=18, pady=(4, 4))
        when = "BUGÜN" if mrp["reorder_by_days"] <= 0 else f"{mrp['reorder_by_days']:.0f} gun icinde"
        ctk.CTkLabel(rec, text=f"Siparis Verilmesi Gereken: {when}",
                     font=FONT_BODY_BOLD,
                     text_color=DANGER if mrp["reorder_by_days"] <= 1 else WARNING).pack(
            anchor="w", padx=18, pady=(0, 16))

        metrics_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                     border_width=1, border_color=BORDER)
        metrics_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(metrics_card, text="MATEMATIKSEL HESAPLAMA",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))

        rows = [
            ("Mevcut Stok",             f"{p['stock']} adet"),
            ("Aylık Ortalama Talep",    f"{mrp['avg_monthly_demand']:.1f} adet"),
            ("Günlük Ortalama Talep",   f"{mrp['avg_daily_demand']:.2f} adet"),
            ("Talep Standart Sapma",    f"{mrp['demand_std_monthly']:.2f} adet (aylik)"),
            ("Tedarik Süresi",          f"{mrp['lead_time']} gun"),
            ("Servis Seviyesi (Z=1.65)", f"%{mrp['service_level']*100:.0f}"),
            ("Emniyet Stogu",           f"{mrp['safety_stock']:.0f} adet"),
            ("Yeniden Sipariş Noktasi (s)", f"{mrp['reorder_point']:.0f} adet"),
            ("Ekonomik Sipariş Miktari (EOQ)", f"{mrp['eoq']:.0f} adet"),
            ("Stok Yeterliligi",        f"{mrp['days_of_stock_left']:.1f} gun"),
        ]
        for lbl, val in rows:
            rf = ctk.CTkFrame(metrics_card, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(rf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC, anchor="w", width=320).pack(side="left")
            ctk.CTkLabel(rf, text=val, font=FONT_SMALL_BOLD,
                         text_color=TEXT_PRI).pack(side="left")
        ctk.CTkFrame(metrics_card, height=10, fg_color="transparent").pack()

        po_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
        po_card.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkLabel(po_card, text="TEDARIKCI SIPARIS EMRI (OTOMATIK)",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))

        po_rows = [
            ("Tedarikçi",       p.get("supplier_name", "-")),
            ("SKU",             p["sku"]),
            ("Ürün Adı",        p["name"]),
            ("Miktar",          f"{mrp['suggested_qty']} adet"),
            ("Birim Maliyet",   currency.format(p.get("cost", 0))),
            ("Toplam Maliyet",  currency.format(mrp["estimated_cost"])),
            ("Tahmini Teslimat", f"{p['lead_time']} gun icinde"),
        ]
        for lbl, val in po_rows:
            rf = ctk.CTkFrame(po_card, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(rf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC, width=180, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, text=val, font=FONT_SMALL_BOLD,
                         text_color=TEXT_PRI).pack(side="left")

        btns = ctk.CTkFrame(po_card, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(12, 16))
        ctk.CTkButton(btns, text="Sipariş Emrini Oluştur",
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT_PRI,
                      height=40, font=FONT_BODY_BOLD, corner_radius=10,
                      command=self._create_order).pack(side="left")
        ctk.CTkButton(btns, text=i18n.t("common.close"),
                      fg_color=BG_CARD, hover_color=BG_HOVER,
                      text_color=TEXT_PRI, height=40, font=FONT_BODY_BOLD,
                      corner_radius=10, command=self.destroy).pack(side="right")

    def _create_order(self):
        from core import ai_engine
        p = self.product
        mrp = analytics.mrp_report(p)
        db.add_notification(8, "success", f"Siparis Emri: {p['sku']}",
                             f"{p['name']} icin {mrp['suggested_qty']} adet "
                             f"({currency.format(mrp['estimated_cost'])}) siparis emri olusturuldu. "
                             f"Tedarikci: {p.get('supplier_name', '-')}.",
                             target_sku=p["sku"])
        db.log_agent_action("create_purchase_order", p["sku"], {
            "qty": mrp["suggested_qty"], "cost": mrp["estimated_cost"]
        }, "applied")
        messagebox.showinfo("Tamam",
                             f"Siparis emri olusturuldu.\n\n"
                             f"{mrp['suggested_qty']} adet × {currency.format(p['cost'])} = "
                             f"{currency.format(mrp['estimated_cost'])}",
                             parent=self)
        self.destroy()


class SmartAddWindow(ctk.CTkToplevel):
    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Akıllı Ürün Ekle — Görsel Tabanli")
        self.geometry("680x740")
        self.configure(fg_color=BG_DARK)
        self.grab_set()
        self.img_path = None
        self._build()

    def _build(self):
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                     scrollbar_button_color=BORDER)
        sf.pack(fill="both", expand=True)

        ctk.CTkLabel(sf, text="Akıllı Ürün Ekle", font=FONT_H1,
                     text_color=TEXT_PRI).pack(anchor="w", padx=22, pady=(22, 4))
        ctk.CTkLabel(sf, text="1) Once ürün görseli yukleyin. "
                              "2) AI tüm alanlari önerilen olarak doldurur. "
                              "3) İştediginiz alani duzenleyip kaydedin.",
                     font=FONT_SMALL, text_color=TEXT_SEC,
                     wraplength=620, justify="left").pack(anchor="w", padx=22, pady=(0, 16))

        img_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                 border_width=2, border_color=ACCENT)
        img_card.pack(fill="x", padx=22, pady=(0, 14))
        self._img_box = ctk.CTkFrame(img_card, fg_color=BG_DARK, corner_radius=10,
                                       width=220, height=220)
        self._img_box.pack(pady=18)
        self._img_box.pack_propagate(False)
        self._img_lbl = ctk.CTkLabel(self._img_box, text="📷\nGörsel Yukle",
                                       font=FONT_HEAD, text_color=TEXT_SEC)
        self._img_lbl.pack(expand=True)
        ctk.CTkButton(img_card, text="Görsel Sec & AI Analizi Başlat",
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT_PRI,
                      height=40, corner_radius=10, font=FONT_BODY_BOLD,
                      command=self._pick_image).pack(pady=(0, 18))

        self._form = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        self._form.pack(fill="x", padx=22, pady=(0, 14))
        ctk.CTkLabel(self._form, text="Önerilen Alanlar (Duzenleyebilirsiniz)",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))

        self.fields = {}
        field_defs = [
            ("SKU",                "sku"),
            ("Ürün Adı",           "name"),
            ("Kategori",           "category"),
            ("Stok Miktari",       "stock"),
            ("Satis Fiyati (TL)",  "price"),
            ("Maliyet (TL)",       "cost"),
            ("Tedarikçi ID (1-5)", "supplier_id"),
            ("Barkod",             "barcode"),
        ]
        for label, key in field_defs:
            rf = ctk.CTkFrame(self._form, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(rf, text=label, font=FONT_SMALL_BOLD,
                         text_color=TEXT_SEC, width=160, anchor="w").pack(side="left")
            e = ctk.CTkEntry(rf, fg_color=BG_DARK, border_color=BORDER,
                             text_color=TEXT_PRI, height=34, font=FONT_SMALL)
            e.pack(side="left", fill="x", expand=True)
            self.fields[key] = e

        ctk.CTkFrame(self._form, height=10, fg_color="transparent").pack()

        ctk.CTkButton(sf, text=i18n.t("common.save"),
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT_PRI,
                      height=44, font=FONT_BODY_BOLD, corner_radius=10,
                      command=self._save).pack(fill="x", padx=22, pady=(0, 18))

    def _pick_image(self):
        path = filedialog.askopenfilename(
            filetypes=[("Görsel", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not path:
            return
        self.img_path = path
        try:
            img = Image.open(path).resize((200, 200))
            ph = ctk.CTkImage(light_image=img, dark_image=img, size=(200, 200))
            self._img_lbl.configure(image=ph, text="")
        except Exception:
            self._img_lbl.configure(text="📷")
        ctk.CTkLabel(self._img_box, text="AI analiz ediyor...",
                      font=FONT_SMALL, text_color=ACCENT).pack()
        self._ai_suggest(path)

    def _ai_suggest(self, path):
        from core import ai_engine
        new_id = f"NW-{abs(hash(path)) % 900 + 100}"
        self.fields["sku"].delete(0, "end")
        self.fields["sku"].insert(0, new_id)

        def _on_result(result, err):
            self.after(0, lambda: self._apply_ai_suggestion(result, err))
        ai_engine.analyze_product_image(path, _on_result)

    def _apply_ai_suggestion(self, result, err):
        if err or not result:
            fn = os.path.basename(self.img_path or "").lower()
            cat = "Giyim"
            if any(k in fn for k in ["sneaker", "shoe", "ayakkabi", "bot"]):
                cat = "Ayakkabi"
            elif any(k in fn for k in ["bere", "fular", "cüzdan", "kemer"]):
                cat = "Aksesuar"
            fallback = {
                "name": "Yeni Ürün (manuel duzenleyin)",
                "category": cat, "stock": "50", "price": "299.00",
                "cost": "95.00", "supplier_id": "1",
                "barcode": f"869{abs(hash(self.img_path or '')) % 10000000000:010d}",
            }
            for k, v in fallback.items():
                if k in self.fields:
                    self.fields[k].delete(0, "end")
                    self.fields[k].insert(0, str(v))
            if err:
                messagebox.showwarning("AI Uyarısi",
                    f"Gemini Vision basarisiz: {err}\nManuel doldurun.",
                    parent=self)
            return

        suggestions = {
            "name":        result.get("name", ""),
            "category":    result.get("category", "Giyim"),
            "stock":       "50",
            "price":       f"{result.get('price', 0):.2f}",
            "cost":        f"{result.get('cost', 0):.2f}",
            "supplier_id": "1",
            "barcode":     f"869{abs(hash(self.img_path or '')) % 10000000000:010d}",
        }
        for k, v in suggestions.items():
            if k in self.fields:
                self.fields[k].delete(0, "end")
                self.fields[k].insert(0, str(v))

    def _save(self):
        try:
            data = {
                "sku":           self.fields["sku"].get().strip().upper(),
                "name":          self.fields["name"].get().strip(),
                "category":      self.fields["category"].get().strip(),
                "stock":         int(self.fields["stock"].get()),
                "price":         float(self.fields["price"].get()),
                "cost":          float(self.fields["cost"].get()),
                "supplier_id":   int(self.fields["supplier_id"].get()),
                "barcode":       self.fields["barcode"].get().strip(),
                "image_path":    self.img_path,
                "reorder_point": 20,
                "reorder_qty":   50,
                "lead_time":     7,
                "platforms":     ["Trendyol"],
                "return_rate":   0.04,
                "status":        "Satışta",
                "monthly_sales": [0] * 12,
                "weight_kg":     0.3,
            }
            if not data["sku"] or not data["name"]:
                messagebox.showerror("Hata", "SKU ve Ürün Adı zorunlu.", parent=self)
                return
            db.add_product(data)
            messagebox.showinfo("OK", "Ürün eklendi.", parent=self)
            if self.on_save:
                self.on_save()
            self.destroy()
        except Exception as ex:
            messagebox.showerror("Hata", str(ex), parent=self)
