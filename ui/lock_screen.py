# -*- coding: utf-8 -*-
import customtkinter as ctk
from typing import Optional, Callable

from ui.theme import *
from ui.widgets import Pill
from core import credentials


class IntegrationLockCard(ctk.CTkFrame):
    def __init__(self, parent, page_name: str,
                  on_configure: Optional[Callable] = None,
                  required_platforms: Optional[list[str]] = None):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=14,
                          border_width=2, border_color=WARNING)
        self._page_name = page_name
        self._on_configure = on_configure
        self._required = required_platforms or [credentials.PLATFORM_TRENDYOL]
        self._build()

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=32, pady=32)

        head = ctk.CTkFrame(inner, fg_color="transparent")
        head.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(head, text="🔒", font=(FONT_FAMILY, 36),
                      text_color=WARNING).pack(side="left", padx=(0, 16))
        title_box = ctk.CTkFrame(head, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_box, text=f"{self._page_name} — Kilitli",
                      font=FONT_H1, text_color=TEXT_PRI,
                      anchor="w").pack(anchor="w")
        ctk.CTkLabel(title_box,
                      text="Bu modül gerçek veri ile çalışır. Pazar yeri "
                            "entegrasyonunuzu kuran kadar verileri 0 olarak "
                            "gösterir veya kapalı kalır.",
                      font=FONT_SMALL, text_color=TEXT_SEC,
                      wraplength=720, justify="left",
                      anchor="w").pack(anchor="w", pady=(4, 0))

        ctk.CTkFrame(inner, height=1, fg_color=BORDER).pack(fill="x", pady=14)

        ctk.CTkLabel(inner, text="Aktif Pazar Yerleri",
                      font=FONT_SUB, text_color=TEXT_PRI,
                      anchor="w").pack(anchor="w")
        list_frame = ctk.CTkFrame(inner, fg_color="transparent")
        list_frame.pack(fill="x", pady=(8, 14))
        for p in self._required:
            label = credentials.PLATFORM_LABELS.get(p, p)
            configured = credentials.is_configured(p)
            row = ctk.CTkFrame(list_frame, fg_color=BG_DARK, corner_radius=10)
            row.pack(fill="x", pady=4)
            inner_r = ctk.CTkFrame(row, fg_color="transparent")
            inner_r.pack(fill="x", padx=14, pady=10)
            icon_lbl = ctk.CTkLabel(
                inner_r,
                text=("✅" if configured else "○"),
                font=(FONT_FAMILY, 16, "bold"),
                text_color=ACCENT if configured else TEXT_MUT)
            icon_lbl.pack(side="left", padx=(0, 12))
            ctk.CTkLabel(inner_r, text=label, font=FONT_BODY_BOLD,
                          text_color=TEXT_PRI).pack(side="left")
            badge_text = "AKTİF" if configured else "BEKLİYOR"
            badge_col = ACCENT if configured else WARNING
            Pill(inner_r, f"  {badge_text}  ", badge_col,
                  BG_CARD).pack(side="right")

        cta = ctk.CTkButton(
            inner, text="⚙  Profil → Pazar Yeri Entegrasyonu",
            height=44, font=FONT_BODY_BOLD,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color=BG_DARK,
            corner_radius=10,
            command=self._handle_configure)
        cta.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(
            inner,
            text="API bilgilerinizi (Satıcı ID + API Key + Secret) Profil "
                  "sayfasındaki 'Pazar Yeri Entegrasyonu' bölümünden girin. "
                  "Veriler şifreli olarak lokalde saklanır, bulutla "
                  "paylaşılmaz.",
            font=FONT_TINY, text_color=TEXT_MUT,
            wraplength=720, justify="left").pack(anchor="w", pady=(14, 0))

    def _handle_configure(self):
        if self._on_configure:
            try:
                self._on_configure()
                return
            except Exception:
                pass


def needs_credentials(platform: str = None) -> bool:
    if platform:
        return not credentials.is_configured(platform)
    return not credentials.any_configured()


__all__ = ["IntegrationLockCard", "needs_credentials"]
