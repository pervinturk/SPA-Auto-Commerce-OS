import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from ui.theme import *
from ui.widgets import ChartHover
from core import i18n, currency, database as db
from core.mock_data import (MONTHS, REVENUE, EXPENSES, PROFIT,
                             EXPENSE_BREAKDOWN, UPCOMING_PAYOUTS)


class FinancePage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self._period = "Aylık"
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        sc = self._scroll
        hdr = ctk.CTkFrame(sc, fg_color="transparent")
        hdr.pack(fill="x", padx=28, pady=(22, 4))
        ctk.CTkLabel(hdr, text=i18n.t("finance.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(side="left")

        period_f = ctk.CTkFrame(hdr, fg_color=BG_PANEL, corner_radius=10,
                                border_width=1, border_color=BORDER)
        period_f.pack(side="right")
        self._period_btns = {}
        for p in ["Günlük", "Aylık", "Yıllık"]:
            btn = ctk.CTkButton(period_f, text=p, width=80, height=34,
                                font=FONT_SMALL_BOLD, corner_radius=8,
                                fg_color=ACCENT if p == self._period else "transparent",
                                text_color=TEXT_PRI if p == self._period else TEXT_SEC,
                                hover_color=ACCENT_H,
                                command=lambda x=p: self._set_period(x))
            btn.pack(side="left", padx=4, pady=4)
            self._period_btns[p] = btn

        ctk.CTkLabel(sc, text=i18n.t("finance.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(2, 16))

        self._kpi_frame = ctk.CTkFrame(sc, fg_color="transparent")
        self._kpi_frame.pack(fill="x", padx=22, pady=(0, 14))
        self._chart_frame = ctk.CTkFrame(sc, fg_color="transparent")
        self._chart_frame.pack(fill="x", padx=22, pady=(0, 14))
        self._lower_frame = ctk.CTkFrame(sc, fg_color="transparent")
        self._lower_frame.pack(fill="x", padx=22, pady=(0, 22))

        self._render()

    def _set_period(self, p):
        self._period = p
        for k, btn in self._period_btns.items():
            btn.configure(fg_color=ACCENT if k == p else "transparent",
                          text_color=TEXT_PRI if k == p else TEXT_SEC)
        self._render()

    def _render(self):
        for f in [self._kpi_frame, self._chart_frame, self._lower_frame]:
            for w in f.winfo_children():
                w.destroy()

        if self._period == "Günlük":
            rev, exp, prof = 4750.0, 1830.0, 2920.0
            label = "Bugün"
        elif self._period == "Aylık":
            rev, exp, prof = REVENUE[-1], EXPENSES[-1], PROFIT[-1]
            label = "Mayis"
        else:
            rev = sum(REVENUE)
            exp = sum(EXPENSES)
            prof = sum(PROFIT)
            label = "2026 Yıllık"

        ctk.CTkLabel(self._kpi_frame, text=label, font=FONT_SMALL,
                     text_color=TEXT_SEC).grid(row=0, column=0, columnspan=4,
                                               padx=6, pady=(0, 6), sticky="w")
        kpis = [
            ("Toplam Gelir", currency.format(rev), ACCENT),
            ("Toplam Gider", currency.format(exp), DANGER),
            ("Net Kâr", currency.format(prof), ACCENT),
            ("Kâr Marjı", f"%{prof/rev*100:.1f}" if rev else "%0", INFO),
        ]
        for i, (lbl, val, col) in enumerate(kpis):
            self._kpi_frame.grid_columnconfigure(i, weight=1)
            c = ctk.CTkFrame(self._kpi_frame, fg_color=BG_PANEL, corner_radius=12,
                             border_width=1, border_color=BORDER)
            c.grid(row=1, column=i, padx=6, sticky="ew")
            ctk.CTkLabel(c, text=lbl, font=FONT_SMALL_BOLD,
                         text_color=TEXT_SEC).pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(c, text=val, font=FONT_KPI,
                         text_color=col).pack(anchor="w", padx=16, pady=(0, 14))

        self._chart_frame.grid_columnconfigure(0, weight=6)
        self._chart_frame.grid_columnconfigure(1, weight=4)

        ch = ctk.CTkFrame(self._chart_frame, fg_color=BG_PANEL, corner_radius=14,
                          border_width=1, border_color=BORDER)
        ch.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(ch, text="Aylık Gelir / Gider / Kar",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(ch, text=f"Birim: 1.000 {currency.symbol()}",
                     font=FONT_TINY, text_color=TEXT_SEC).pack(anchor="w", padx=18)

        scale = (1 / (currency.rate_usd_try() * 1000)) if currency.get() == "USD" else 1/1000
        fig, ax = plt.subplots(figsize=(7.2, 3.2), facecolor=BG_PANEL)
        ax.set_facecolor(BG_PANEL)
        ax.plot(MONTHS, [r*scale for r in REVENUE], color=ACCENT, marker="o",
                markersize=5, linewidth=2.2, label="Gelir")
        ax.plot(MONTHS, [e*scale for e in EXPENSES], color=DANGER, marker="o",
                markersize=5, linewidth=2.2, label="Gider")
        ax.fill_between(range(len(MONTHS)), [p*scale for p in PROFIT],
                        color=INFO, alpha=0.18, label="Kar")
        ax.set_xticks(range(len(MONTHS)))
        ax.set_xticklabels(MONTHS, color=TEXT_SEC, fontsize=9)
        ax.tick_params(colors=TEXT_SEC, labelsize=9)
        ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        ax.legend(facecolor=BG_CARD, labelcolor=TEXT_PRI, fontsize=9,
                  framealpha=0.85, edgecolor=BORDER)
        fig.tight_layout(pad=1.2)
        cv = FigureCanvasTkAgg(fig, ch)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=12, pady=(4, 14))
        sym = currency.symbol()
        ChartHover(cv, ax,
                    fmt=lambda lbl, y, s=sym: f"{lbl}  ·  {y*1000:,.0f} {s}",
                    x_labels=MONTHS)
        plt.close(fig)

        pie_card = ctk.CTkFrame(self._chart_frame, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
        pie_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        ctk.CTkLabel(pie_card, text="Gider Dağılımı",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 4))

        labels = list(EXPENSE_BREAKDOWN.keys())
        values = list(EXPENSE_BREAKDOWN.values())
        colors_p = [ACCENT, INFO, WARNING, DANGER, "#A78BFA", "#34D399", TEXT_SEC]

        fig2, ax2 = plt.subplots(figsize=(3.6, 2.8), facecolor=BG_PANEL)
        ax2.set_facecolor(BG_PANEL)
        wedges, _, autotexts = ax2.pie(
            values, labels=None, colors=colors_p[:len(values)],
            autopct="%1.0f%%", startangle=140,
            textprops={"color": TEXT_PRI, "fontsize": 9},
            wedgeprops={"linewidth": 1.5, "edgecolor": BG_PANEL}
        )
        for at in autotexts:
            at.set_color(TEXT_PRI)
            at.set_fontsize(8)
        fig2.tight_layout(pad=0.6)
        cv2 = FigureCanvasTkAgg(fig2, pie_card)
        cv2.draw()
        cv2.get_tk_widget().pack(fill="both", padx=10, pady=(0, 6))
        sym = currency.symbol()
        total = sum(values) or 1
        pie_data = [(l, v) for l, v in zip(labels, values)]
        ChartHover(cv2, ax2,
                    fmt=lambda lbl, v, s=sym, t=total: f"{lbl}: {v:,.0f} {s}  ·  %{v/t*100:.1f}",
                    pie_data=pie_data)
        plt.close(fig2)

        for i, (lbl, val) in enumerate(zip(labels, values)):
            lf = ctk.CTkFrame(pie_card, fg_color="transparent")
            lf.pack(fill="x", padx=18, pady=2)
            ctk.CTkFrame(lf, width=12, height=12, fg_color=colors_p[i % len(colors_p)],
                         corner_radius=2).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(lf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC).pack(side="left")
            ctk.CTkLabel(lf, text=currency.format(val), font=FONT_SMALL_BOLD,
                         text_color=TEXT_PRI).pack(side="right")
        ctk.CTkFrame(pie_card, height=12, fg_color="transparent").pack()

        self._lower_frame.grid_columnconfigure(0, weight=6)
        self._lower_frame.grid_columnconfigure(1, weight=4)

        tx_card = ctk.CTkFrame(self._lower_frame, fg_color=BG_PANEL, corner_radius=14,
                               border_width=1, border_color=BORDER)
        tx_card.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        ctk.CTkLabel(tx_card, text=i18n.t("finance.transactions"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        for tx in db.get_transactions()[:15]:
            tf = ctk.CTkFrame(tx_card, fg_color="transparent")
            tf.pack(fill="x", padx=14, pady=3)
            col = ACCENT if tx["type"] == "Gelir" else DANGER
            sign = "+" if tx["type"] == "Gelir" else ""
            ctk.CTkLabel(tf, text=tx["date"], font=FONT_SMALL,
                         text_color=TEXT_SEC, width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(tf, text=tx["desc"], font=FONT_SMALL,
                         text_color=TEXT_PRI).pack(side="left", padx=8)
            ctk.CTkLabel(tf, text=f"{sign}{currency.format(tx['amount'])}",
                         font=FONT_SMALL_BOLD, text_color=col).pack(side="right")
            ctk.CTkFrame(tx_card, height=1, fg_color=BORDER).pack(fill="x", padx=14)
        ctk.CTkFrame(tx_card, height=10, fg_color="transparent").pack()

        po_card = ctk.CTkFrame(self._lower_frame, fg_color=BG_PANEL, corner_radius=14,
                               border_width=1, border_color=BORDER)
        po_card.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        ctk.CTkLabel(po_card, text=i18n.t("finance.upcoming_payouts"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        total_payout = sum(p["amount"] for p in UPCOMING_PAYOUTS)
        ctk.CTkLabel(po_card, text=currency.format(total_payout),
                     font=FONT_TITLE, text_color=ACCENT).pack(anchor="w", padx=18, pady=(0, 12))
        for po in UPCOMING_PAYOUTS:
            pf = ctk.CTkFrame(po_card, fg_color=BG_DARK, corner_radius=10)
            pf.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(pf, text=po["platform"], font=FONT_BODY_BOLD,
                         text_color=po["color"]).pack(anchor="w", padx=14, pady=(12, 2))
            ctk.CTkLabel(pf, text=currency.format(po["amount"]),
                         font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=14)
            ctk.CTkLabel(pf, text=f"Beklenen: {po['date']}",
                         font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w", padx=14, pady=(0, 12))

        ins_card = ctk.CTkFrame(self._lower_frame, fg_color=BG_PANEL, corner_radius=14,
                                 border_width=1, border_color=BORDER)
        ins_card.grid(row=1, column=0, columnspan=2, padx=0, pady=(14, 0), sticky="ew")
        ctk.CTkLabel(ins_card, text=i18n.t("finance.profit_loss"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        top_exp = sorted(EXPENSE_BREAKDOWN.items(), key=lambda x: x[1], reverse=True)
        insights = [
            (DANGER, f"En buyuk gider: '{top_exp[0][0]}' → {currency.format(top_exp[0][1])}. "
                      f"Bu kalemi %10 azaltirsaniz aylik {currency.format(top_exp[0][1]*0.10)} kar artisi."),
            (WARNING, f"Ikinci buyuk gider: '{top_exp[1][0]}' → {currency.format(top_exp[1][1])}. "
                      f"Kargo konsolidasyonu ile %15-20 tasarruf mumkun."),
            (ACCENT, f"Bu ayin kar marji: %{PROFIT[-1]/REVENUE[-1]*100:.1f}. "
                     "Sektör ortalamasi %22, portfoy üstunde performans."),
            (INFO, "TS-001 ve AK-088 en yüksek marjli ürünler. Reklam butcesini bu urunlere "
                   "kaydirmak aylık tahmini +4.500 TL kar sağlar."),
        ]
        for col, text in insights:
            inf = ctk.CTkFrame(ins_card, fg_color=BG_DARK, corner_radius=10)
            inf.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(inf, text=text, font=FONT_SMALL,
                         text_color=col, wraplength=1100,
                         justify="left").pack(anchor="w", padx=14, pady=10)
        ctk.CTkFrame(ins_card, height=12, fg_color="transparent").pack()
