# -*- coding: utf-8 -*-
import threading
import customtkinter as ctk
from tkinter import messagebox
from typing import Optional, Callable

from ui.theme import *
from ui.widgets import Pill, Tooltip
from core import credentials


class PlatformCredentialsDialog(ctk.CTkToplevel):
    def __init__(self, parent, platform: str,
                  on_saved: Optional[Callable] = None):
        super().__init__(parent)
        self.platform = (platform or "").lower()
        self.on_saved = on_saved
        label = credentials.PLATFORM_LABELS.get(self.platform, self.platform)
        self.title(f"{label} Entegrasyonu — API Bilgileri")
        self.geometry("680x680")
        self.configure(fg_color=BG_DARK)
        self.grab_set()
        self.after(50, self._bring_to_front)
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build()

    def _bring_to_front(self):
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(400, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _build(self):
        label = credentials.PLATFORM_LABELS.get(self.platform, self.platform)

        hdr = ctk.CTkFrame(self, fg_color=BG_PANEL, height=58,
                            corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"{label} Entegrasyonu",
                      font=FONT_H1, text_color=TEXT_PRI).pack(
            side="left", padx=20, pady=14)
        configured = credentials.is_configured(self.platform)
        Pill(hdr, "  AKTİF  " if configured else "  YAPILMAMIŞ  ",
              ACCENT if configured else WARNING, ACCENT_DK if configured else BG_CARD
              ).pack(side="left", padx=10, pady=18)
        ctk.CTkButton(hdr, text="✕", width=36, height=34,
                      fg_color="transparent", hover_color=BG_HOVER,
                      text_color=TEXT_PRI, font=FONT_HEAD,
                      command=self.destroy).pack(side="right", padx=12, pady=12)

        body = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                        scrollbar_button_color=BORDER)
        body.pack(fill="both", expand=True, padx=14, pady=14)

        intro = ctk.CTkFrame(body, fg_color=BG_PANEL, corner_radius=12,
                              border_width=1, border_color=INFO)
        intro.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(intro, text="ℹ  Bu bilgiler nereden bulunur?",
                      font=FONT_SUB, text_color=INFO).pack(
            anchor="w", padx=18, pady=(14, 4))
        intro_text = self._intro_text()
        ctk.CTkLabel(intro, text=intro_text, font=FONT_SMALL,
                      text_color=TEXT_SEC, wraplength=600,
                      justify="left").pack(anchor="w", padx=18, pady=(0, 14))

        fields_card = ctk.CTkFrame(body, fg_color=BG_PANEL, corner_radius=12,
                                     border_width=1, border_color=BORDER)
        fields_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(fields_card, text="API Bilgileri",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(
            anchor="w", padx=18, pady=(14, 4))

        existing = credentials.get_credentials(self.platform) or {}
        fields = credentials.PLATFORM_FIELDS.get(self.platform, [])
        for key, label_t, tooltip_t in fields:
            row = ctk.CTkFrame(fields_card, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=6)
            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x")
            lbl = ctk.CTkLabel(head, text=label_t, font=FONT_SMALL_BOLD,
                                 text_color=TEXT_PRI)
            lbl.pack(side="left")
            help_dot = ctk.CTkLabel(head, text="ⓘ", font=FONT_SMALL,
                                       text_color=INFO, cursor="hand2")
            help_dot.pack(side="left", padx=6)
            try:
                Tooltip(help_dot, tooltip_t)
                Tooltip(lbl, tooltip_t)
            except Exception:
                pass
            is_secret = ("secret" in key.lower() or
                          "password" in key.lower() or
                          "token" in key.lower())
            entry = ctk.CTkEntry(
                row, fg_color=BG_DARK, border_color=BORDER,
                text_color=TEXT_PRI, height=36, font=FONT_BODY,
                show="•" if is_secret else "")
            entry.pack(fill="x", pady=(6, 0))
            if existing.get(key):
                entry.insert(0, str(existing[key]))
            self._entries[key] = entry

        st = credentials.get_status(self.platform)
        if st.get("configured"):
            note = ctk.CTkFrame(body, fg_color=BG_PANEL, corner_radius=10,
                                  border_width=1, border_color=BORDER)
            note.pack(fill="x", pady=(0, 14))
            ctk.CTkLabel(note,
                          text=f"Son güncelleme: {(st.get('updated_at') or '')[:19]}",
                          font=FONT_TINY, text_color=TEXT_MUT).pack(
                anchor="w", padx=18, pady=(10, 2))
            if st.get("last_error"):
                ctk.CTkLabel(note,
                              text=f"⚠ Son doğrulama hatası: {st['last_error'][:200]}",
                              font=FONT_TINY, text_color=DANGER,
                              wraplength=580, justify="left").pack(
                    anchor="w", padx=18, pady=(0, 10))

        self._status_box = ctk.CTkFrame(self, fg_color=BG_DARK, height=0)
        self._status_box.pack(fill="x", side="bottom")
        self._status_lbl = ctk.CTkLabel(
            self._status_box, text="", font=FONT_SMALL, text_color=TEXT_SEC,
            wraplength=620, justify="left")
        self._status_lbl.pack(anchor="w", padx=18, pady=4)

        actions = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0,
                                 height=68)
        actions.pack(fill="x", side="bottom")
        actions.pack_propagate(False)
        ctk.CTkButton(actions, text="💾  Kaydet",
                      height=42, width=140, font=FONT_BODY_BOLD,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color=BG_DARK, corner_radius=10,
                      command=self._save).pack(side="right", padx=(6, 14), pady=12)
        self._test_btn = ctk.CTkButton(
            actions, text="🔌  Bağlantıyı Test Et",
            height=42, width=180, font=FONT_SMALL_BOLD,
            fg_color=BG_CARD, hover_color=BG_HOVER, text_color=INFO,
            border_width=1, border_color=INFO, corner_radius=10,
            command=self._test_only)
        self._test_btn.pack(side="right", padx=4, pady=12)
        if configured:
            ctk.CTkButton(actions, text="🗑  Sil",
                          height=42, width=90, font=FONT_SMALL_BOLD,
                          fg_color=BG_CARD, hover_color=BG_HOVER,
                          text_color=DANGER, corner_radius=10,
                          command=self._delete).pack(side="right", padx=4, pady=12)
        ctk.CTkButton(actions, text="İptal",
                      height=42, width=110, font=FONT_SMALL_BOLD,
                      fg_color=BG_CARD, hover_color=BG_HOVER,
                      text_color=TEXT_SEC, corner_radius=10,
                      command=self.destroy).pack(side="left", padx=14, pady=12)

    def _intro_text(self) -> str:
        if self.platform == credentials.PLATFORM_TRENDYOL:
            return (
                "1) Trendyol Partner > Entegrasyon Bilgilerim sekmesini açın.\n"
                "2) Satıcı (Cari) ID, API Key ve API Secret değerlerini "
                "kopyalayın. (Marka ID isteğe bağlı; girilmezse Cari ID "
                "kullanılır.)\n"
                "3) Bu pencereye yapıştırıp 'Kaydet ve Doğrula' butonuna "
                "basın. Sistem hemen ürünleri ve son siparişleri çekmeye "
                "başlar.\n\n"
                "Notlar: Bilgiler bilgisayarınızda XOR ile şifreli "
                "saklanır, internete gönderilmez. Trendyol Finans / "
                "Hakediş endpoint'i bazen 556 (Service Unavailable) "
                "dönebilir — bu Trendyol sunucusundan kaynaklı geçici "
                "bir sorundur, kalan endpoint'ler çalışmaya devam eder.")
        if self.platform == credentials.PLATFORM_HEPSIBURADA:
            return ("Hepsiburada Mağaza Yönetimi > Entegrasyon > API "
                     "Bilgileri sayfasından merchant ID, kullanıcı adı "
                     "ve şifrenizi girin.")
        if self.platform == credentials.PLATFORM_AMAZON:
            return ("Amazon Seller Central > Apps & Services > Develop "
                     "Apps > SP-API ile geliştirici hesabı oluşturun. "
                     "LWA refresh token, IAM Access/Secret Key ve "
                     "Marketplace ID gerekir.")
        if self.platform == credentials.PLATFORM_N11:
            return ("N11.com Magaza Yönetimi > Entegrasyon bilgilerinizi "
                     "girin. Sandık servisi kapatılırsa endpoint 503 dönebilir.")
        if self.platform == credentials.PLATFORM_ETSY:
            return ("Etsy Developer Portal'da yeni app oluşturup API "
                     "Key + Shared Secret + Shop ID bilgilerinizi girin.")
        return "Platform API bilgilerinizi alttaki alanlara girin."

    def _collect_data(self) -> dict:
        data = {}
        for key, entry in self._entries.items():
            val = entry.get().strip()
            if val:
                data[key] = val
        return data

    def _validate_required(self, data: dict) -> tuple[bool, str]:
        fields = credentials.PLATFORM_FIELDS.get(self.platform, [])
        required = [(k, lbl) for k, lbl, _ in fields if lbl.endswith("*")]
        missing = [lbl.rstrip(" *") for k, lbl in required if not data.get(k)]
        if missing:
            return False, ("Zorunlu alanları doldurmalısınız:\n  • " +
                           "\n  • ".join(missing))
        return True, ""

    def _set_status(self, text: str, color: str = None):
        try:
            self._status_lbl.configure(
                text=text, text_color=color or TEXT_SEC)
            self.update_idletasks()
        except Exception:
            pass

    def _test_only(self):
        data = self._collect_data()
        ok_req, msg = self._validate_required(data)
        if not ok_req:
            self._set_status("⚠  " + msg, WARNING)
            return
        verifier = self._build_verifier()
        if not verifier:
            self._set_status("Bu platform için bağlantı testi henüz desteklenmiyor.",
                              INFO)
            return
        self._test_btn.configure(state="disabled", text="🔌  Test ediliyor…")
        self._set_status("Trendyol API'sine bağlanılıyor…", INFO)

        def _run():
            try:
                ok, message = verifier(data)
            except Exception as exc:
                ok, message = False, str(exc)[:300]
            self.after(0, lambda: self._on_test_done(ok, message))
        threading.Thread(target=_run, daemon=True).start()

    def _on_test_done(self, ok: bool, message: str):
        self._test_btn.configure(state="normal", text="🔌  Bağlantıyı Test Et")
        if ok:
            self._set_status("✓ Bağlantı başarılı · " + message, ACCENT)
        else:
            self._set_status("✗ Bağlantı başarısız · " + message, DANGER)

    def _save(self):
        data = self._collect_data()
        ok_req, msg = self._validate_required(data)
        if not ok_req:
            messagebox.showerror("Eksik Zorunlu Alan", msg, parent=self)
            return

        verifier = self._build_verifier()
        result = credentials.save_credentials(self.platform, data,
                                                 verify_callback=verifier)

        if not result.get("saved"):
            err_detail = result.get("error", "Bilinmeyen hata")
            messagebox.showerror(
                "Kayıt Başarısız",
                f"Bilgiler bilgisayara kaydedilemedi.\n\n"
                f"Teknik detay: {err_detail}\n\n"
                f"SQLite veritabanı yazma hakkı yok olabilir veya disk dolu olabilir.",
                parent=self)
            return

        if result.get("verified"):
            messagebox.showinfo(
                "✓ Başarılı",
                f"{credentials.PLATFORM_LABELS.get(self.platform)} bilgileri "
                f"kaydedildi VE Trendyol API'sinden doğrulandı.\n\n"
                f"{result.get('message', '')}\n\n"
                "Artık sayaçlar gerçek satıcı paneliniz üzerinden çalışacak.",
                parent=self)
        else:
            err = result.get("verify_error") or result.get("message", "")
            messagebox.showwarning(
                "Kaydedildi — Ama Doğrulanamadı",
                f"Bilgiler bilgisayara kaydedildi.\n\n"
                f"Ancak Trendyol API'sine bağlanılırken sorun oluştu:\n\n"
                f"{err}\n\n"
                "Olası nedenler:\n"
                "  • API Key veya Secret hatalı yazılmış olabilir\n"
                "  • Cari ID eşleşmiyor olabilir\n"
                "  • Trendyol sunucusu geçici olarak yanıt vermiyor olabilir\n"
                "  • IP'niz Trendyol tarafında whitelist'te değil olabilir\n\n"
                "Bilgiler kayıtlı kalır; daha sonra 'Bağlantıyı Test Et' "
                "ile tekrar deneyebilirsiniz.",
                parent=self)
        if self.on_saved:
            try:
                self.on_saved(self.platform)
            except Exception:
                pass
        self.destroy()

    def _delete(self):
        confirm = messagebox.askyesno(
            "Bilgileri Sil",
            f"{credentials.PLATFORM_LABELS.get(self.platform)} entegrasyon "
            "bilgilerini silmek istediğinize emin misiniz? Bu platforma "
            "bağlı tüm modüller tekrar kilitlenir.",
            parent=self)
        if not confirm:
            return
        credentials.clear_credentials(self.platform)
        if self.on_saved:
            try:
                self.on_saved(self.platform)
            except Exception:
                pass
        self.destroy()

    def _build_verifier(self):
        if self.platform == credentials.PLATFORM_TRENDYOL:
            def _verify(payload):
                import os
                old_sid = os.environ.get("TRENDYOL_SELLER_ID", "")
                old_key = os.environ.get("TRENDYOL_API_KEY", "")
                old_sec = os.environ.get("TRENDYOL_API_SECRET", "")
                os.environ["TRENDYOL_SELLER_ID"]  = str(payload.get("seller_id", ""))
                os.environ["TRENDYOL_API_KEY"]    = payload.get("api_key", "")
                os.environ["TRENDYOL_API_SECRET"] = payload.get("api_secret", "")
                try:
                    from core import trendyol_sync as ts
                    ok, msg = ts.verify_credentials()
                    return ok, msg
                finally:
                    os.environ["TRENDYOL_SELLER_ID"]  = old_sid
                    os.environ["TRENDYOL_API_KEY"]    = old_key
                    os.environ["TRENDYOL_API_SECRET"] = old_sec
            return _verify
        return None


__all__ = ["PlatformCredentialsDialog"]
