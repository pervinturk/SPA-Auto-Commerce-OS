import customtkinter as ctk
from ui.theme import *
from ui.widgets import Pill
from core import database as db
from core import i18n, ai_engine


class AdvisorPage(ctk.CTkFrame):
    def __init__(self, parent, navigator=None):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=0)
        self.navigator = navigator
        self._history = []
        self._pending = None
        self._build()

    def _goto_profile(self):
        if self.navigator:
            try: self.navigator("profile")
            except Exception: pass

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                              scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)
        sc = self._scroll

        ctk.CTkLabel(sc, text=i18n.t("advisor.title"), font=FONT_TITLE,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(22, 4))
        ctk.CTkLabel(sc, text=i18n.t("advisor.subtitle"),
                     font=FONT_BODY, text_color=TEXT_SEC).pack(anchor="w", padx=28, pady=(0, 18))

        from core import credentials
        is_live = credentials.is_configured(credentials.PLATFORM_TRENDYOL)
        if not is_live:
            from ui.lock_screen import IntegrationLockCard
            lock = IntegrationLockCard(
                sc, page_name="Akıl Hocası",
                on_configure=lambda: self._goto_profile())
            lock.pack(fill="x", padx=22, pady=(0, 16))
            info = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=12,
                                  border_width=1, border_color=INFO)
            info.pack(fill="x", padx=22, pady=(0, 16))
            ctk.CTkLabel(info, text="🧠  Akıl Hocası ne yapar?",
                          font=FONT_HEAD, text_color=INFO).pack(
                anchor="w", padx=18, pady=(14, 4))
            ctk.CTkLabel(info, text=(
                "Trendyol panelinizden gelen verileri okur, sorularınızı "
                "(stok durumu, iade riski, kâr analizi, kargo "
                "optimizasyonu) cevaplar; onayınızla fiyat/stok/açıklama "
                "değişikliği yapar. API bilgilerinizi girince aktifleşir."),
                font=FONT_SMALL, text_color=TEXT_SEC, wraplength=900,
                justify="left").pack(anchor="w", padx=18, pady=(0, 14))
            return

        ctk.CTkLabel(sc, text=i18n.t("advisor.proactive"), font=FONT_HEAD,
                     text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(0, 8))

        _col = {"danger": DANGER, "warning": WARNING, "info": INFO, "success": ACCENT}
        for n in db.get_notifications():
            c = _col.get(n["type"], INFO)
            card = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", padx=22, pady=5)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=18, pady=(14, 4))
            Pill(top, f"  P{n['severity']}  ", c, BG_CARD).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(top, text=n["title"], font=FONT_BODY_BOLD,
                         text_color=c).pack(side="left")
            if n.get("action"):
                ctk.CTkButton(top, text=n["action"], width=140, height=30,
                              fg_color=BG_CARD, hover_color=BG_HOVER,
                              text_color=c, font=FONT_SMALL_BOLD, corner_radius=6,
                              command=lambda nn=n: self._handle_action(nn)
                              ).pack(side="right")
            ctk.CTkLabel(card, text=n["body"], font=FONT_SMALL,
                         text_color=TEXT_PRI, wraplength=1100,
                         justify="left").pack(anchor="w", padx=18, pady=(0, 14))

        ctk.CTkFrame(sc, height=1, fg_color=BORDER).pack(fill="x", padx=22, pady=14)

        ctk.CTkLabel(sc, text=i18n.t("advisor.chat") + " — Otonom Agent",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=28, pady=(0, 4))
        ctk.CTkLabel(sc, text=("Ornek: 'Mavi tişört rengini siyah yap', "
                                "'TS-001 fiyatini 280 TL yap', "
                                "'SN-014 için yeniden sipariş ver', "
                                "'%15 indirim kampanyasi oluştur'"),
                     font=FONT_SMALL, text_color=TEXT_SEC,
                     wraplength=1100).pack(anchor="w", padx=28, pady=(0, 12))

        quick = ctk.CTkFrame(sc, fg_color="transparent")
        quick.pack(fill="x", padx=22, pady=(0, 10))
        prompts = [
            "Stok durumum nasil?",
            "İade oranlarini analiz et",
            "Fiyat stratejisi önerileri",
            "Kargo optimizasyonu",
            "Amazon'a girmeli miyim?",
            "Bayram kampanyasi onerisi",
        ]
        for i, q in enumerate(prompts):
            quick.grid_columnconfigure(i, weight=1)
            ctk.CTkButton(quick, text=q, height=34, font=FONT_SMALL,
                          fg_color=BG_CARD, hover_color=BG_HOVER,
                          text_color=INFO, corner_radius=8,
                          command=lambda x=q: self._ask(x)
                          ).grid(row=0, column=i, padx=4, sticky="ew")

        chat_card = ctk.CTkFrame(sc, fg_color=BG_PANEL, corner_radius=14,
                                  border_width=1, border_color=BORDER)
        chat_card.pack(fill="x", padx=22, pady=(0, 12))
        self._chat_inner = ctk.CTkFrame(chat_card, fg_color="transparent")
        self._chat_inner.pack(fill="x", padx=14, pady=14)

        input_row = ctk.CTkFrame(sc, fg_color="transparent")
        input_row.pack(fill="x", padx=22, pady=(0, 22))
        self._entry = ctk.CTkEntry(input_row, fg_color=BG_PANEL, border_color=BORDER,
                                   text_color=TEXT_PRI, height=46, font=FONT_BODY,
                                   placeholder_text="Komutunuzu yazın veya soru sorun...")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", lambda e: self._ask(self._entry.get()))
        self._send_btn = ctk.CTkButton(input_row, text=i18n.t("common.send"),
                                       fg_color=ACCENT, hover_color=ACCENT_H,
                                       text_color=TEXT_PRI, height=46, width=110,
                                       font=FONT_BODY_BOLD, corner_radius=8,
                                       command=lambda: self._ask(self._entry.get()))
        self._send_btn.pack(side="left")

    def _ask(self, question):
        question = question.strip()
        if not question:
            return
        self._entry.delete(0, "end")
        self._send_btn.configure(state="disabled", text="...")
        self._add_bubble(question, is_user=True)
        ai_engine.get_response(question, self._on_response)

    def _on_response(self, result):
        self.after(0, lambda: self._handle_response(result))
        self.after(0, lambda: self._send_btn.configure(
            state="normal", text=i18n.t("common.send")))

    def _handle_response(self, result):
        if isinstance(result, dict) and result.get("type") == "action_proposal":
            self._pending = result["action"]
            self._add_proposal(result["action"])
        else:
            text = result["text"] if isinstance(result, dict) else str(result)
            self._add_bubble(text, is_user=False)

    def _add_bubble(self, text, is_user):
        align = "e" if is_user else "w"
        bg = BG_CARD if is_user else ACCENT_DK
        prefix = "Siz" if is_user else "Akıl Hocası"
        col = TEXT_PRI if is_user else ACCENT

        wrap = ctk.CTkFrame(self._chat_inner, fg_color="transparent")
        wrap.pack(fill="x", anchor=align, pady=4)
        f = ctk.CTkFrame(wrap, fg_color=bg, corner_radius=10)
        f.pack(anchor=align, padx=8)
        ctk.CTkLabel(f, text=prefix, font=FONT_TINY,
                     text_color=col).pack(anchor="w", padx=14, pady=(8, 0))
        ctk.CTkLabel(f, text=text, font=FONT_SMALL,
                     text_color=TEXT_PRI, wraplength=820,
                     justify="left").pack(padx=14, pady=(2, 10))

    def _add_proposal(self, action):
        wrap = ctk.CTkFrame(self._chat_inner, fg_color="transparent")
        wrap.pack(fill="x", anchor="w", pady=4)
        f = ctk.CTkFrame(wrap, fg_color=ACCENT_DK, corner_radius=10,
                         border_width=2, border_color=ACCENT)
        f.pack(anchor="w", padx=8, fill="x")
        ctk.CTkLabel(f, text="ONAY GEREKTIREN AKSIYON", font=FONT_TINY,
                     text_color=ACCENT).pack(anchor="w", padx=14, pady=(10, 0))
        ctk.CTkLabel(f, text=action["confirm_text"], font=FONT_SMALL_BOLD,
                     text_color=TEXT_PRI, wraplength=820,
                     justify="left").pack(anchor="w", padx=14, pady=(2, 10))
        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(btns, text=i18n.t("common.approve"),
                      fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT_PRI,
                      height=34, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=lambda: self._approve(action, f)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text=i18n.t("common.reject"),
                      fg_color=BG_CARD, hover_color=BG_HOVER, text_color=DANGER,
                      height=34, font=FONT_SMALL_BOLD, corner_radius=8,
                      command=lambda: self._reject(f)).pack(side="left")

    def _approve(self, action, frame):
        result = ai_engine.apply_action(action)
        frame.destroy()
        self._add_bubble(result, is_user=False)
        self._pending = None

    def _reject(self, frame):
        frame.destroy()
        self._add_bubble("Aksiyon iptal edildi.", is_user=False)
        self._pending = None

    def _handle_action(self, n):
        msg = (f"'{n['title']}' uyarisi icin onerilen aksiyon: '{n['action']}'. "
               f"Detayli analiz icin Akil Hocasi sohbetini kullanin.")
        self._add_bubble(msg, is_user=False)
        db.mark_notification_read(n["id"])
