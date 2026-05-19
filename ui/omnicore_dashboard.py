from __future__ import annotations
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import customtkinter as ctk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from sqlalchemy import select, func, desc

from ui.theme import *
from ui.widgets import Pill, ChartHover
from core.database_async import (
    AsyncSessionLocal, init_models,
    InventoryDecision, CarrierSelection, ForexPosition, IPInfringement,
    ADRCase, ShipmentAudit, ProcessTrace, PortfolioDecision,
    HybridInferenceLog, AnomalyEvent,
)


SEVERITY_COLORS = {
    "LOW":      ACCENT,
    "MEDIUM":   WARNING,
    "HIGH":     DANGER,
    "CRITICAL": DANGER,
}

DECISION_COLORS = {
    "CLEAN":      ACCENT,
    "SUSPICIOUS": WARNING,
    "INFRINGING": DANGER,
}

STATUS_COLORS = {
    "PASSED":  ACCENT,
    "ANDON":   WARNING,
    "BLOCKED": DANGER,
    "PENDING": INFO,
}

ADR_COLORS = {
    "REFUND":   INFO,
    "REPLACE":  ACCENT,
    "PARTIAL":  WARNING,
    "REJECT":   DANGER,
    "ESCALATE": DANGER,
    "GOODWILL": ACCENT,
}


