import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import messagebox
from ui.theme import *
from ui.widgets import Pill, ChartHover
from core import i18n, currency, database as db
from core.mock_data import MARKETPLACES


class MarketplacesPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        sc = self._scroll
        ctk.CTkLabel(sc, text=i18n.t("marketplaces.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(22, 4))
        ctk.CTkLabel(sc, text=i18n.t("marketplaces.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(0, 18))

        from core import credentials
        _platform_keys = {
            "Trendyol":     credentials.PLATFORM_TRENDYOL,
            "Hepsiburada":  credentials.PLATFORM_HEPSIBURADA,
            "Amazon TR/EU": credentials.PLATFORM_AMAZON,
            "N11":          credentials.PLATFORM_N11,
            "Etsy":         credentials.PLATFORM_ETSY,
        }
        active = []
        locked = []
        for m in MARKETPLACES:
            pkey = _platform_keys.get(m["name"])
            m_copy = dict(m)
            m_copy["_platform_key"] = pkey
            m_copy["_configured"] = (
                credentials.is_configured(pkey) if pkey else False)
            if m_copy["_configured"]:
                active.append(m_copy)
            else:
                locked.append(m_copy)

        ctk.CTkLabel(sc,
                     text=i18n.t("marketplaces.active") +
                            (f"  ({len(active)} aktif)" if active else
                             "  (Henüz kurulu platform yok)"),
                     font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(0, 8))

        if not active:
            empty = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=12,
                                  border_width=2, border_color=WARNING)
            empty.pack(fill="x", padx=22, pady=(0, 16))
            ctk.CTkLabel(empty, text="🔒  Aktif Pazar Yeri Yok",
                          font=FONT_HEAD, text_color=WARNING).pack(
                anchor="w", padx=22, pady=(18, 4))
            ctk.CTkLabel(empty,
                          text="Aşağıdaki platform kartlarından birine tıklayıp "
                                "'API Bilgilerini Gir' butonu ile entegrasyonu "
                                "kurabilirsiniz. Bilgiler girildiği an o platform "
                                "kart üst kısmına 'AKTİF' olarak taşınır ve gerçek "
                                "verileriniz çekilmeye başlar.",
                          font=FONT_SMALL, text_color=TEXT_SEC, wraplength=900,
                          justify="left").pack(anchor="w", padx=22, pady=(0, 22))

        act_row = ctk.CTkFrame(sc, fg_color="transparent")
        act_row.pack(fill="x", padx=22, pady=(0, 16))
        for i, m in enumerate(active):
            act_row.grid_columnconfigure(i, weight=1)
            self._active_card(act_row, m, i)

        if len(active) >= 2:
            self._comparison_chart(sc, active)

        ctk.CTkFrame(sc, height=1, fg_color=BORDER).pack(fill="x", padx=22, pady=14)
        ctk.CTkLabel(sc, text="Büyüme Fırsatları", font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(0, 8))

        for i, m in enumerate(locked):
            self._locked_card(sc, m)

        ctk.CTkFrame(sc, height=20, fg_color="transparent").pack()

    def _active_card(self, parent, m, col):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                            border_width=2, border_color=m["color"], cursor="hand2")
        card.grid(row=0, column=col, padx=6, sticky="nsew")

        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkLabel(hdr, text=m["name"], font=FONT_HEAD,
                     text_color=m["color"]).pack(side="left")
        Pill(hdr, "AKTİF", ACCENT, ACCENT_DK).pack(side="right")

        ctk.CTkLabel(card, text=m["desc"], font=FONT_SMALL,
                     text_color=TEXT_SEC).pack(anchor="w", padx=18, pady=(0, 10))
        ctk.CTkFrame(card, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=(0, 10))

        margin_pct = (m["profit"] / m["revenue"] * 100) if m["revenue"] else 0
        ctr  = m.get("click_through", 0) * 100
        conv = m.get("conversion", 0) * 100
        ad_spend = m.get("ad_spend_monthly", 0)
        ad_eff = (m["profit"] / ad_spend) if ad_spend else 0
        metrics = [
            ("Aylık Ciro",       currency.format(m["revenue"]),                TEXT_PRI),
            ("Net Kâr",          currency.format(m["profit"]),                 ACCENT),
            ("Kâr Marjı",        f"%{margin_pct:.1f}",
             ACCENT if margin_pct > 25 else WARNING),
            ("Sipariş Sayısı",   str(m["orders"]),                              TEXT_PRI),
            ("Ortalama Sepet",   currency.format(m.get("avg_basket", 0)),       TEXT_PRI),
            ("Aktif Listeleme",  str(m.get("active_listings", 0)),              INFO),
            ("Buy-Box Payı",     f"%{m.get('buy_box_share', 0)*100:.0f}",
             INFO if m.get('buy_box_share', 0) > 0.5 else WARNING),
            ("Komisyon",         f"%{m['commission']*100:.0f}",                 WARNING),
            ("İade Oranı",       f"%{m['return_rate']*100:.0f}",
             DANGER if m["return_rate"] > 0.05 else ACCENT),
            ("CTR / Dönüşüm",    f"%{ctr:.2f} / %{conv:.2f}",                    TEXT_PRI),
            ("Reklam Bütçesi",   currency.format(ad_spend),                     WARNING),
            ("Reklam Verimi",    f"{ad_eff:.2f}x",
             ACCENT if ad_eff > 5 else (WARNING if ad_eff > 2 else DANGER)),
            ("Organik Pay",      f"%{m.get('organic_share', 0)*100:.0f}",       INFO),
            ("Mağaza Puanı",     f"{m['rating']} ★",                            INFO),
        ]
        for lbl, val, col_c in metrics:
            mf = ctk.CTkFrame(card, fg_color="transparent")
            mf.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(mf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_SEC).pack(side="left")
            ctk.CTkLabel(mf, text=val, font=FONT_BODY_BOLD,
                         text_color=col_c).pack(side="right")

        ctk.CTkButton(card, text=i18n.t("common.detail") + "  →",
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
                      height=34, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=lambda mm=m: self._open_detail(mm)).pack(
            fill="x", padx=14, pady=(12, 16))

        for w in [card, hdr] + list(card.winfo_children()):
            try:
                w.bind("<Button-1>", lambda e, mm=m: self._open_detail(mm), add="+")
            except Exception:
                pass

    def _locked_card(self, parent, m):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                            border_width=1, border_color=BORDER, cursor="hand2")
        card.pack(fill="x", padx=22, pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        top = ctk.CTkFrame(left, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(top, text=m["name"], font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(side="left")
        potential = m.get("potential", "Belirsiz")
        pot_col = {"Yüksek": ACCENT, "Orta": WARNING}.get(potential, TEXT_SEC)
        Pill(top, f"  {potential}  ", pot_col, BG_CARD).pack(side="left", padx=10)
        Pill(top, "KİLİTLİ", TEXT_SEC, BG_CARD).pack(side="left")
        ctk.CTkLabel(left, text=m.get("desc", ""), font=FONT_SMALL,
                     text_color=TEXT_SEC).pack(anchor="w", pady=(6, 6))

        ai_note = m.get("ai_note") or (
            f"API bilgilerinizi girince {m['name']} verileriniz çekilir, "
            "akıl hocası kâr/iade/stok yorumlarını üretmeye başlar.")
        ai = ctk.CTkFrame(left, fg_color=ACCENT_DK, corner_radius=8)
        ai.pack(fill="x", pady=(4, 6))
        ctk.CTkLabel(ai, text="Akıl Hocası: " + ai_note,
                     font=FONT_SMALL, text_color=TEXT_PRI, wraplength=800,
                     justify="left").pack(anchor="w", padx=12, pady=10)

        info = ctk.CTkFrame(left, fg_color="transparent")
        info.pack(fill="x", pady=(4, 0))
        details = [
            ("Açılış Maliyeti", m.get("unlock_fee", "—")),
            ("Listeleme/Komisyon", m.get("listing_fee", "—")),
            ("Tahmini Açılış Süresi", f"{m.get('avg_unlock_days', '—')} gün"),
        ]
        for lbl, val in details:
            r = ctk.CTkFrame(info, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=lbl, font=FONT_TINY,
                         text_color=TEXT_SEC, width=180, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=val, font=FONT_SMALL,
                         text_color=TEXT_PRI).pack(side="left")

        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right", padx=(20, 0))
        if m.get("_platform_key"):
            ctk.CTkButton(right, text="🔑  API Bilgilerini Gir",
                          fg_color=ACCENT, hover_color=ACCENT_H,
                          text_color=BG_DARK,
                          height=40, width=200, font=FONT_SMALL_BOLD,
                          corner_radius=10,
                          command=lambda p=m["_platform_key"]:
                              self._open_creds(p)).pack(pady=(0, 6))
        ctk.CTkButton(right, text=i18n.t("marketplaces.join") + " (Süreç)",
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=ACCENT,
                      height=36, width=200, font=FONT_SMALL_BOLD, corner_radius=10,
                      command=lambda mm=m: self._open_detail(mm)).pack(pady=(0, 6))
        ctk.CTkButton(right, text=i18n.t("common.detail"),
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
                      height=36, width=200, font=FONT_SMALL_BOLD, corner_radius=10,
                      command=lambda mm=m: self._open_detail(mm)).pack()

        for w in [card, inner, left, top]:
            try:
                w.bind("<Button-1>", lambda e, mm=m: self._open_detail(mm), add="+")
            except Exception:
                pass

    def _comparison_chart(self, parent, active):
        ch_card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
        ch_card.pack(fill="x", padx=22, pady=(0, 16))
        ctk.CTkLabel(ch_card, text="Platform Karşılaştırması",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 6))

        fig, axes = plt.subplots(1, 3, figsize=(11, 3.0), facecolor=BG_PANEL)
        scale = (1 / currency.rate_usd_try()) if currency.get() == "USD" else 1
        metrics_cfg = [
            ("Ciro", [m["revenue"] * scale for m in active]),
            ("Net Kâr", [m["profit"] * scale for m in active]),
            ("Sipariş", [m["orders"] for m in active]),
        ]
        names = [m["name"] for m in active]
        colors = [m["color"] for m in active]

        for ax, (title, vals) in zip(axes, metrics_cfg):
            ax.set_facecolor(BG_PANEL)
            bars = ax.bar(names, vals, color=colors, alpha=0.9, width=0.5)
            ax.set_title(title, color=TEXT_PRI, fontsize=10, pad=4)
            ax.tick_params(colors=TEXT_SEC, labelsize=9)
            ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
            for sp in ax.spines.values():
                sp.set_color(BORDER)
            for bar, val in zip(bars, vals):
                ax.text(bar.get_x() + bar.get_width()/2,
                         bar.get_height(),
                         f"{val:,.0f}", ha="center", va="bottom",
                         color=TEXT_PRI, fontsize=9)
        fig.tight_layout(pad=1.2)
        cv = FigureCanvasTkAgg(fig, ch_card)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=14, pady=(0, 14))
        for ax, (title, vals) in zip(axes, metrics_cfg):
            unit = ("TL" if title in ("Ciro", "Net Kâr") and currency.get() == "TRY"
                    else ("USD" if title in ("Ciro", "Net Kâr") else "adet"))
            ChartHover(cv, ax,
                        fmt=lambda lbl, y, t=title, u=unit: f"{t}: {y:,.0f} {u}",
                        x_labels=names)
        plt.close(fig)

    def _open_creds(self, platform_key: str):
        from ui.credentials_dialog import PlatformCredentialsDialog
        def _saved(p):
            for w in self._scroll.winfo_children():
                w.destroy()
            self._build()
        PlatformCredentialsDialog(self, platform_key, on_saved=_saved)

    def _open_detail(self, m):
        MarketplaceDetailWindow(self, m)


class MarketplaceDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, marketplace):
        super().__init__(parent)
        self.m = marketplace
        self.title(f"{marketplace['name']} — Detay")
        self.geometry("840x800")
        self.minsize(720, 640)
        self.configure(fg_color=BG_DARK)
        self.grab_set()
        self._build()

    def _build(self):
        sf = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                     scrollbar_button_color=BORDER)
        sf.pack(fill="both", expand=True)
        m = self.m

        head = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                            border_width=2, border_color=m["color"])
        head.pack(fill="x", padx=18, pady=18)
        top = ctk.CTkFrame(head, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 8))
        ctk.CTkLabel(top, text=m["name"], font=FONT_H1,
                     text_color=TEXT_PRI).pack(side="left")
        Pill(top, "AKTİF" if m["active"] else "KİLİTLİ",
             ACCENT if m["active"] else TEXT_SEC,
             ACCENT_DK if m["active"] else BG_CARD).pack(side="right")
        ctk.CTkLabel(head, text=m["desc"], font=FONT_BODY,
                     text_color=TEXT_SEC).pack(anchor="w", padx=18, pady=(0, 16))

        if m["active"]:
            self._build_active_kpis(sf, m)
            self._build_active_charts(sf, m)

        if not m["active"]:
            ai = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                              border_width=1, border_color=ACCENT)
            ai.pack(fill="x", padx=18, pady=(0, 12))
            ctk.CTkLabel(ai, text=i18n.t("marketplaces.ai_eval"),
                         font=FONT_HEAD, text_color=ACCENT).pack(anchor="w", padx=18, pady=(16, 4))
            ctk.CTkLabel(ai, text=m.get("ai_note", ""), font=FONT_SMALL,
                         text_color=TEXT_PRI, wraplength=760,
                         justify="left").pack(anchor="w", padx=18, pady=(0, 12))

            lift_r = m.get("expected_revenue_lift", 0) * 100
            lift_p = m.get("expected_profit_lift", 0) * 100
            li = ctk.CTkFrame(ai, fg_color="transparent")
            li.pack(fill="x", padx=18, pady=(0, 16))
            ctk.CTkLabel(li, text=i18n.t("marketplaces.expected_lift") + ":",
                         font=FONT_SMALL_BOLD, text_color=TEXT_PRI).pack(side="left", padx=(0, 12))
            Pill(li, f"  Ciro +%{lift_r:.0f}  ", ACCENT,
                 ACCENT_DK).pack(side="left", padx=(0, 8))
            Pill(li, f"  Kar +%{lift_p:.0f}  ", INFO,
                 BG_CARD).pack(side="left")

            from core import ai_engine, currency
            current_monthly_rev = sum(o.get("total", 0) for o in db.get_orders()
                                       if o.get("status") != "İade")
            feas_input = dict(m)
            feas_input["expected_rev_lift"] = m.get("expected_revenue_lift", 0)
            feas_input["expected_profit_lift"] = m.get("expected_profit_lift", 0)
            fz = ai_engine.marketplace_feasibility(feas_input, current_monthly_rev)
            verdict_col = {"ÖNERİLİR": ACCENT, "ARAŞTIR": WARNING,
                            "RİSKLİ": DANGER}[fz["verdict"]]

            fcard = ctk.CTkFrame(ai, fg_color=BG_DARK, corner_radius=10,
                                  border_width=2, border_color=verdict_col)
            fcard.pack(fill="x", padx=18, pady=(0, 16))
            ctk.CTkLabel(fcard, text="AI Fizibilite Skoru",
                          font=FONT_SMALL_BOLD, text_color=TEXT_MUT).pack(
                anchor="w", padx=14, pady=(12, 0))
            vrow = ctk.CTkFrame(fcard, fg_color="transparent")
            vrow.pack(fill="x", padx=14, pady=(2, 10))
            ctk.CTkLabel(vrow, text=fz["verdict"],
                          font=FONT_H1, text_color=verdict_col).pack(side="left")
            ctk.CTkLabel(vrow,
                          text=f"  ·  ROI (12 ay): %{min(fz['roi_pct_12mo'],999):.0f}",
                          font=FONT_BODY_BOLD, text_color=TEXT_SEC).pack(side="left", padx=8)

            grid = ctk.CTkFrame(fcard, fg_color="transparent")
            grid.pack(fill="x", padx=14, pady=(0, 12))
            for i in range(4):
                grid.grid_columnconfigure(i, weight=1)
            metrics = [
                ("Ek Aylık Ciro",     currency.format(fz["incremental_revenue"]), ACCENT),
                ("Ek Aylık Kar",      currency.format(fz["incremental_profit"]), ACCENT),
                ("Sabit Aylık Gider", currency.format(fz["fixed_monthly_cost"]), DANGER),
                ("Basabas",           f"{fz['breakeven_months']} ay" if fz["breakeven_months"] is not None else "—",
                                       INFO),
            ]
            for ci, (lbl, val, col) in enumerate(metrics):
                cell = ctk.CTkFrame(grid, fg_color="transparent")
                cell.grid(row=0, column=ci, padx=4, sticky="ew")
                ctk.CTkLabel(cell, text=lbl, font=FONT_TINY,
                              text_color=TEXT_MUT).pack(anchor="w")
                ctk.CTkLabel(cell, text=val, font=FONT_BODY_BOLD,
                              text_color=col).pack(anchor="w")

            self._build_locked_projection(sf, m, current_monthly_rev, fz)

        steps_card = ctk.CTkFrame(sf, fg_color=BG_PANEL, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        steps_card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(steps_card, text=i18n.t("marketplaces.join_timeline"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        ctk.CTkLabel(steps_card,
                     text=f"Toplam ortalama acilis suresi: ~{m.get('avg_unlock_days', 7)} gun",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w", padx=18, pady=(0, 12))

        for i, (step_title, desc) in enumerate(m.get("join_steps", [])):
            sf_row = ctk.CTkFrame(steps_card, fg_color=BG_DARK, corner_radius=10)
            sf_row.pack(fill="x", padx=14, pady=4)
            num_box = ctk.CTkFrame(sf_row, fg_color=ACCENT, corner_radius=18,
                                    width=36, height=36)
            num_box.pack(side="left", padx=(12, 12), pady=12)
            num_box.pack_propagate(False)
            ctk.CTkLabel(num_box, text=str(i+1),
                         font=FONT_BODY_BOLD,
                         text_color=BG_DARK).pack(expand=True)
            tx = ctk.CTkFrame(sf_row, fg_color="transparent")
            tx.pack(side="left", fill="both", expand=True, pady=10)
            ctk.CTkLabel(tx, text=step_title, font=FONT_BODY_BOLD,
                         text_color=TEXT_PRI).pack(anchor="w")
            ctk.CTkLabel(tx, text=desc, font=FONT_SMALL,
                         text_color=TEXT_SEC, wraplength=620,
                         justify="left").pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(steps_card, height=10, fg_color="transparent").pack()

        if not m["active"]:
            btns = ctk.CTkFrame(sf, fg_color="transparent")
            btns.pack(fill="x", padx=18, pady=(0, 22))
            ctk.CTkButton(btns, text=f"→ {m['name']} Hesabi Ac (Yonlendir)",
                          fg_color=m["color"], hover_color=m["color"],
                          text_color=TEXT_PRI, height=44,
                          font=FONT_BODY_BOLD, corner_radius=10,
                          command=self._initiate_join).pack(fill="x")

    def _initiate_join(self):
        db.add_notification(7, "info", f"{self.m['name']} Acilis Sureci Baslatildi",
                             f"Tahmini acilis suresi: {self.m.get('avg_unlock_days', 7)} gun. "
                             f"Adımları Akıl Hocası takip ediyor.",
                             action="Takip Et")
        messagebox.showinfo("Tamam",
                             f"{self.m['name']} açılış süreci başlatıldı.\n"
                             f"Ortalama {self.m.get('avg_unlock_days', 7)} gün içinde aktif olacak.\n"
                             "Bildirim sisteminden takip edebilirsiniz.",
                             parent=self)
        self.destroy()

    # ----- Locked marketplace projection chart -----
    def _build_locked_projection(self, parent, m, cur_rev, fz):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(card, text="Açılış Senaryosu — 12 Aylık Projeksiyon",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card,
                      text="Mevcut hacme göre kümülatif Ek Kâr ve Geri Ödeme",
                      font=FONT_TINY, text_color=TEXT_SEC).pack(
            anchor="w", padx=18, pady=(0, 12))

        ramp = [0.10, 0.25, 0.45, 0.65, 0.80, 0.90, 0.95, 1.00,
                1.00, 1.00, 1.00, 1.00]
        months = ["+1", "+2", "+3", "+4", "+5", "+6",
                  "+7", "+8", "+9", "+10", "+11", "+12"]
        fixed = fz["fixed_monthly_cost"]
        cum_profit = []
        cum_cost = []
        running = 0
        running_cost = 0
        for r in ramp:
            running += fz["incremental_profit"] * r
            running_cost += fixed
            cum_profit.append(running)
            cum_cost.append(running_cost)
        net = [p - c for p, c in zip(cum_profit, cum_cost)]

        fig, ax = plt.subplots(figsize=(8.4, 3.2), facecolor=BG_PANEL)
        ax.set_facecolor(BG_PANEL)
        ax.plot(months, cum_profit, color=ACCENT, marker="o",
                 linewidth=2.3, label="Kümülatif Ek Kâr")
        ax.plot(months, cum_cost, color=DANGER, marker="o",
                 linewidth=2.0, linestyle="--", label="Kümülatif Sabit Gider")
        ax.plot(months, net, color=INFO, marker="o",
                 linewidth=2.3, label="Net Etki")
        ax.axhline(0, color=TEXT_MUT, linewidth=0.7, linestyle=":")
        ax.fill_between(range(len(months)), net, color=INFO, alpha=0.10)
        ax.set_title(f"{m['name']} — 12 Aylık Net Etki", color=TEXT_PRI,
                      fontsize=10, pad=6)
        ax.tick_params(colors=TEXT_SEC, labelsize=9)
        ax.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax.spines.values():
            sp.set_color(BORDER)
        ax.legend(facecolor=BG_CARD, labelcolor=TEXT_PRI, fontsize=9,
                   framealpha=0.85, edgecolor=BORDER, loc="upper left")
        fig.tight_layout(pad=1.0)
        cv = FigureCanvasTkAgg(fig, card)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=14, pady=(0, 14))
        sym = currency.symbol()
        ChartHover(cv, ax,
                    fmt=lambda lbl, y, s=sym: f"{lbl}: {y:,.0f} {s}",
                    x_labels=months)
        plt.close(fig)

    # ----- Active marketplace rich detail blocks -----
    def _build_active_kpis(self, parent, m):
        margin_pct = (m["profit"] / m["revenue"] * 100) if m["revenue"] else 0
        ctr = m.get("click_through", 0) * 100
        conv = m.get("conversion", 0) * 100
        ad_spend = m.get("ad_spend_monthly", 0)
        ad_eff = (m["profit"] / ad_spend) if ad_spend else 0

        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(card, text="Performans Özeti — 14 Metrik",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card,
                      text="Tüm anahtar göstergeler · Grafik üzerine gelince ayrıntı",
                      font=FONT_TINY, text_color=TEXT_SEC).pack(
            anchor="w", padx=18, pady=(0, 12))

        items = [
            ("Aylık Ciro",       currency.format(m["revenue"]),                   ACCENT),
            ("Net Kâr",          currency.format(m["profit"]),                    ACCENT),
            ("Kâr Marjı",        f"%{margin_pct:.1f}",                             ACCENT if margin_pct > 25 else WARNING),
            ("Sipariş Sayısı",   str(m["orders"]),                                  TEXT_PRI),
            ("Ortalama Sepet",   currency.format(m.get("avg_basket", 0)),          TEXT_PRI),
            ("Aktif Listeleme",  str(m.get("active_listings", 0)),                  INFO),
            ("Buy-Box Payı",     f"%{m.get('buy_box_share', 0)*100:.0f}",
             INFO if m.get('buy_box_share', 0) > 0.5 else WARNING),
            ("Komisyon Oranı",   f"%{m['commission']*100:.0f}",                    WARNING),
            ("İade Oranı",       f"%{m['return_rate']*100:.0f}",
             DANGER if m["return_rate"] > 0.05 else ACCENT),
            ("CTR",              f"%{ctr:.2f}",                                    TEXT_PRI),
            ("Dönüşüm",          f"%{conv:.2f}",                                   TEXT_PRI),
            ("Reklam Bütçesi",   currency.format(ad_spend),                        WARNING),
            ("Reklam Verimi",    f"{ad_eff:.2f}x",
             ACCENT if ad_eff > 5 else (WARNING if ad_eff > 2 else DANGER)),
            ("Mağaza Puanı",     f"{m['rating']} ★",                                INFO),
        ]
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 16))
        cols = 4
        for i in range(cols):
            grid.grid_columnconfigure(i, weight=1, uniform="kpi")
        for i, (lbl, val, col) in enumerate(items):
            r, c = i // cols, i % cols
            cell = ctk.CTkFrame(grid, fg_color=BG_DARK, corner_radius=10,
                                 border_width=1, border_color=BORDER)
            cell.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            ctk.CTkLabel(cell, text=lbl, font=FONT_TINY,
                          text_color=TEXT_MUT).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(cell, text=val, font=FONT_SUB,
                          text_color=col).pack(anchor="w", padx=12, pady=(2, 10))

    def _build_active_charts(self, parent, m):
        from core.mock_data import MONTHS
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkLabel(card, text="Görsel Analizler — Etkileşimli Grafikler",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(card,
                      text="Fareyi grafik üzerine getir, değerleri canlı gör",
                      font=FONT_TINY, text_color=TEXT_SEC).pack(
            anchor="w", padx=18, pady=(0, 12))

        ctr = m.get("click_through", 0) * 100
        conv = m.get("conversion", 0) * 100
        margin_pct = (m["profit"] / m["revenue"] * 100) if m["revenue"] else 0
        ad_spend = m.get("ad_spend_monthly", 0)
        ad_eff = (m["profit"] / ad_spend) if ad_spend else 0

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.2, 3.0), facecolor=BG_PANEL)

        # Sol: Trafik hunisi (CTR → Dönüşüm)
        ax1.set_facecolor(BG_PANEL)
        funnel_labels = ["Görüntülenme", "Tıklama (CTR)", "Sipariş (Dönüşüm)"]
        funnel_values = [100, ctr, ctr * conv / 100]
        bars1 = ax1.barh(funnel_labels, funnel_values,
                          color=[INFO, WARNING, ACCENT], height=0.55)
        ax1.set_xlim(0, 100)
        ax1.set_title("Trafik Hunisi (%)", color=TEXT_PRI, fontsize=10, pad=6)
        ax1.tick_params(colors=TEXT_SEC, labelsize=9)
        ax1.grid(axis="x", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax1.spines.values():
            sp.set_color(BORDER)
        for b, v in zip(bars1, funnel_values):
            ax1.text(v + 1.5, b.get_y() + b.get_height()/2,
                      f"%{v:.2f}", color=TEXT_PRI, va="center", fontsize=9)

        # Sağ: Marj & Verim & Buy-Box
        ax2.set_facecolor(BG_PANEL)
        kpi_labels = ["Kâr Marjı %", "Buy-Box %", "Reklam Verimi"]
        kpi_values = [margin_pct, m.get("buy_box_share", 0) * 100, ad_eff * 5]
        bars2 = ax2.bar(kpi_labels, kpi_values,
                         color=[ACCENT, INFO, WARNING], width=0.55)
        ax2.set_title("Operasyonel Göstergeler", color=TEXT_PRI, fontsize=10, pad=6)
        ax2.tick_params(colors=TEXT_SEC, labelsize=9)
        ax2.grid(axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.5)
        for sp in ax2.spines.values():
            sp.set_color(BORDER)
        for b, v, raw in zip(bars2, kpi_values,
                              [f"%{margin_pct:.1f}",
                               f"%{m.get('buy_box_share', 0)*100:.0f}",
                               f"{ad_eff:.2f}x"]):
            ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 1,
                      raw, color=TEXT_PRI, ha="center", fontsize=9)

        fig.tight_layout(pad=1.0)
        cv = FigureCanvasTkAgg(fig, card)
        cv.draw()
        cv.get_tk_widget().pack(fill="both", padx=14, pady=(0, 14))
        ChartHover(cv, ax1,
                    fmt=lambda lbl, v: f"{lbl}: %{v:.2f}",
                    x_labels=funnel_labels)
        ChartHover(cv, ax2,
                    fmt=lambda lbl, v: f"{lbl}: {v:.2f}",
                    x_labels=kpi_labels)
        plt.close(fig)
