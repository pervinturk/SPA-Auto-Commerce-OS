import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from ui.theme import *
from ui.widgets import KPICard, Tooltip, ChartHover, SortableTable
from core import database as db
from core import i18n, currency
from core.mock_data import MONTHS, REVENUE, PROFIT, UPCOMING_PAYOUTS


class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, navigator=None):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self.navigator = navigator or (lambda *_: None)
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        sc = self._scroll
        ctk.CTkLabel(sc, text=i18n.t("dashboard.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(22, 4))
        ctk.CTkLabel(sc, text=i18n.t("dashboard.subtitle") + "  ·  " +
                     i18n.t("dashboard.click_to_open"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(0, 20))

        from core import credentials
        is_live = credentials.is_configured(credentials.PLATFORM_TRENDYOL)

        if not is_live:
            from ui.lock_screen import IntegrationLockCard
            lock = IntegrationLockCard(
                sc, page_name="Ana Panel",
                on_configure=lambda: self.navigator("profile"))
            lock.pack(fill="x", padx=22, pady=(0, 16))

        if is_live:
            orders_all = db.get_orders("active")
            active_orders = len(orders_all)
            revenue_now = sum(o.get("total", 0) for o in orders_all)
            profit_now = int(revenue_now * 0.34)
            upcoming = 0
        else:
            active_orders = 0
            revenue_now = 0
            profit_now = 0
            upcoming = 0

        kpi_row = ctk.CTkFrame(sc, fg_color="transparent")
        kpi_row.pack(fill="x", padx=22, pady=(0, 16))

        kpis = [
            (i18n.t("dashboard.monthly_revenue"), currency.format(revenue_now),
             f"+12% {i18n.t('common.revenue').lower()}", ACCENT, lambda: self.navigator("finance"), "📈"),
            (i18n.t("dashboard.net_profit"), currency.format(profit_now),
             "+5%", ACCENT, lambda: self.navigator("finance"), "💰"),
            (i18n.t("dashboard.active_orders"), str(active_orders),
             f"2 {i18n.t('status.pending').lower()}", WARNING,
             lambda: self.navigator("orders"), "📦"),
            (i18n.t("dashboard.upcoming_payout"), currency.format(upcoming),
             "2 gun", INFO, lambda: self.navigator("finance"), "🏦"),
        ]
        for i, (lbl, val, delta, col, cmd, ic) in enumerate(kpis):
            kpi_row.grid_columnconfigure(i, weight=1)
            c = KPICard(kpi_row, lbl, val, delta, col, on_click=cmd, icon=ic)
            c.grid(row=0, column=i, padx=6, sticky="ew")
            Tooltip(c, i18n.t("dashboard.click_to_open"))

        mid = ctk.CTkFrame(sc, fg_color="transparent")
        mid.pack(fill="x", padx=22, pady=(0, 14))
        mid.grid_columnconfigure(0, weight=6)
        mid.grid_columnconfigure(1, weight=4)

        ch_card = ctk.CTkFrame(mid, fg_color=BG_PANEL, corner_radius=14,
                               border_width=1, border_color=BORDER)
        ch_card.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        ctk.CTkLabel(ch_card, text="Aylık Ciro & Kâr Trendi",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(ch_card, text=f"Birim: 1.000 {currency.symbol()}",
                     font=FONT_TINY, text_color=TEXT_SEC).pack(anchor="w", padx=18)

        fig, ax = plt.subplots(figsize=(7.4, 3.4), facecolor=BG_PANEL)
        ax.set_facecolor(BG_PANEL)
        x = np.arange(len(MONTHS))
        scale = 1 / (currency.rate_usd_try() * 1000) if currency.get() == "USD" else 1 / 1000
        rev_s = [r * scale for r in REVENUE]
        prof_s = [p * scale for p in PROFIT]
        ax.bar(x - 0.2, rev_s, 0.38, color=ACCENT, alpha=0.9, label=i18n.t("common.revenue"))
        ax.bar(x + 0.2, prof_s, 0.38, color=INFO, alpha=0.9, label=i18n.t("common.profit"))
        ax.set_xticks(x)
        ax.set_xticklabels(MONTHS, color=TEXT_SEC, fontsize=9)
        ax.tick_params(colors=TEXT_SEC, labelsize=9)
        ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        ax.legend(facecolor=BG_CARD, labelcolor=TEXT_PRI, fontsize=9, framealpha=0.85,
                  edgecolor=BORDER)
        fig.tight_layout(pad=1.2)
        cv = FigureCanvasTkAgg(fig, ch_card)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=12, pady=(6, 14))
        sym = currency.symbol()
        ChartHover(cv, ax,
                    fmt=lambda lbl, y: f"{lbl}  ·  {y*1000:,.0f} {sym}",
                    x_labels=MONTHS)
        plt.close(fig)

        al_card = ctk.CTkFrame(mid, fg_color=BG_PANEL, corner_radius=14,
                               border_width=1, border_color=BORDER)
        al_card.grid(row=0, column=1, padx=(10, 0), sticky="nsew")

        al_hdr = ctk.CTkFrame(al_card, fg_color="transparent")
        al_hdr.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(al_hdr, text="Akıl Hocası Uyarılari",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(al_hdr, text="Tumu →", width=80, height=28,
                      fg_color=BG_CARD, hover_color=BG_HOVER,
                      text_color=INFO, font=FONT_SMALL, corner_radius=6,
                      command=lambda: self.navigator("advisor")).pack(side="right")

        _col = {"danger": DANGER, "warning": WARNING, "info": INFO, "success": ACCENT}
        notifs = db.get_notifications()[:4]
        for n in notifs:
            c = _col.get(n["type"], INFO)
            af = ctk.CTkFrame(al_card, fg_color=BG_DARK, corner_radius=10,
                              border_width=1, border_color=BORDER)
            af.pack(fill="x", padx=12, pady=4)

            head = ctk.CTkFrame(af, fg_color="transparent")
            head.pack(fill="x", padx=12, pady=(10, 2))
            ctk.CTkLabel(head, text=f"P{n['severity']}", font=FONT_TINY,
                         text_color=c, fg_color=BG_CARD, corner_radius=4,
                         width=32).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(head, text=n["title"], font=FONT_SMALL_BOLD,
                         text_color=c, wraplength=280, justify="left").pack(side="left", anchor="w")

            body = n["body"][:120] + "..." if len(n["body"]) > 120 else n["body"]
            ctk.CTkLabel(af, text=body, font=FONT_SMALL,
                         text_color=TEXT_SEC, wraplength=320, justify="left").pack(
                anchor="w", padx=12, pady=(0, 8))

            if n.get("target_sku"):
                ctk.CTkButton(af, text=f"→ {n['target_sku']}", height=26,
                              fg_color=BG_CARD, hover_color=BG_HOVER,
                              text_color=INFO, font=FONT_SMALL, corner_radius=6,
                              command=lambda nn=n: self.navigator(
                                  "inventory", focus_sku=nn["target_sku"])).pack(
                    anchor="w", padx=12, pady=(0, 10))
            else:
                ctk.CTkFrame(af, height=4, fg_color="transparent").pack()

        ord_card = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
        ord_card.pack(fill="x", padx=22, pady=(0, 22))

        oc_hdr = ctk.CTkFrame(ord_card, fg_color="transparent")
        oc_hdr.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(oc_hdr, text="Son Siparişler (Aktif)",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(side="left")
        ctk.CTkButton(oc_hdr, text=i18n.t("nav.orders") + " →", height=28,
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
                      font=FONT_SMALL, corner_radius=6,
                      command=lambda: self.navigator("orders")).pack(side="right")

        cols = ["Sipariş No", i18n.t("common.platform"), "Ürün",
                i18n.t("common.amount"), i18n.t("common.city"), i18n.t("common.status")]
        col_w = [120, 130, 280, 130, 130, 140]
        _st = {"Bekliyor": WARNING, "Kargoda": INFO,
               "Teslim Edildi": ACCENT, "İade": DANGER}
        rows = []
        for o in db.get_orders("active")[:6]:
            rows.append({"cells": [o["id"], o["platform"], o["product"],
                                     currency.format(o["total"]),
                                     o["city"], o["status"]],
                          "data": o})

        table_wrap = ctk.CTkFrame(ord_card, fg_color="transparent")
        table_wrap.pack(fill="x", padx=14, pady=(0, 14))
        SortableTable(
            table_wrap,
            columns=cols, rows=rows,
            column_widths=col_w,
            status_col=5, status_colors=_st,
            on_row_click=lambda d: self.navigator("orders"),
            export_filename="son_siparisler.csv",
        ).pack(fill="x")