async def _fetch_all_data() -> dict:
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    cutoff_7d = datetime.utcnow() - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        inv_decisions = (await session.execute(
            select(InventoryDecision)
            .order_by(desc(InventoryDecision.created_at))
            .limit(8))).scalars().all()
        inv_total = (await session.execute(
            select(func.count(InventoryDecision.id)))).scalar_one()
        inv_avg_cost = (await session.execute(
            select(func.coalesce(func.avg(InventoryDecision.total_cost), 0.0))
            )).scalar_one()

        carriers = (await session.execute(
            select(CarrierSelection)
            .order_by(desc(CarrierSelection.created_at))
            .limit(8))).scalars().all()
        carrier_wins = (await session.execute(
            select(CarrierSelection.selected_carrier,
                    func.count(CarrierSelection.id))
            .group_by(CarrierSelection.selected_carrier))).all()

        forex = (await session.execute(
            select(ForexPosition)
            .order_by(desc(ForexPosition.created_at))
            .limit(8))).scalars().all()
        forex_hedge_rec = (await session.execute(
            select(func.count(ForexPosition.id))
            .where(ForexPosition.hedge_recommended.is_(True)))).scalar_one()

        portfolio = (await session.execute(
            select(PortfolioDecision)
            .order_by(desc(PortfolioDecision.snapshot_at))
            .limit(1))).scalar_one_or_none()

        ip_rows = (await session.execute(
            select(IPInfringement)
            .order_by(desc(IPInfringement.created_at))
            .limit(8))).scalars().all()
        ip_infringing = (await session.execute(
            select(func.count(IPInfringement.id))
            .where(IPInfringement.decision == "INFRINGING"))).scalar_one()

        adr_open = (await session.execute(
            select(ADRCase)
            .where(ADRCase.settled.is_(False))
            .order_by(desc(ADRCase.created_at))
            .limit(8))).scalars().all()
        adr_by_action = (await session.execute(
            select(ADRCase.recommended_action,
                    func.count(ADRCase.id),
                    func.coalesce(func.sum(ADRCase.expected_cost), 0.0))
            .where(ADRCase.created_at >= cutoff_7d)
            .group_by(ADRCase.recommended_action))).all()

        shipments = (await session.execute(
            select(ShipmentAudit)
            .order_by(desc(ShipmentAudit.created_at))
            .limit(8))).scalars().all()
        ship_andon = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= cutoff_24h)
            .where(ShipmentAudit.andon_triggered.is_(True)))).scalar_one()
        ship_total = (await session.execute(
            select(func.count(ShipmentAudit.id))
            .where(ShipmentAudit.created_at >= cutoff_24h))).scalar_one()

        process = (await session.execute(
            select(ProcessTrace)
            .order_by(desc(ProcessTrace.created_at))
            .limit(8))).scalars().all()
        proc_by_severity = (await session.execute(
            select(ProcessTrace.severity, func.count(ProcessTrace.id))
            .where(ProcessTrace.created_at >= cutoff_24h)
            .group_by(ProcessTrace.severity))).all()

        hybrid_logs = (await session.execute(
            select(HybridInferenceLog)
            .order_by(desc(HybridInferenceLog.created_at))
            .limit(50))).scalars().all()
        hybrid_total = (await session.execute(
            select(func.count(HybridInferenceLog.id)))).scalar_one()
        hybrid_cost = (await session.execute(
            select(func.coalesce(func.sum(HybridInferenceLog.cost_usd), 0.0))
            )).scalar_one()
        hybrid_fallback = (await session.execute(
            select(func.count(HybridInferenceLog.id))
            .where(HybridInferenceLog.fallback_triggered.is_(True)))).scalar_one()

        anomalies = (await session.execute(
            select(AnomalyEvent)
            .where(AnomalyEvent.resolved.is_(False))
            .order_by(desc(AnomalyEvent.created_at))
            .limit(20))).scalars().all()
        anom_by_sev = (await session.execute(
            select(AnomalyEvent.severity, func.count(AnomalyEvent.id))
            .where(AnomalyEvent.resolved.is_(False))
            .group_by(AnomalyEvent.severity))).all()

    return {
        "inv_decisions":   [_inv_to_dict(r) for r in inv_decisions],
        "inv_total":       int(inv_total or 0),
        "inv_avg_cost":    float(inv_avg_cost or 0.0),
        "carriers":        [_carrier_to_dict(r) for r in carriers],
        "carrier_wins":    [(str(c), int(n)) for c, n in carrier_wins],
        "forex":           [_forex_to_dict(r) for r in forex],
        "forex_hedge_rec": int(forex_hedge_rec or 0),
        "portfolio":       _portfolio_to_dict(portfolio) if portfolio else None,
        "ip_rows":         [_ip_to_dict(r) for r in ip_rows],
        "ip_infringing":   int(ip_infringing or 0),
        "adr_open":        [_adr_to_dict(r) for r in adr_open],
        "adr_by_action":   [(str(a), int(n), float(c)) for a, n, c in adr_by_action],
        "shipments":       [_ship_to_dict(r) for r in shipments],
        "ship_andon_24h":  int(ship_andon or 0),
        "ship_total_24h":  int(ship_total or 0),
        "process":         [_proc_to_dict(r) for r in process],
        "proc_by_severity": [(str(s), int(n)) for s, n in proc_by_severity],
        "hybrid_logs":     [_hyb_to_dict(r) for r in hybrid_logs],
        "hybrid_total":    int(hybrid_total or 0),
        "hybrid_cost":     float(hybrid_cost or 0.0),
        "hybrid_fallback": int(hybrid_fallback or 0),
        "anomalies":       [_anom_to_dict(r) for r in anomalies],
        "anom_by_sev":     [(str(s), int(n)) for s, n in anom_by_sev],
        "fetched_at":      datetime.utcnow().isoformat(),
    }


def _inv_to_dict(r) -> dict:
    return {"id": r.id, "sku": r.sku, "method": r.method,
            "horizon": r.horizon,
            "total_cost": float(r.total_cost or 0),
            "avg_lot_size": float(r.avg_lot_size or 0),
            "order_count": len(r.order_periods or []),
            "created_at": r.created_at}


def _carrier_to_dict(r) -> dict:
    scores = r.closeness_scores or []
    top_score = scores[r.selected_index] if scores and r.selected_index < len(scores) else 0.0
    return {"id": r.id, "order_id": r.order_id,
            "selected": r.selected_carrier,
            "score": float(top_score),
            "n_candidates": len(r.candidates or []),
            "created_at": r.created_at}


def _forex_to_dict(r) -> dict:
    return {"id": r.id, "pair": r.pair,
            "notional": float(r.notional or 0),
            "var": float(r.parametric_var or 0),
            "es": float(r.expected_shortfall or 0),
            "hedge": bool(r.hedge_recommended),
            "ratio": float(r.hedge_ratio or 0),
            "created_at": r.created_at}


