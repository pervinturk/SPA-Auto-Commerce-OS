import customtkinter as ctk
from tkinter import messagebox
from ui.theme import *
from ui.widgets import Pill, Tooltip
from core import i18n, currency, database as db, credentials


class ProfilePage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self._data = self._load_profile_data()
        self._entries = {}
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        self._build()

    def _load_profile_data(self) -> dict:
        data = {
            "company_name": "",   "trade_name":  "",
            "tax_office":   "",   "tax_no":      "",
            "mersis_no":    "",
            "address":      "",   "city":        "",
            "district":     "",   "zip":         "",
            "phone":        "",   "email":       "",
            "website":      "",
            "founder":      "",   "founded":     "",
            "employees":    "",   "sector":      "",
            "iban":         "",   "bank":        "",
        }
        try:
            saved = db.get_setting("profile_json")
            if saved:
                import json
                data.update(json.loads(saved))
        except Exception:
            pass
        try:
            if credentials.is_configured(credentials.PLATFORM_TRENDYOL):
                from core import trendyol_sync as ts
                info = ts.fetch_seller_info()
                if isinstance(info, dict):
                    data.setdefault("company_name", info.get("companyName", ""))
                    if not data["company_name"]:
                        data["company_name"] = info.get("companyName", "")
                    if not data["trade_name"]:
                        data["trade_name"] = info.get("name", "")
                    if not data["tax_no"]:
                        data["tax_no"] = str(info.get("taxNumber", ""))
                    if not data["tax_office"]:
                        data["tax_office"] = info.get("taxOffice", "")
                    if not data["mersis_no"]:
                        data["mersis_no"] = info.get("mersisNumber", "")
                    if not data["phone"]:
                        data["phone"] = info.get("phoneNumber", "")
                    if not data["email"]:
                        data["email"] = info.get("email", "")
        except Exception:
            pass
        return data

    def _build(self):
        sc = self._scroll
        ctk.CTkLabel(sc, text=i18n.t("profile.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(22, 4))
        ctk.CTkLabel(sc, text=i18n.t("profile.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(0, 18))

        self._build_integrations_card(sc)

        avatar_row = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                  border_width=1, border_color=BORDER)
        avatar_row.pack(fill="x", padx=22, pady=(0, 14))
        ar = ctk.CTkFrame(avatar_row, fg_color="transparent")
        ar.pack(fill="x", padx=18, pady=18)
        circle = ctk.CTkFrame(ar, width=72, height=72, corner_radius=36,
                              fg_color=ACCENT)
        circle.pack(side="left")
        circle.pack_propagate(False)
        initials = self._data.get("founder", "A")[:1].upper()
        ctk.CTkLabel(circle, text=initials, font=("Segoe UI", 30, "bold"),
                     text_color=BG_DARK).place(relx=0.5, rely=0.5, anchor="center")
        info_col = ctk.CTkFrame(ar, fg_color="transparent")
        info_col.pack(side="left", padx=18)
        ctk.CTkLabel(info_col, text=self._data.get("company_name", ""),
                     font=FONT_H1, text_color=TEXT_PRI).pack(anchor="w")
        ctk.CTkLabel(info_col, text=self._data.get("trade_name", ""),
                     font=FONT_SMALL_BOLD, text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(info_col, text=f"Kurucu: {self._data.get('founder', '')}  ·  "
                                      f"{self._data.get('founded', '')}",
                     font=FONT_SMALL, text_color=TEXT_SEC).pack(anchor="w")

        settings = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                 border_width=2, border_color=ACCENT)
        settings.pack(fill="x", padx=22, pady=(0, 14))
        ctk.CTkLabel(settings, text=i18n.t("profile.settings"), font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))

        srow = ctk.CTkFrame(settings, fg_color="transparent")
        srow.pack(fill="x", padx=18, pady=(0, 16))

        lf = ctk.CTkFrame(srow, fg_color="transparent")
        lf.pack(side="left", padx=(0, 30))
        ctk.CTkLabel(lf, text=i18n.t("profile.language"), font=FONT_SMALL_BOLD,
                     text_color=TEXT_SEC).pack(anchor="w")
        seg = ctk.CTkSegmentedButton(lf, values=["TR", "EN"],
                                      fg_color=BG_DARK,
                                      selected_color=ACCENT,
                                      selected_hover_color=ACCENT_H,
                                      unselected_color=BG_DARK,
                                      text_color=TEXT_PRI,
                                      font=FONT_BODY_BOLD,
                                      command=lambda v: i18n.set_lang(v.lower()))
        seg.set(i18n.get_lang().upper())
        seg.pack(pady=(6, 0))

        cf = ctk.CTkFrame(srow, fg_color="transparent")
        cf.pack(side="left")
        ctk.CTkLabel(cf, text=i18n.t("profile.currency"), font=FONT_SMALL_BOLD,
                     text_color=TEXT_SEC).pack(anchor="w")
        cseg = ctk.CTkSegmentedButton(cf, values=["TRY", "USD"],
                                       fg_color=BG_DARK,
                                       selected_color=ACCENT,
                                       selected_hover_color=ACCENT_H,
                                       unselected_color=BG_DARK,
                                       text_color=TEXT_PRI,
                                       font=FONT_BODY_BOLD,
                                       command=lambda v: currency.set(v))
        cseg.set(currency.get())
        cseg.pack(pady=(6, 0))

        rf = ctk.CTkFrame(srow, fg_color="transparent")
        rf.pack(side="right")
        ctk.CTkLabel(rf, text="Güncel Kur", font=FONT_SMALL_BOLD,
                     text_color=TEXT_SEC).pack(anchor="e")
        ctk.CTkLabel(rf, text=f"1 USD = {currency.rate_usd_try():.2f} TL",
                     font=FONT_BODY_BOLD, text_color=INFO).pack(anchor="e", pady=(6, 0))

        sections = [
            ("Şirket Bilgileri", [
                ("Şirket Adı",    "company_name"),
                ("Ticari Unvan",  "trade_name"),
                ("Sektör",        "sector"),
                ("Kurucu",        "founder"),
                ("Kuruluş Yili",  "founded"),
                ("Çalışan Sayisi", "employees"),
            ]),
            ("Vergi & Yasal", [
                ("Vergi Dairesi", "tax_office"),
                ("Vergi No",      "tax_no"),
                ("MERSİS No",     "mersis_no"),
            ]),
            ("Adres & İletişim", [
                ("Adres",         "address"),
                ("Şehir",         "city"),
                ("Ilce",          "district"),
                ("Posta Kodu",    "zip"),
                ("Telefon",       "phone"),
                ("E-posta",       "email"),
                ("Web Sitesi",    "website"),
            ]),
            ("Banka Bilgileri", [
                ("Banka",         "bank"),
                ("IBAN",          "iban"),
            ]),
        ]

        two_col = ctk.CTkFrame(sc, fg_color="transparent")
        two_col.pack(fill="x", padx=22, pady=(0, 14))
        two_col.grid_columnconfigure(0, weight=1)
        two_col.grid_columnconfigure(1, weight=1)

        for si, (title, fields) in enumerate(sections):
            col_idx = si % 2
            row_idx = si // 2
            card = ctk.CTkFrame(two_col, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
            card.grid(row=row_idx, column=col_idx, padx=6, pady=6, sticky="nsew")
            ctk.CTkLabel(card, text=title, font=FONT_HEAD,
                         text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
            ctk.CTkFrame(card, height=1, fg_color=BORDER).pack(fill="x", padx=14, pady=(0, 8))
            for lbl, key in fields:
                ff = ctk.CTkFrame(card, fg_color="transparent")
                ff.pack(fill="x", padx=18, pady=4)
                ctk.CTkLabel(ff, text=lbl, font=FONT_SMALL_BOLD,
                             text_color=TEXT_SEC, width=130, anchor="w").pack(side="left")
                e = ctk.CTkEntry(ff, fg_color=BG_DARK, border_color=BORDER,
                                 text_color=TEXT_PRI, height=34, font=FONT_SMALL)
                e.insert(0, self._data.get(key, ""))
                e.pack(side="left", fill="x", expand=True)
                self._entries[key] = e
            ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

        notif_card = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                   border_width=1, border_color=BORDER)
        notif_card.pack(fill="x", padx=22, pady=(0, 14))
        ctk.CTkLabel(notif_card, text=i18n.t("profile.notifications"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=18, pady=(16, 8))
        notifs = [
            ("Kritik stok uyarılari", True),
            ("Yeni sipariş bildirimleri", True),
            ("Hakediş odemeleri", True),
            ("AI agent onerisi bildirimleri", True),
            ("Haftalik performans raporu", False),
        ]
        for lbl, default in notifs:
            nf = ctk.CTkFrame(notif_card, fg_color="transparent")
            nf.pack(fill="x", padx=18, pady=4)
            ctk.CTkLabel(nf, text=lbl, font=FONT_SMALL,
                         text_color=TEXT_PRI).pack(side="left")
            sw = ctk.CTkSwitch(nf, text="", fg_color=BORDER, progress_color=ACCENT,
                                button_color=TEXT_PRI, onvalue=True, offvalue=False)
            if default:
                sw.select()
            sw.pack(side="right")
        ctk.CTkFrame(notif_card, height=12, fg_color="transparent").pack()

        save_row = ctk.CTkFrame(sc, fg_color="transparent")
        save_row.pack(fill="x", padx=22, pady=(0, 28))
        ctk.CTkButton(save_row, text=i18n.t("common.save"), height=46,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color=TEXT_PRI, font=FONT_BODY_BOLD, corner_radius=10,
                      command=self._save).pack(side="right")
        self._status = ctk.CTkLabel(save_row, text="", font=FONT_SMALL,
                                     text_color=ACCENT)
        self._status.pack(side="right", padx=12)

    def _save(self):
        for key, entry in self._entries.items():
            self._data[key] = entry.get()
        import json
        try:
            db.set_setting("profile_json", json.dumps(self._data, ensure_ascii=False))
        except Exception:
            for k, v in self._data.items():
                db.set_setting(f"profile.{k}", v)
        self._status.configure(text=i18n.t("profile.saved"))
        self.after(3000, lambda: self._status.configure(text=""))

    def _build_integrations_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=2, border_color=ACCENT)
        card.pack(fill="x", padx=22, pady=(0, 14))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 4))
        title_lbl = ctk.CTkLabel(head, text="🔌  Pazar Yeri Entegrasyonu",
                                    font=FONT_HEAD, text_color=TEXT_PRI)
        title_lbl.pack(side="left")
        try:
            Tooltip(title_lbl,
                     "API bilgilerinizi girince tüm sayaçlar (ciro, kâr, "
                     "stok, sipariş) gerçek satıcı panelinizden gelir.")
        except Exception:
            pass

        configured_count = len(credentials.list_configured())
        Pill(head, f"  {configured_count} AKTİF  ",
              ACCENT if configured_count else WARNING,
              ACCENT_DK if configured_count else BG_CARD
              ).pack(side="right")

        ctk.CTkLabel(card,
                      text="Pazar yeri API bilgilerinizi (Satıcı ID + API Key + "
                            "Secret) girince stok, sipariş, hakediş, kâr, iade "
                            "verileri gerçek panelinizden çekilir. Bilgiler "
                            "şifreli olarak yalnızca bilgisayarınızda saklanır.",
                      font=FONT_SMALL, text_color=TEXT_SEC,
                      wraplength=900, justify="left").pack(
            anchor="w", padx=18, pady=(0, 12))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 16))
        for i in range(2):
            grid.grid_columnconfigure(i, weight=1, uniform="plat")

        for i, platform in enumerate(credentials.PLATFORM_FIELDS.keys()):
            r, c = i // 2, i % 2
            self._platform_tile(grid, platform, r, c)

    def _platform_tile(self, parent, platform: str, r: int, c: int):
        label = credentials.PLATFORM_LABELS.get(platform, platform)
        configured = credentials.is_configured(platform)
        status = credentials.get_status(platform)

        tile = ctk.CTkFrame(parent, fg_color=BG_DARK, corner_radius=12,
                             border_width=2,
                             border_color=ACCENT if configured else BORDER)
        tile.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")

        head = ctk.CTkFrame(tile, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(head, text=label, font=FONT_SUB,
                      text_color=TEXT_PRI).pack(side="left")
        Pill(head, "  AKTİF  " if configured else "  KAPALI  ",
              ACCENT if configured else TEXT_MUT,
              ACCENT_DK if configured else BG_CARD
              ).pack(side="right")

        if configured and status.get("last_verified"):
            ctk.CTkLabel(tile,
                          text=f"✓ Doğrulanmış · {status['last_verified'][:16]}",
                          font=FONT_TINY, text_color=ACCENT).pack(
                anchor="w", padx=14, pady=(0, 2))
        elif configured and status.get("last_error"):
            ctk.CTkLabel(tile,
                          text=f"⚠ {status['last_error'][:60]}",
                          font=FONT_TINY, text_color=WARNING,
                          wraplength=300).pack(anchor="w", padx=14, pady=(0, 2))
        elif not configured:
            ctk.CTkLabel(tile, text="API bilgileri girilmedi",
                          font=FONT_TINY, text_color=TEXT_MUT).pack(
                anchor="w", padx=14, pady=(0, 2))

        btn = ctk.CTkButton(
            tile,
            text="⚙  Bilgileri Düzenle" if configured else "+  API Bilgileri Gir",
            height=36, font=FONT_SMALL_BOLD, corner_radius=8,
            fg_color=ACCENT if not configured else BG_CARD,
            hover_color=ACCENT_H if not configured else BG_HOVER,
            text_color=BG_DARK if not configured else INFO,
            command=lambda p=platform: self._open_creds_dialog(p))
        btn.pack(fill="x", padx=14, pady=(8, 14))

    def _open_creds_dialog(self, platform: str):
        from ui.credentials_dialog import PlatformCredentialsDialog
        def _on_saved(p):
            self._data = self._load_profile_data()
            for w in self._scroll.winfo_children():
                w.destroy()
            self._entries.clear()
            self._build()
        PlatformCredentialsDialog(self, platform, on_saved=_on_saved)
