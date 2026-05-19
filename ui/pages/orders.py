import customtkinter as ctk
from tkinter import filedialog, messagebox
import webbrowser
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from ui.theme import *
from ui.widgets import SortableTable, Pill, ChartHover
from core import database as db
from core import i18n, currency, analytics, ai_engine


class OrdersPage(ctk.CTkFrame):
    def __init__(self, parent, tab: str = None):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self._tab = tab or "active"
        self._build()

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        sc = self._scroll

        hdr = ctk.CTkFrame(sc, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 4))
        ctk.CTkLabel(hdr, text=i18n.t("orders.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(hdr, text=i18n.t("common.export") + " (CSV)",
                      fg_color=BG_PANEL, hover_color=BG_HOVER, text_color=INFO,
                      height=36, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=self._export_csv).pack(side="right")

        ctk.CTkLabel(sc, text=i18n.t("orders.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(2, 16))

        all_orders = db.get_orders()
        active = [o for o in all_orders if o["status"] != "İade"]
        returns = [o for o in all_orders if o["status"] == "İade"]

        sum_row = ctk.CTkFrame(sc, fg_color="transparent")
        sum_row.pack(fill="x", padx=22, pady=(0, 16))
        _st_cnt = {}
        for o in active:
            _st_cnt[o["status"]] = _st_cnt.get(o["status"], 0) + 1
        sums = [
            ("Aktif Toplam", str(len(active)), TEXT_PRI),
            ("Bekliyor", str(_st_cnt.get("Bekliyor", 0)), WARNING),
            ("Kargoda", str(_st_cnt.get("Kargoda", 0)), INFO),
            ("Teslim Edildi", str(_st_cnt.get("Teslim Edildi", 0)), ACCENT),
            ("İade (Ayri)", str(len(returns)), DANGER),
        ]
        for i, (lbl, val, col) in enumerate(sums):
            sum_row.grid_columnconfigure(i, weight=1)
            c = ctk.CTkFrame(sum_row, fg_color=BG_PANEL, corner_radius=12,
                             border_width=1, border_color=BORDER)
            c.grid(row=0, column=i, padx=6, sticky="ew")
            ctk.CTkLabel(c, text=lbl, font=FONT_SMALL_BOLD,
                         text_color=TEXT_SEC).pack(anchor="w", padx=14, pady=(14, 2))
            ctk.CTkLabel(c, text=val, font=FONT_KPI,
                         text_color=col).pack(anchor="w", padx=14, pady=(0, 14))

        tabs = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=10,
                            border_width=1, border_color=BORDER)
        tabs.pack(anchor="w", padx=22, pady=(0, 12))
        self._tab_btns = {}
        for key, label in [("active", i18n.t("orders.active_tab") + f"  ({len(active)})"),
                            ("returns", i18n.t("orders.returns_tab") + f"  ({len(returns)})")]:
            btn = ctk.CTkButton(tabs, text=label, height=36, corner_radius=8,
                                font=FONT_SMALL_BOLD,
                                fg_color=ACCENT if key == self._tab else "transparent",
                                hover_color=BG_HOVER,
                                text_color=TEXT_PRI if key == self._tab else TEXT_SEC,
                                command=lambda k=key: self._switch_tab(k))
            btn.pack(side="left", padx=4, pady=4)
            self._tab_btns[key] = btn

        self._table_card = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                         border_width=1, border_color=BORDER)
        self._table_card.pack(fill="x", padx=22, pady=(0, 22))
        self._render_table()

    def _switch_tab(self, k):
        self._tab = k
        for kk, btn in self._tab_btns.items():
            btn.configure(fg_color=ACCENT if kk == k else "transparent",
                          text_color=TEXT_PRI if kk == k else TEXT_SEC)
        self._render_table()

    def _render_table(self):
        for w in self._table_card.winfo_children():
            w.destroy()

        title = i18n.t("orders.live_feed") if self._tab == "active" else i18n.t("orders.returns_tab")
        ctk.CTkLabel(self._table_card, text=title, font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))

        orders = db.get_orders(self._tab)
        cols = ["Sipariş No", i18n.t("common.platform"), "Ürün",
                i18n.t("common.amount"), i18n.t("common.city"),
                i18n.t("common.date"), i18n.t("common.status")]
        rows = []
        for o in orders:
            rows.append({
                "cells": [o["id"], o["platform"], o["product"][:28],
                           currency.format(o["total"]),
                           o["city"], o["date"][:10], o["status"]],
                "data": o,
            })
        status_colors = {
            "Bekliyor": WARNING, "Kargoda": INFO,
            "Teslim Edildi": ACCENT, "İade": DANGER,
        }
        table_holder = ctk.CTkFrame(self._table_card, fg_color="transparent")
        table_holder.pack(fill="x", padx=14, pady=(0, 14))
        SortableTable(table_holder, cols, rows,
                      on_row_click=lambda o: self._open_detail(o),
                      status_col=6, status_colors=status_colors).pack(fill="x")

    def _open_detail(self, o):
        OrderDetailWindow(self, o)

    def _export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                              filetypes=[("CSV", "*.csv")])
        if not path:
            return
        orders = db.get_orders(self._tab)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Platform", "SKU", "Ürün", "Adet", "Tutar",
                        "Komisyon", "Kargo", "Şehir", "Durum", "Tarih"])
            for o in orders:
                w.writerow([o["id"], o["platform"], o["sku"], o["product"],
                             o["qty"], o["total"], o["commission"], o["cargo_cost"],
                             o["city"], o["status"], o["date"]])
        messagebox.showinfo("OK", f"Disa aktarildi:\n{path}", parent=self)


class OrderDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, order):
        super().__init__(parent)
        self.order = order
        self.title(f"Siparis Detayi — {order['id']}")
        self.geometry("960x900")
        self.minsize(820, 720)
        self.configure(fg_color=BG_DARK)
        self.grab_set()
        self._build()

    def _build(self):
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                     scrollbar_button_color=BORDER)
        sf.pack(fill="both", expand=True)
        o = self.order

        head = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                            border_width=2, border_color=o["platform_color"])
        head.pack(fill="x", padx=18, pady=(18, 12))
        top = ctk.CTkFrame(head, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(top, text=o["id"], font=FONT_H1,
                     text_color=TEXT_PRI).pack(side="left")
        Pill(top, f"  {o['platform']}  ", o["platform_color"], BG_CARD).pack(side="left", padx=10)
        _st = {"Bekliyor": WARNING, "Kargoda": INFO,
               "Teslim Edildi": ACCENT, "İade": DANGER}
        Pill(top, f"  {o['status']}  ",
             _st.get(o["status"], TEXT_PRI), BG_CARD).pack(side="right")

        meta = ctk.CTkFrame(head, fg_color="transparent")
        meta.pack(fill="x", padx=18, pady=(0, 8))
        ctk.CTkLabel(meta, text=f"Tarih: {o['date']}  ·  Fatura: {o['invoice']}",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w")

        if o["status"] in ("Bekliyor", "Kargoda") and o.get("deadline_hours", 0) > 0:
            cd = ctk.CTkFrame(head, fg_color=WARNING_BG, corner_radius=10)
            cd.pack(fill="x", padx=18, pady=(8, 16))
            ctk.CTkLabel(cd, text=f"⏱  {i18n.t('orders.countdown')}: {o['deadline_hours']} saat",
                         font=FONT_BODY_BOLD,
                         text_color=WARNING).pack(anchor="w", padx=14, pady=10)
        else:
            ctk.CTkFrame(head, height=6, fg_color="transparent").pack()

        prod = db.get_product(o["sku"]) or {"cost": 0, "name": o["product"]}
        breakdown = analytics.order_breakdown(o, product_cost=prod.get("cost", 0))

        bd_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
        bd_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(bd_card, text=i18n.t("orders.cost_breakdown") + " — Seffaf Hesap",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(bd_card, text="Müşteriden tahsil edilen tutardan her kalemden kim ne aldigi:",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w", padx=18, pady=(0, 12))

        left = ctk.CTkFrame(bd_card, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(18, 8), pady=(0, 18))

        items = [
            ("Müşteri Odemesi (Brut)",
             currency.format(breakdown["total"]), ACCENT, "+"),
            (f"KDV (%{breakdown['kdv_rate']*100:.0f}) → Devlete",
             currency.format(breakdown["kdv"]), WARNING, "-"),
            (f"Platform Komisyonu (%{breakdown['commission_rate']*100:.0f}) → {o['platform']}",
             currency.format(breakdown["commission"]), DANGER, "-"),
            ("Kargo Bedeli → Kargo Şirketi",
             currency.format(breakdown["cargo"]), DANGER, "-"),
            (f"Urun Maliyeti ({o['qty']} adet)",
             currency.format(breakdown["product_cost"]), DANGER, "-"),
        ]
        for lbl, val, col, sign in items:
            rf = ctk.CTkFrame(left, fg_color="transparent")
            rf.pack(fill="x", pady=3)
            ctk.CTkLabel(rf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, text=f"{sign} {val}", font=FONT_SMALL_BOLD,
                         text_color=col).pack(side="right")

        ctk.CTkFrame(left, height=1, fg_color=BORDER).pack(fill="x", pady=(8, 6))
        rf = ctk.CTkFrame(left, fg_color="transparent")
        rf.pack(fill="x", pady=2)
        ctk.CTkLabel(rf, text="Net Kâr (Bu Sipariş)", font=FONT_BODY_BOLD,
                     text_color=TEXT_PRI).pack(side="left")
        col = ACCENT if breakdown["net_profit"] > 0 else DANGER
        ctk.CTkLabel(rf, text=currency.format(breakdown["net_profit"]),
                     font=FONT_HEAD, text_color=col).pack(side="right")
        rf2 = ctk.CTkFrame(left, fg_color="transparent")
        rf2.pack(fill="x", pady=2)
        ctk.CTkLabel(rf2, text="Kâr Marjı (Brute Göre)", font=FONT_SMALL,
                     text_color=TEXT_SEC).pack(side="left")
        ctk.CTkLabel(rf2, text=f"%{breakdown['margin_pct']:.1f}",
                     font=FONT_SMALL_BOLD,
                     text_color=col).pack(side="right")

        right = ctk.CTkFrame(bd_card, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(8, 18), pady=(0, 18))
        try:
            fig, ax = plt.subplots(figsize=(4.2, 3.0), facecolor=BG_PANEL)
            ax.set_facecolor(BG_PANEL)
            labels = ["KDV", "Komisyon", "Kargo", "Maliyet", "Net Kâr"]
            values = [max(0, breakdown["kdv"]), max(0, breakdown["commission"]),
                      max(0, breakdown["cargo"]), max(0, breakdown["product_cost"]),
                      max(0, breakdown["net_profit"])]
            colors_p = [WARNING, DANGER, "#A78BFA", "#F87171", ACCENT]
            ax.pie(values, labels=labels, colors=colors_p, autopct="%1.0f%%",
                   startangle=90, textprops={"color": TEXT_PRI, "fontsize": 8},
                   wedgeprops={"linewidth": 1.5, "edgecolor": BG_PANEL})
            fig.tight_layout(pad=0.8)
            cv = FigureCanvasTkAgg(fig, right)
            cv.draw()
            cv.get_tk_widget().pack(fill="both")
            sym = currency.symbol() if hasattr(currency, "symbol") else "TL"
            ChartHover(cv, ax,
                        fmt=lambda lbl, val, s=sym: f"{lbl}: {val:,.2f} {s}",
                        pie_data=list(zip(labels, values)))
            plt.close(fig)
        except Exception:
            pass

        cust = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                            border_width=1, border_color=BORDER)
        cust.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(cust, text="Müşteri & Teslimat", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        c_rows = [
            (i18n.t("common.customer"), o["customer"]),
            (i18n.t("common.city") + " / Ilce", f"{o['city']} / {o['district']}"),
            ("Adres", o["address"]),
            ("Müşteri Notu", o["note"] or "-"),
        ]
        for lbl, val in c_rows:
            rf = ctk.CTkFrame(cust, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=3)
            ctk.CTkLabel(rf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC, width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, text=val, font=FONT_SMALL_BOLD,
                         text_color=WARNING if "Notu" in lbl and val != "-" else TEXT_PRI,
                         wraplength=600, justify="left").pack(side="left")
        ctk.CTkFrame(cust, height=10, fg_color="transparent").pack()

        cargo = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                              border_width=1, border_color=BORDER)
        cargo.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(cargo, text="Kargo & Takip", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        k_rows = [
            ("Kargo Firmasi", o["cargo"]),
            ("Takip No", o["tracking"] or "Henuz yok"),
            ("Tahmini Teslimat", f"{o['est_days']} gun" if o["est_days"] > 0 else "Teslim edildi"),
        ]
        for lbl, val in k_rows:
            rf = ctk.CTkFrame(cargo, fg_color="transparent")
            rf.pack(fill="x", padx=18, pady=3)
            ctk.CTkLabel(rf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC, width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(rf, text=val, font=FONT_SMALL_BOLD,
                         text_color=TEXT_PRI).pack(side="left")
        if o.get("tracking_url"):
            btns = ctk.CTkFrame(cargo, fg_color="transparent")
            btns.pack(fill="x", padx=18, pady=(8, 14))
            ctk.CTkButton(btns, text=f"→ {o['cargo']} Sitesinde Takip Et",
                          fg_color=INFO, hover_color="#3B82F6", text_color=TEXT_PRI,
                          height=34, font=FONT_SMALL_BOLD, corner_radius=8,
                          command=lambda: webbrowser.open(o["tracking_url"])).pack(side="left")

        up = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                          border_width=1, border_color=BORDER)
        up.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(up, text="Belgeler", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        bf = ctk.CTkFrame(up, fg_color="transparent")
        bf.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(bf, text="📄 " + i18n.t("orders.upload_invoice"),
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=TEXT_PRI,
                      height=36, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=lambda: self._upload_doc("invoice")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bf, text="🏷  " + i18n.t("orders.upload_label"),
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=TEXT_PRI,
                      height=36, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=lambda: self._upload_doc("label")).pack(side="left")

        pkg = ai_engine.packaging_recommendation(prod if prod else o)
        pkg_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                 border_width=1, border_color=BORDER)
        pkg_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(pkg_card, text="AI Paketleme Önerisi",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(pkg_card, text=pkg, font=FONT_SMALL,
                     text_color=TEXT_PRI, wraplength=880,
                     justify="left").pack(anchor="w", padx=18, pady=(0, 16))

        if o.get("reviews"):
            rv_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                    border_width=1, border_color=BORDER)
            rv_card.pack(fill="x", padx=18, pady=(0, 18))
            ctk.CTkLabel(rv_card, text=i18n.t("orders.reviews"),
                         font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
            for rv in o["reviews"]:
                stars = "★" * rv["rating"] + "☆" * (5 - rv["rating"])
                rc = ctk.CTkFrame(rv_card, fg_color=BG_DARK, corner_radius=10)
                rc.pack(fill="x", padx=18, pady=4)
                head_rc = ctk.CTkFrame(rc, fg_color="transparent")
                head_rc.pack(fill="x", padx=14, pady=(10, 2))
                ctk.CTkLabel(head_rc, text=rv["user"], font=FONT_SMALL_BOLD,
                             text_color=TEXT_PRI).pack(side="left")
                ctk.CTkLabel(head_rc, text=stars, font=FONT_SMALL_BOLD,
                             text_color=WARNING).pack(side="right")
                ctk.CTkLabel(rc, text=rv["text"], font=FONT_SMALL,
                             text_color=TEXT_PRI, wraplength=860,
                             justify="left").pack(anchor="w", padx=14, pady=(0, 6))
                suggested = ai_engine.review_reply(rv["text"], rv["rating"])
                ctk.CTkLabel(rc, text="AI Önerisi: " + suggested, font=FONT_TINY,
                             text_color=INFO, wraplength=860,
                             justify="left").pack(anchor="w", padx=14, pady=(0, 10))

    def _upload_doc(self, kind):
        path = filedialog.askopenfilename(
            filetypes=[("PDF/Görsel", "*.pdf *.png *.jpg *.jpeg")])
        if not path:
            return
        col = "invoice_path" if kind == "invoice" else "label_path"
        db.execute(f"UPDATE orders SET {col}=? WHERE id=?", (path, self.order["id"]))
        messagebox.showinfo("OK", "Belge eklendi.", parent=self)
