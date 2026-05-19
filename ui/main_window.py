import customtkinter as ctk
from ui.theme import *
from ui.widgets import NotificationBell
from ui.agent_widget import GlobalAgent
from core import database as db
from core import i18n, currency


NAV_KEYS = [
    ("dashboard",    "nav.dashboard",    "📊"),
    ("inventory",    "nav.inventory",    "📦"),
    ("orders",       "nav.orders",       "🧾"),
    ("finance",      "nav.finance",      "💰"),
    ("advisor",      "nav.advisor",      "🧠"),
    ("marketplaces", "nav.marketplaces", "🌐"),
    ("profile",      "nav.profile",      "⚙"),
]


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        db.init_db()
        i18n.load()
        currency.load()
        i18n.subscribe(self._refresh_labels)
        currency.subscribe(self._refresh_pages)

        self.title("SPA Center — Akıllı Satıcı Paneli")
        self.geometry("1440x880")
        self.minsize(1120, 720)
        self.configure(fg_color=BG_DARK)

        self._pages = {}
        self._active = None
        self._build()

    def _build(self):
        self._topbar = ctk.CTkFrame(self, height=54, fg_color=BG_PANEL,
                                     corner_radius=0, border_width=0)
        self._topbar.pack(side="top", fill="x")
        self._topbar.pack_propagate(False)

        brand = ctk.CTkFrame(self._topbar, fg_color="transparent")
        brand.pack(side="left", padx=18)
        ctk.CTkLabel(brand, text="SPA", font=(FONT_FAMILY, 20, "bold"),
                     text_color=ACCENT).pack(side="left")
        ctk.CTkLabel(brand, text="Center", font=FONT_SUB,
                     text_color=TEXT_PRI).pack(side="left", padx=(8, 0), pady=(3, 0))

        controls = ctk.CTkFrame(self._topbar, fg_color="transparent")
        controls.pack(side="right", padx=16)

        self._notif_btn = NotificationBell(controls, self._open_notifications)
        self._notif_btn.pack(side="right", padx=6)

        self._omnicore_btn = ctk.CTkButton(
            controls, text="📊  Akıllı Panel",
            width=150, height=34, corner_radius=8,
            fg_color=ACCENT_DK, hover_color=BG_HOVER,
            text_color=ACCENT, font=FONT_SMALL_BOLD,
            border_width=1, border_color=ACCENT,
            command=self._open_omnicore)
        self._omnicore_btn.pack(side="right", padx=6)
        try:
            from ui.widgets import Tooltip
            Tooltip(self._omnicore_btn,
                     "Akıllı Panel — Tüm motorlardan canlı özet: stok, "
                     "sipariş, kâr, kargo, AI maliyetleri. Tek tıkla "
                     "operasyonun nabzı.")
        except Exception:
            pass

        self._cur_btn = ctk.CTkSegmentedButton(controls, values=["TRY", "USD"],
                                                fg_color=BG_DARK,
                                                selected_color=ACCENT,
                                                selected_hover_color=ACCENT_H,
                                                unselected_color=BG_DARK,
                                                text_color=TEXT_PRI,
                                                font=FONT_SMALL_BOLD,
                                                command=self._on_currency)
        self._cur_btn.set(currency.get())
        self._cur_btn.pack(side="right", padx=6)

        self._lang_btn = ctk.CTkSegmentedButton(controls, values=["TR", "EN"],
                                                 fg_color=BG_DARK,
                                                 selected_color=ACCENT,
                                                 selected_hover_color=ACCENT_H,
                                                 unselected_color=BG_DARK,
                                                 text_color=TEXT_PRI,
                                                 font=FONT_SMALL_BOLD,
                                                 command=self._on_lang)
        self._lang_btn.set(i18n.get_lang().upper())
        self._lang_btn.pack(side="right", padx=6)

        self._rate_lbl = ctk.CTkLabel(controls,
                                       text=f"1 USD = {currency.rate_usd_try():.2f} TL",
                                       font=FONT_TINY, text_color=TEXT_SEC)
        self._rate_lbl.pack(side="right", padx=14)

        body = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        body.pack(side="top", fill="both", expand=True)

        self._sidebar = ctk.CTkFrame(body, width=SIDEBAR_W, fg_color=BG_PANEL,
                                     corner_radius=0, border_width=1, border_color=BORDER)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        ctk.CTkLabel(self._sidebar, text="MENU",
                     font=FONT_TINY, text_color=TEXT_MUT).pack(anchor="w", padx=22, pady=(18, 6))

        self._nav_btns = {}
        for key, t_key, icon in NAV_KEYS:
            btn = ctk.CTkButton(
                self._sidebar, text=f"  {icon}    {i18n.t(t_key)}",
                font=FONT_BODY_BOLD, height=42,
                fg_color="transparent", hover_color=BG_HOVER,
                text_color=TEXT_SEC, anchor="w",
                corner_radius=8,
                command=lambda k=key: self.navigate(k)
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[key] = btn

        ctk.CTkFrame(self._sidebar, height=1, fg_color=BORDER).pack(
            fill="x", padx=14, pady=(14, 8), side="bottom")
        ctk.CTkLabel(self._sidebar, text="v2.0.0",
                     font=FONT_TINY, text_color=TEXT_MUT).pack(side="bottom", pady=(0, 16))

        self._content = ctk.CTkFrame(body, fg_color=BG_DARK, corner_radius=0)
        self._content.pack(side="left", fill="both", expand=True)

        self.navigate("dashboard")
        self._update_notif_count()
        self.after(15000, self._tick)
        self._agent = GlobalAgent(self, refresh_pages_cb=self._refresh_pages)

    def _tick(self):
        self._update_notif_count()
        self._rate_lbl.configure(text=f"1 USD = {currency.rate_usd_try():.2f} TL")
        self.after(15000, self._tick)

    def _update_notif_count(self):
        try:
            unread = db.get_notifications(only_unread=True)
            self._notif_btn.set_count(len(unread))
        except Exception:
            pass

    def _on_currency(self, val):
        currency.set(val)

    def _on_lang(self, val):
        i18n.set_lang(val.lower())

    def _refresh_labels(self):
        for key, t_key, icon in NAV_KEYS:
            self._nav_btns[key].configure(text=f"  {icon}    {i18n.t(t_key)}")
        self._refresh_pages()

    def _refresh_pages(self):
        active = self._active
        for key, page in list(self._pages.items()):
            try:
                page.destroy()
            except Exception:
                pass
        self._pages.clear()
        if active:
            self._active = None
            self.navigate(active)

    def navigate(self, key: str, **kwargs):
        if self._active == key and not kwargs:
            return
        if key not in self._pages or kwargs:
            if key in self._pages:
                try:
                    self._pages[key].destroy()
                except Exception:
                    pass
                del self._pages[key]
            self._pages[key] = self._make_page(key, **kwargs)
        for k, btn in self._nav_btns.items():
            btn.configure(fg_color=ACCENT if k == key else "transparent",
                          text_color=TEXT_PRI if k == key else TEXT_SEC)
        if self._active and self._active in self._pages and self._active != key:
            try:
                self._pages[self._active].pack_forget()
            except Exception:
                pass
        self._pages[key].pack(fill="both", expand=True)
        self._active = key

    def _make_page(self, key, **kwargs):
        if key == "dashboard":
            from ui.pages.dashboard import DashboardPage
            return DashboardPage(self._content, navigator=self.navigate)
        if key == "inventory":
            from ui.pages.inventory import InventoryPage
            return InventoryPage(self._content, focus_sku=kwargs.get("focus_sku"))
        if key == "orders":
            from ui.pages.orders import OrdersPage
            return OrdersPage(self._content, tab=kwargs.get("tab"))
        if key == "finance":
            from ui.pages.finance import FinancePage
            return FinancePage(self._content)
        if key == "advisor":
            from ui.pages.advisor import AdvisorPage
            return AdvisorPage(self._content, navigator=self.navigate)
        if key == "marketplaces":
            from ui.pages.marketplaces import MarketplacesPage
            return MarketplacesPage(self._content)
        if key == "profile":
            from ui.pages.profile import ProfilePage
            return ProfilePage(self._content)
        return ctk.CTkFrame(self._content, fg_color=BG_DARK)

    def _open_omnicore(self):
        from ui.omnicore_dashboard import open_omnicore_dashboard
        win = open_omnicore_dashboard(self)
        try:
            win.lift()
            win.focus_force()
        except Exception:
            pass
        return win

    def _open_notifications(self):
        win = ctk.CTkToplevel(self)
        win.title(i18n.t("common.notifications"))
        win.geometry("560x640")
        win.configure(fg_color=BG_PANEL)
        win.grab_set()

        ctk.CTkLabel(win, text=i18n.t("common.notifications"),
                     font=FONT_HEAD, text_color=TEXT_PRI).pack(anchor="w", padx=20, pady=(18, 10))

        sf = ctk.CTkScrollableFrame(win, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=10, pady=(0, 16))

        notifs = db.get_notifications()
        _col = {"danger": DANGER, "warning": WARNING, "info": INFO, "success": ACCENT}
        for n in notifs:
            c = _col.get(n["type"], INFO)
            card = ctk.CTkFrame(sf, fg_color=BG_DARK, corner_radius=10,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", padx=8, pady=5)
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(top, text=f"P{n['severity']}", font=FONT_TINY,
                         text_color=c, fg_color=BG_CARD,
                         corner_radius=4, width=36).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(top, text=n["title"], font=FONT_BODY_BOLD,
                         text_color=c).pack(side="left")
            if n["read"] == 0:
                ctk.CTkLabel(top, text="●", text_color=ACCENT,
                             font=FONT_BODY).pack(side="right")
            ctk.CTkLabel(card, text=n["body"], font=FONT_SMALL,
                         text_color=TEXT_PRI, wraplength=480,
                         justify="left").pack(anchor="w", padx=12, pady=(0, 8))

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.pack(fill="x", padx=12, pady=(0, 10))
            if n.get("target_sku"):
                ctk.CTkButton(actions, text=f"→ {n['target_sku']}", height=28,
                              fg_color=BG_CARD, hover_color=BG_HOVER,
                              text_color=INFO, font=FONT_SMALL,
                              command=lambda nn=n: (
                                  db.mark_notification_read(nn["id"]),
                                  win.destroy(),
                                  self.navigate("inventory",
                                                 focus_sku=nn["target_sku"]))).pack(side="left", padx=(0, 6))
            ctk.CTkButton(actions, text="Okundu", height=28, width=80,
                          fg_color=BG_CARD, hover_color=BG_HOVER,
                          text_color=TEXT_SEC, font=FONT_SMALL,
                          command=lambda nn=n, cc=card: (
                              db.mark_notification_read(nn["id"]),
                              cc.destroy(),
                              self._update_notif_count())).pack(side="right")

        for n in notifs:
            if n["read"] == 0:
                pass
        self._update_notif_count()