def _portfolio_to_dict(r) -> dict:
    return {"id": r.id,
            "selected": list(r.selected_skus or []),
            "weights": list(r.selected_weights or []),
            "expected_return": float(r.expected_return or 0),
            "sigma": float(r.portfolio_sigma or 0),
            "method": r.method,
            "snapshot": r.snapshot_at}


def _ip_to_dict(r) -> dict:
    return {"id": r.id, "sku": r.listing_sku,
            "decision": r.decision, "risk": r.risk_level,
            "hamming": int(r.hamming_distance or 0),
            "similarity": float(r.similarity_pct or 0),
            "tfidf": float(r.trademark_tfidf or 0)}


def _adr_to_dict(r) -> dict:
    return {"id": r.id, "order_id": r.order_id,
            "type": r.dispute_type,
            "action": r.recommended_action,
            "claimed": float(r.claimed_amount or 0),
            "expected_cost": float(r.expected_cost or 0),
            "evidence": float(r.evidence_score or 0),
            "cltv": float(r.cltv_score or 0)}


def _ship_to_dict(r) -> dict:
    return {"id": r.id, "order_id": r.order_id,
            "status": r.status,
            "bom_compliance": float(r.bom_compliance or 0),
            "temp_max": float(r.temp_max or 0),
            "shock_events": int(r.shock_events or 0),
            "andon": bool(r.andon_triggered)}


def _proc_to_dict(r) -> dict:
    return {"id": r.id, "trace_id": r.trace_id,
            "process": r.process_name,
            "damerau": int(r.damerau_distance or 0),
            "pct": float(r.deviation_pct or 0),
            "severity": r.severity}


def _hyb_to_dict(r) -> dict:
    return {"id": r.id, "kind": r.request_kind,
            "route": r.routed_to,
            "latency": int(r.latency_ms or 0),
            "cost": float(r.cost_usd or 0),
            "confidence": float(r.confidence or 0),
            "fallback": bool(r.fallback_triggered)}


def _anom_to_dict(r) -> dict:
    return {"id": r.id, "table": r.source_table,
            "src_id": r.source_id, "severity": r.severity,
            "description": r.description or ""}


class OmniCoreDashboardWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Akıllı Panel — SPA Center")
        self.geometry("1400x900")
        self.minsize(1100, 700)
        self.configure(fg_color=BG_DARK)
        self._data: dict = {}
        self._loading = False
        self._build_chrome()
        self._build_body()
        self.after(150, self._async_refresh)
        self.after(50, self._bring_to_front)

    def _bring_to_front(self):
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.after(500, lambda: self.attributes("-topmost", False))
        except Exception:
            pass

    def _build_chrome(self):
        bar = ctk.CTkFrame(self, height=58, fg_color=BG_PANEL,
                            corner_radius=0, border_width=0)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)
        title_box = ctk.CTkFrame(bar, fg_color="transparent")
        title_box.pack(side="left", padx=20)
        ctk.CTkLabel(title_box, text="Akıllı",
                      font=(FONT_FAMILY, 20, "bold"),
                      text_color=ACCENT).pack(side="left", pady=14)
        ctk.CTkLabel(title_box, text="Panel",
                      font=FONT_SUB, text_color=TEXT_PRI
                      ).pack(side="left", padx=(8, 0), pady=(17, 0))
        Pill(bar, "  CANLI ÖZET  ", ACCENT, ACCENT_DK).pack(side="left", padx=10, pady=18)

        ctrl = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl.pack(side="right", padx=16)
        self._status_lbl = ctk.CTkLabel(ctrl, text="",
                                          font=FONT_TINY, text_color=TEXT_SEC)
        self._status_lbl.pack(side="right", padx=12, pady=14)
        ctk.CTkButton(ctrl, text="↻ Yenile", width=110, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      text_color=BG_DARK, font=FONT_SMALL_BOLD,
                      corner_radius=8,
                      command=self._async_refresh).pack(side="right", padx=4, pady=12)

    def _build_body(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color=BG_DARK,
                                                scrollbar_button_color=BORDER)
        self._scroll.pack(fill="both", expand=True)

        self._kpi_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._kpi_row.pack(fill="x", padx=14, pady=(12, 8))

        self._grid_top = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._grid_top.pack(fill="x", padx=14, pady=4)
        self._grid_top.grid_columnconfigure(0, weight=1, uniform="g")
        self._grid_top.grid_columnconfigure(1, weight=1, uniform="g")

        self._grid_mid = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._grid_mid.pack(fill="x", padx=14, pady=4)
        self._grid_mid.grid_columnconfigure(0, weight=1, uniform="g")
        self._grid_mid.grid_columnconfigure(1, weight=1, uniform="g")

        self._grid_bot = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._grid_bot.pack(fill="x", padx=14, pady=4)
        self._grid_bot.grid_columnconfigure(0, weight=1, uniform="g")
        self._grid_bot.grid_columnconfigure(1, weight=1, uniform="g")

        self._anom_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._anom_row.pack(fill="x", padx=14, pady=(4, 14))

    def _async_refresh(self):
        if self._loading:
            return
        self._loading = True
        self._status_lbl.configure(text="Veriler yükleniyor…", text_color=WARNING)

        def _worker():
            try:
                data = asyncio.run(_safe_fetch())
                self.after(0, lambda: self._on_data_loaded(data))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_load_error(str(e)))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_load_error(self, msg: str):
        self._loading = False
        self._status_lbl.configure(text=f"Hata: {msg[:60]}", text_color=DANGER)

    def _on_data_loaded(self, data: dict):
        self._data = data
        self._loading = False
        for w in self._kpi_row.winfo_children(): w.destroy()
        for w in self._grid_top.winfo_children(): w.destroy()
        for w in self._grid_mid.winfo_children(): w.destroy()
        for w in self._grid_bot.winfo_children(): w.destroy()
        for w in self._anom_row.winfo_children(): w.destroy()
        self._render_kpis()
        self._render_inventory_card(self._grid_top, 0)
        self._render_carrier_card(self._grid_top, 1)
        self._render_forex_card(self._grid_mid, 0)
        self._render_portfolio_card(self._grid_mid, 1)
        self._render_ip_card(self._grid_bot, 0)
        self._render_adr_card(self._grid_bot, 1)
        self._render_shipment_card(self._grid_bot, 0, row=1)
        self._render_process_card(self._grid_bot, 1, row=1)
        self._render_hybrid_card(self._anom_row)
        self._render_anomaly_inbox(self._anom_row)
        ts = data.get("fetched_at", "")[:19].replace("T", " ")
        self._status_lbl.configure(
            text=f"Güncellendi: {ts} UTC", text_color=ACCENT)

    def _render_kpis(self):
        kpis = [
            ("MRP Kararları",        str(self._data.get("inv_total", 0)),
             "Wagner-Whitin",       ACCENT),
            ("Forex Hedge",          str(self._data.get("forex_hedge_rec", 0)),
             "Önerilen",             WARNING),
            ("IP İhlal",             str(self._data.get("ip_infringing", 0)),
             "INFRINGING",          DANGER),
            ("Andon 24s",            f"{self._data.get('ship_andon_24h', 0)}"
             f"/{self._data.get('ship_total_24h', 0)}",
             "Tetiklenen / Toplam",  WARNING),
            ("Hybrid AI Maliyet",   f"${self._data.get('hybrid_cost', 0):.4f}",
             f"{self._data.get('hybrid_total', 0)} call",  INFO),
            ("Açık Anomaliler",      str(len(self._data.get("anomalies", []))),
             "Çözülmemiş",           DANGER),
        ]
        for i, (lbl, val, sub, col) in enumerate(kpis):
            self._kpi_row.grid_columnconfigure(i, weight=1, uniform="k")
            c = ctk.CTkFrame(self._kpi_row, fg_color=BG_PANEL,
                              corner_radius=12, border_width=1,
                              border_color=BORDER)
            c.grid(row=0, column=i, padx=4, sticky="ew")
            ctk.CTkLabel(c, text=lbl, font=FONT_TINY,
                          text_color=TEXT_MUT).pack(anchor="w", padx=14, pady=(12, 0))
            ctk.CTkLabel(c, text=val, font=FONT_KPI,
                          text_color=col).pack(anchor="w", padx=14, pady=(2, 0))
            ctk.CTkLabel(c, text=sub, font=FONT_TINY,
                          text_color=TEXT_SEC).pack(anchor="w", padx=14, pady=(0, 12))

    def _card_shell(self, parent, row: int, col: int, title: str, subtitle: str = ""):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(hdr, text=title, font=FONT_HEAD,
                      text_color=TEXT_PRI).pack(side="left")
        if subtitle:
            ctk.CTkLabel(hdr, text=subtitle, font=FONT_TINY,
                          text_color=TEXT_MUT).pack(side="right")
        return card

    def _render_inventory_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "Wagner-Whitin / MRP Kararları",
                                  f"avg cost: {self._data.get('inv_avg_cost', 0):,.0f}")
        rows = self._data.get("inv_decisions", [])
        if not rows:
            ctk.CTkLabel(card, text="Veri yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return
        for r in rows[:6]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["sku"], font=FONT_SMALL_BOLD,
                          text_color=TEXT_PRI, width=80,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=r["method"], font=FONT_TINY,
                          text_color=ACCENT, width=120,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line,
                          text=f"H={r['horizon']}  ord={r['order_count']}",
                          font=FONT_TINY, text_color=TEXT_SEC, width=110,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"{r['total_cost']:,.0f} TL",
                          font=FONT_SMALL_BOLD, text_color=INFO,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_carrier_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "TOPSIS Kargo Seçimi",
                                  f"{len(self._data.get('carriers', []))} kayıt")
        wins = self._data.get("carrier_wins", [])
        if wins:
            bar = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=8)
            bar.pack(fill="x", padx=14, pady=(4, 8))
            ctk.CTkLabel(bar, text="Kazanma Frekansı",
                          font=FONT_TINY, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=12, pady=(8, 2))
            total = sum(n for _, n in wins) or 1
            for carrier, n in sorted(wins, key=lambda x: -x[1])[:5]:
                pct = n / total * 100
                row_f = ctk.CTkFrame(bar, fg_color="transparent")
                row_f.pack(fill="x", padx=12, pady=2)
                ctk.CTkLabel(row_f, text=carrier, font=FONT_TINY,
                              text_color=TEXT_PRI, width=140,
                              anchor="w").pack(side="left")
                ctk.CTkLabel(row_f, text=f"{n}  (%{pct:.0f})",
                              font=FONT_TINY, text_color=ACCENT,
                              anchor="e").pack(side="right")
            ctk.CTkFrame(bar, height=6, fg_color="transparent").pack()

        rows = self._data.get("carriers", [])[:5]
        for r in rows:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=(r.get("order_id") or "—")[:14],
                          font=FONT_TINY, text_color=TEXT_MUT, width=110,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=r["selected"], font=FONT_SMALL_BOLD,
                          text_color=ACCENT,
                          anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(line, text=f"C={r['score']:.3f}",
                          font=FONT_TINY, text_color=INFO,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_forex_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "Forex VaR / Hedge",
                                  "Parametric Brownian")
        rows = self._data.get("forex", [])
        if not rows:
            ctk.CTkLabel(card, text="Pozisyon kaydı yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return
        for r in rows[:6]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["pair"], font=FONT_SMALL_BOLD,
                          text_color=INFO, width=80,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"{r['notional']:,.0f}",
                          font=FONT_TINY, text_color=TEXT_SEC, width=90,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"VaR={r['var']:,.0f}",
                          font=FONT_TINY, text_color=DANGER, width=110,
                          anchor="w").pack(side="left")
            hedge_col = WARNING if r["hedge"] else TEXT_MUT
            hedge_txt = f"H={r['ratio']:.2f}" if r["hedge"] else "—"
            ctk.CTkLabel(line, text=hedge_txt, font=FONT_TINY,
                          text_color=hedge_col,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_portfolio_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "Sharpe-ROT Portföy",
                                  "")
        pf = self._data.get("portfolio")
        if not pf:
            ctk.CTkLabel(card, text="Portföy kararı yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return

        metrics = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=8)
        metrics.pack(fill="x", padx=14, pady=(4, 8))
        items = [
            ("E[R]",     f"%{pf['expected_return']*100:.2f}",   ACCENT),
            ("σ",        f"%{pf['sigma']*100:.2f}",              WARNING),
            ("Method",   pf["method"],                            INFO),
        ]
        for i, (lbl, val, col_c) in enumerate(items):
            metrics.grid_columnconfigure(i, weight=1, uniform="m")
            cell = ctk.CTkFrame(metrics, fg_color="transparent")
            cell.grid(row=0, column=i, padx=8, pady=8, sticky="ew")
            ctk.CTkLabel(cell, text=lbl, font=FONT_TINY,
                          text_color=TEXT_MUT).pack(anchor="w")
            ctk.CTkLabel(cell, text=val, font=FONT_BODY_BOLD,
                          text_color=col_c).pack(anchor="w")

        selected = pf.get("selected", [])
        weights = pf.get("weights", [])
        for sku, w in zip(selected[:6], weights[:6]):
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=sku, font=FONT_SMALL_BOLD,
                          text_color=TEXT_PRI, width=120,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"w=%{w*100:.1f}",
                          font=FONT_TINY, text_color=ACCENT,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_ip_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "IP Shield / pHash",
                                  f"{self._data.get('ip_infringing', 0)} INFRINGING")
        rows = self._data.get("ip_rows", [])
        if not rows:
            ctk.CTkLabel(card, text="İhlal taraması yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return
        for r in rows[:6]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["sku"], font=FONT_SMALL_BOLD,
                          text_color=TEXT_PRI, width=90,
                          anchor="w").pack(side="left")
            dec_col = DECISION_COLORS.get(r["decision"], TEXT_SEC)
            Pill(line, f"  {r['decision']}  ", dec_col, BG_CARD
                  ).pack(side="left", padx=4)
            ctk.CTkLabel(line, text=f"d={r['hamming']}",
                          font=FONT_TINY, text_color=INFO, width=60,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"sim=%{r['similarity']*100:.0f}",
                          font=FONT_TINY, text_color=TEXT_SEC, width=80,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"tfidf=%{r['tfidf']*100:.0f}",
                          font=FONT_TINY, text_color=WARNING,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_adr_card(self, parent, col: int, row: int = 0):
        card = self._card_shell(parent, row, col,
                                  "ADR Vakaları",
                                  f"{len(self._data.get('adr_open', []))} açık")
        actions = self._data.get("adr_by_action", [])
        if actions:
            bar = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=8)
            bar.pack(fill="x", padx=14, pady=(4, 8))
            ctk.CTkLabel(bar, text="Aksiyon Dağılımı (7 gün)",
                          font=FONT_TINY, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=12, pady=(8, 2))
            for act, n, cost in sorted(actions, key=lambda x: -x[1])[:5]:
                clean_act = act.replace("ADRAction.", "")
                row_f = ctk.CTkFrame(bar, fg_color="transparent")
                row_f.pack(fill="x", padx=12, pady=2)
                ctk.CTkLabel(row_f, text=clean_act, font=FONT_TINY,
                              text_color=ADR_COLORS.get(clean_act, TEXT_PRI),
                              width=100, anchor="w").pack(side="left")
                ctk.CTkLabel(row_f, text=f"{n}×",
                              font=FONT_TINY, text_color=TEXT_SEC, width=40,
                              anchor="w").pack(side="left")
                ctk.CTkLabel(row_f, text=f"{cost:,.0f} TL",
                              font=FONT_TINY, text_color=INFO,
                              anchor="e").pack(side="right")
            ctk.CTkFrame(bar, height=6, fg_color="transparent").pack()

        for r in self._data.get("adr_open", [])[:4]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["order_id"][:14], font=FONT_TINY,
                          text_color=TEXT_MUT, width=110,
                          anchor="w").pack(side="left")
            clean_act = (r["action"] or "").replace("ADRAction.", "")
            ctk.CTkLabel(line, text=clean_act, font=FONT_SMALL_BOLD,
                          text_color=ADR_COLORS.get(clean_act, TEXT_PRI),
                          width=90, anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"{r['expected_cost']:,.0f}",
                          font=FONT_TINY, text_color=INFO,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_shipment_card(self, parent, col: int, row: int):
        card = self._card_shell(parent, row, col,
                                  "Shipment Audit / Andon",
                                  "IoT + BOM")
        rows = self._data.get("shipments", [])
        if not rows:
            ctk.CTkLabel(card, text="Audit yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return
        for r in rows[:6]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["order_id"][:12], font=FONT_TINY,
                          text_color=TEXT_MUT, width=100,
                          anchor="w").pack(side="left")
            status_clean = str(r["status"]).replace("ShipmentStatus.", "")
            st_col = STATUS_COLORS.get(status_clean, TEXT_PRI)
            Pill(line, f"  {status_clean}  ", st_col, BG_CARD
                  ).pack(side="left", padx=2)
            ctk.CTkLabel(line, text=f"BOM=%{r['bom_compliance']*100:.0f}",
                          font=FONT_TINY, text_color=TEXT_SEC, width=90,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"T={r['temp_max']:.0f}°",
                          font=FONT_TINY, text_color=TEXT_SEC, width=60,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"sh={r['shock_events']}",
                          font=FONT_TINY,
                          text_color=DANGER if r["shock_events"] > 0 else TEXT_MUT,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_process_card(self, parent, col: int, row: int):
        card = self._card_shell(parent, row, col,
                                  "Process Mining Deviation",
                                  "Damerau-Levenshtein")
        sev = self._data.get("proc_by_severity", [])
        if sev:
            bar = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=8)
            bar.pack(fill="x", padx=14, pady=(4, 8))
            ctk.CTkLabel(bar, text="24s Severity",
                          font=FONT_TINY, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=12, pady=(8, 2))
            for s, n in sorted(sev, key=lambda x: -x[1]):
                clean = str(s).replace("Severity.", "")
                row_f = ctk.CTkFrame(bar, fg_color="transparent")
                row_f.pack(fill="x", padx=12, pady=2)
                ctk.CTkLabel(row_f, text=clean, font=FONT_TINY,
                              text_color=SEVERITY_COLORS.get(clean, TEXT_PRI),
                              width=100, anchor="w").pack(side="left")
                ctk.CTkLabel(row_f, text=str(n), font=FONT_TINY,
                              text_color=TEXT_SEC,
                              anchor="e").pack(side="right")
            ctk.CTkFrame(bar, height=6, fg_color="transparent").pack()

        for r in self._data.get("process", [])[:5]:
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=2)
            ctk.CTkLabel(line, text=r["trace_id"][:14], font=FONT_TINY,
                          text_color=TEXT_MUT, width=110,
                          anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=r["process"], font=FONT_SMALL_BOLD,
                          text_color=TEXT_PRI, width=90,
                          anchor="w").pack(side="left")
            sev_clean = str(r["severity"]).replace("Severity.", "")
            ctk.CTkLabel(line, text=sev_clean, font=FONT_TINY,
                          text_color=SEVERITY_COLORS.get(sev_clean, TEXT_PRI),
                          width=70, anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"d={r['damerau']} %{r['pct']*100:.0f}",
                          font=FONT_TINY, text_color=DANGER,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

    def _render_hybrid_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=1, border_color=BORDER)
        card.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=4)
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(hdr, text="Hybrid AI Telemetry",
                      font=FONT_HEAD, text_color=TEXT_PRI).pack(side="left")
        fb = self._data.get("hybrid_fallback", 0)
        total = self._data.get("hybrid_total", 1) or 1
        ctk.CTkLabel(hdr, text=f"fallback %{fb/total*100:.0f}",
                      font=FONT_TINY, text_color=WARNING).pack(side="right")

        logs = self._data.get("hybrid_logs", [])
        if not logs:
            ctk.CTkLabel(card, text="Inference logu yok",
                          font=FONT_SMALL, text_color=TEXT_MUT
                          ).pack(anchor="w", padx=18, pady=(0, 18))
            return
        by_route: dict = {}
        for r in logs:
            by_route[r["route"]] = by_route.get(r["route"], 0) + 1
        for route, n in by_route.items():
            line = ctk.CTkFrame(card, fg_color="transparent")
            line.pack(fill="x", padx=14, pady=1)
            ctk.CTkLabel(line, text=route, font=FONT_TINY,
                          text_color=ACCENT if "LOCAL" in route else INFO,
                          width=120, anchor="w").pack(side="left")
            ctk.CTkLabel(line, text=f"{n} call", font=FONT_TINY,
                          text_color=TEXT_SEC,
                          anchor="e").pack(side="right")
        ctk.CTkFrame(card, height=6, fg_color="transparent").pack()

        sample = logs[:5]
        if sample:
            avg_lat = sum(r["latency"] for r in sample) / len(sample)
            avg_conf = sum(r["confidence"] for r in sample) / len(sample)
            stat = ctk.CTkFrame(card, fg_color=BG_DARK, corner_radius=8)
            stat.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(stat, text=f"Son 5 ortalama:  lat={avg_lat:.0f}ms  "
                                      f"conf=%{avg_conf*100:.0f}",
                          font=FONT_TINY, text_color=TEXT_SEC
                          ).pack(anchor="w", padx=12, pady=8)
        ctk.CTkFrame(card, height=8, fg_color="transparent").pack()

    def _render_anomaly_inbox(self, parent):
        card = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=14,
                             border_width=2, border_color=DANGER)
        card.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=4)
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(hdr, text="Anomaly Inbox",
                      font=FONT_HEAD, text_color=DANGER).pack(side="left")
        by_sev = self._data.get("anom_by_sev", [])
        for sev, n in by_sev:
            clean = str(sev).replace("Severity.", "")
            Pill(hdr, f"  {clean}: {n}  ",
                  SEVERITY_COLORS.get(clean, TEXT_PRI),
                  BG_CARD).pack(side="right", padx=2)

        anoms = self._data.get("anomalies", [])
        if not anoms:
            ctk.CTkLabel(card, text="Çözülmemiş anomali yok ✓",
                          font=FONT_SMALL, text_color=ACCENT
                          ).pack(anchor="w", padx=18, pady=(8, 18))
            return
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                          scrollbar_button_color=BORDER,
                                          height=200)
        scroll.pack(fill="both", expand=True, padx=10, pady=(4, 12))
        for a in anoms[:10]:
            line = ctk.CTkFrame(scroll, fg_color=BG_DARK, corner_radius=8)
            line.pack(fill="x", pady=2)
            top = ctk.CTkFrame(line, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(6, 0))
            sev_clean = str(a["severity"]).replace("Severity.", "")
            Pill(top, f"  {sev_clean}  ",
                  SEVERITY_COLORS.get(sev_clean, TEXT_PRI),
                  BG_CARD).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(top, text=f"{a['table']}#{a['src_id']}",
                          font=FONT_TINY, text_color=TEXT_MUT
                          ).pack(side="left")
            ctk.CTkLabel(line, text=a["description"][:120],
                          font=FONT_TINY, text_color=TEXT_PRI,
                          wraplength=520, justify="left"
                          ).pack(anchor="w", padx=10, pady=(2, 6))


async def _safe_fetch() -> dict:
    try:
        await init_models()
    except Exception:
        pass
    return await _fetch_all_data()


def open_omnicore_dashboard(parent) -> OmniCoreDashboardWindow:
    return OmniCoreDashboardWindow(parent)


__all__ = ["OmniCoreDashboardWindow", "open_omnicore_dashboard"]
