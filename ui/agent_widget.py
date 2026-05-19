# -*- coding: utf-8 -*-
"""Global Akıl Hocası — uygulamanın her sayfasından erişilebilen floating
chat widget'ı. Sağ alt köşede yuvarlak buton; tıklayınca yan-panel açılır.

- Her sayfanın bağlamından bağımsız çalışır (database üzerinden)
- ai_engine.get_response ile aksiyon önerisi yakalar
- Onaylanırsa apply_action ile DB'yi değiştirir, sayfayı yeniler"""
from __future__ import annotations
import customtkinter as ctk
from ui.theme import *
from ui.widgets import Pill
from core import ai_engine, database as db


class GlobalAgent:
    def __init__(self, root, refresh_pages_cb=None):
        self.root = root
        self.refresh_cb = refresh_pages_cb or (lambda: None)
        self._panel = None
        self._chat_inner = None
        self._entry = None
        self._send_btn = None
        self._pending = None
        self._history = []
        self._build_fab()

    def _build_fab(self):
        """Floating action button (sağ alt köşe)"""
        self._fab = ctk.CTkButton(
            self.root, text="🧠",
            font=("Segoe UI Symbol", 22),
            width=56, height=56, corner_radius=28,
            fg_color=ACCENT, hover_color=ACCENT_H,
            text_color=BG_DARK,
            border_width=2, border_color=ACCENT,
            command=self.toggle)
        self.root.after(100, self._place_fab)
        self.root.bind("<Configure>", lambda e: self._place_fab(), add="+")

    def _place_fab(self):
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self._fab.place(x=w - 80, y=h - 80)
            if self._panel is not None and self._panel.winfo_exists():
                self._reposition_panel()
        except Exception:
            pass

    def toggle(self):
        if self._panel is not None and self._panel.winfo_exists():
            self._panel.destroy()
            self._panel = None
            self._fab.configure(text="🧠")
            return
        self._open_panel()
        self._fab.configure(text="✕")

    def _open_panel(self):
        self._panel = ctk.CTkFrame(self.root, fg_color=BG_PANEL,
                                    corner_radius=14, border_width=2,
                                    border_color=ACCENT, width=420, height=560)
        self._panel.pack_propagate(False)
        self._reposition_panel()

        # Header
        hdr = ctk.CTkFrame(self._panel, fg_color=ACCENT_DK, corner_radius=0,
                           height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        title = ctk.CTkFrame(hdr, fg_color="transparent")
        title.pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(title, text="🧠 Akıl Hocası",
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(side="left")
        Pill(hdr, "  AKTİF  ", ACCENT, BG_DARK).pack(side="left", padx=10, pady=14)
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="transparent", hover_color=BG_HOVER,
                      text_color=TEXT_PRI, font=FONT_BODY_BOLD,
                      command=self.toggle).pack(side="right", padx=12, pady=10)

        # Chat scroll area
        self._chat_inner = ctk.CTkScrollableFrame(
            self._panel, fg_color=BG_DARK,
            scrollbar_button_color=BORDER)
        self._chat_inner.pack(fill="both", expand=True, padx=8, pady=8)

        self._add_bubble(
            "Merhaba! Bir şey değiştirmek veya analiz görmek için bana söyle.\n"
            "Örnek: 'TS-001 fiyatını 280 TL yap', 'SN-014 için sipariş ver', "
            "'%15 indirim kampanyası başlat'",
            is_user=False)

        quick = ctk.CTkFrame(self._panel, fg_color=BG_PANEL)
        quick.pack(fill="x", padx=8, pady=(0, 6))
        for q in ["Stok durumu?", "İade riskli ürün?", "Bayram kampanyası"]:
            ctk.CTkButton(quick, text=q, height=28, font=FONT_TINY,
                          fg_color=BG_CARD, hover_color=BG_HOVER,
                          text_color=INFO, corner_radius=6,
                          command=lambda x=q: self._ask(x)).pack(
                side="left", padx=2, pady=4)

        # Input
        ibar = ctk.CTkFrame(self._panel, fg_color=BG_PANEL)
        ibar.pack(fill="x", padx=8, pady=(0, 10))
        self._entry = ctk.CTkEntry(ibar, fg_color=BG_DARK, border_color=BORDER,
                                    text_color=TEXT_PRI, height=40, font=FONT_SMALL,
                                    placeholder_text="Komut veya soru…")
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._entry.bind("<Return>", lambda e: self._ask(self._entry.get()))
        self._send_btn = ctk.CTkButton(ibar, text="↑", width=44, height=40,
                                        font=FONT_HEAD,
                                        fg_color=ACCENT, hover_color=ACCENT_H,
                                        text_color=BG_DARK, corner_radius=8,
                                        command=lambda: self._ask(self._entry.get()))
        self._send_btn.pack(side="right")

    def _reposition_panel(self):
        try:
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            pw, ph = 420, 560
            x = max(20, w - pw - 30)
            y = max(20, h - ph - 100)
            self._panel.place(x=x, y=y)
            self._fab.lift()
        except Exception:
            pass

    def _ask(self, q):
        q = (q or "").strip()
        if not q or self._chat_inner is None:
            return
        self._entry.delete(0, "end")
        self._send_btn.configure(state="disabled", text="…")
        self._add_bubble(q, is_user=True)
        ai_engine.get_response(q, lambda r: self.root.after(0, lambda: self._on_response(r)))

    def _on_response(self, result):
        self._send_btn.configure(state="normal", text="↑")
        if isinstance(result, dict) and result.get("type") == "action_proposal":
            self._pending = result["action"]
            self._add_proposal(result["action"])
        else:
            text = result["text"] if isinstance(result, dict) else str(result)
            self._add_bubble(text, is_user=False)

    def _add_bubble(self, text, is_user):
        if self._chat_inner is None or not self._chat_inner.winfo_exists():
            return
        anchor = "e" if is_user else "w"
        bg = BG_CARD if is_user else ACCENT_DK
        prefix = "Siz" if is_user else "Akıl Hocası"
        col = TEXT_PRI if is_user else ACCENT

        wrap = ctk.CTkFrame(self._chat_inner, fg_color="transparent")
        wrap.pack(fill="x", anchor=anchor, pady=3)
        f = ctk.CTkFrame(wrap, fg_color=bg, corner_radius=10)
        f.pack(anchor=anchor, padx=6)
        ctk.CTkLabel(f, text=prefix, font=FONT_TINY,
                     text_color=col).pack(anchor="w", padx=12, pady=(6, 0))
        ctk.CTkLabel(f, text=text, font=FONT_SMALL,
                     text_color=TEXT_PRI, wraplength=320,
                     justify="left").pack(padx=12, pady=(2, 8))
        # Auto-scroll
        self._chat_inner.update_idletasks()
        try:
            self._chat_inner._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _add_proposal(self, action):
        if self._chat_inner is None:
            return
        wrap = ctk.CTkFrame(self._chat_inner, fg_color="transparent")
        wrap.pack(fill="x", anchor="w", pady=3)
        f = ctk.CTkFrame(wrap, fg_color=ACCENT_DK, corner_radius=10,
                         border_width=2, border_color=ACCENT)
        f.pack(anchor="w", padx=6, fill="x")
        ctk.CTkLabel(f, text="ONAY GEREKTİRİYOR",
                     font=FONT_TINY, text_color=ACCENT).pack(
            anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(f, text=action["confirm_text"],
                     font=FONT_SMALL_BOLD, text_color=TEXT_PRI,
                     wraplength=320, justify="left").pack(
            anchor="w", padx=12, pady=(2, 8))
        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(btns, text="✓ Onayla", height=30,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color=BG_DARK, font=FONT_SMALL_BOLD,
                      corner_radius=6,
                      command=lambda: self._apply(action)).pack(
            side="left", padx=(0, 6))
        ctk.CTkButton(btns, text="✗ İptal", height=30,
                      fg_color=BG_CARD, hover_color=BG_HOVER,
                      text_color=TEXT_SEC, font=FONT_SMALL_BOLD,
                      corner_radius=6,
                      command=self._reject).pack(side="left")

    def _apply(self, action):
        msg = ai_engine.apply_action(action)
        self._pending = None
        self._add_bubble(msg, is_user=False)
        try:
            self.refresh_cb()
        except Exception:
            pass

    def _reject(self):
        self._pending = None
        self._add_bubble("İptal edildi. Başka bir konuda yardım edebilir miyim?",
                          is_user=False)
