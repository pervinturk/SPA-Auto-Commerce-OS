# -*- coding: utf-8 -*-
import customtkinter as ctk
import tkinter as tk
from ui.theme import *


class Tooltip:
    def __init__(self, widget, text_fn):
        self.widget = widget
        self.text_fn = text_fn if callable(text_fn) else (lambda: text_fn)
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(bg=BORDER)
        f = tk.Frame(self.tip, bg=BG_CARD, bd=0)
        f.pack(padx=1, pady=1)
        tk.Label(f, text=self.text_fn(), font=FONT_SMALL,
                 fg=TEXT_PRI, bg=BG_CARD, padx=10, pady=6,
                 wraplength=360, justify="left").pack()
        self.tip.geometry(f"+{x}+{y}")

    def _hide(self, _):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class KPICard(ctk.CTkFrame):
    def __init__(self, parent, label, value, delta="", color=None, on_click=None, icon=None):
        super().__init__(parent, fg_color=BG_PANEL, corner_radius=12,
                         border_width=1, border_color=BORDER, cursor="hand2" if on_click else "")
        self.on_click = on_click
        color = color or ACCENT

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 4))
        ctk.CTkLabel(top, text=label, font=FONT_SMALL_BOLD,
                     text_color=TEXT_SEC).pack(side="left")
        if icon:
            ctk.CTkLabel(top, text=icon, font=("Segoe UI Symbol", 18),
                         text_color=color).pack(side="right")
        self._val_lbl = ctk.CTkLabel(self, text=value, font=FONT_KPI,
                                      text_color=TEXT_PRI)
        self._val_lbl.pack(anchor="w", padx=18)
        self._delta_lbl = ctk.CTkLabel(self, text=delta, font=FONT_SMALL,
                                        text_color=color)
        self._delta_lbl.pack(anchor="w", padx=18, pady=(2, 16))

        if on_click:
            try:
                from ui.animations import fade_color
            except Exception:
                fade_color = None
            for w in [self, top, self._val_lbl, self._delta_lbl]:
                w.bind("<Button-1>", lambda e: on_click(), add="+")
                if fade_color:
                    w.bind("<Enter>",
                           lambda e, c=color: fade_color(self, "border_color",
                                                            BORDER, c, 180),
                           add="+")
                    w.bind("<Leave>",
                           lambda e, c=color: fade_color(self, "border_color",
                                                            c, BORDER, 180),
                           add="+")
                else:
                    w.bind("<Enter>", lambda e: self.configure(border_color=color), add="+")
                    w.bind("<Leave>", lambda e: self.configure(border_color=BORDER), add="+")

    def update_value(self, value, delta=None):
        self._val_lbl.configure(text=value)
        if delta is not None:
            self._delta_lbl.configure(text=delta)


class Pill(ctk.CTkLabel):
    def __init__(self, parent, text, color, bg=None):
        super().__init__(parent, text=text, font=FONT_SMALL_BOLD,
                         text_color=color, fg_color=bg or BG_CARD,
                         corner_radius=8, padx=10, pady=3)


class SortableTable(ctk.CTkFrame):
    """Excel-vari uniform sütun genişlikleriyle sıralanabilir / filtrelenebilir tablo.

    columns:        sütun başlıkları listesi
    rows:           [{"cells": [v1, v2, ...], "data": <opsiyonel>}]
    column_widths:  her sütun için sabit pixel genişliği (None=eşit dağıt)
    status_col:     durum hücresinin index'i (renkli gösterilecek)
    status_colors:  {durum_metni: renk}
    on_row_click:   callable(data) — satıra tıklayınca tetiklenir
    """

    def __init__(self, parent, columns, rows, on_row_click=None,
                 column_widths=None, status_colors=None, status_col=None,
                 export_filename=None):
        super().__init__(parent, fg_color="transparent")
        self.columns = columns
        self.full_rows = rows
        self.on_row_click = on_row_click
        n = len(columns)
        if not column_widths or len(column_widths) != n:
            column_widths = [140] * n
        self.column_widths = [int(w) if w else 140 for w in column_widths]
        self.status_colors = status_colors or {}
        self.status_col = status_col
        self.export_filename = export_filename
        self._sort_key = None
        self._sort_asc = True
        self._filter_text = ""
        self._build_filter()
        self._build_header()
        self._body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             scrollbar_button_color=BORDER, height=480)
        self._body.pack(fill="both", expand=True)
        self._render()

    def _build_filter(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 8))
        self._filter_entry = ctk.CTkEntry(bar, fg_color=BG_PANEL, border_color=BORDER,
                                           text_color=TEXT_PRI,
                                           placeholder_text="Tüm sütunlarda ara…",
                                           height=34, font=FONT_SMALL)
        self._filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._filter_entry.bind("<KeyRelease>", self._on_filter)
        if self.export_filename:
            ctk.CTkButton(bar, text="↓ CSV", width=86, height=34,
                          fg_color=BG_CARD, hover_color=BG_HOVER,
                          text_color=TEXT_PRI, font=FONT_SMALL_BOLD,
                          corner_radius=8,
                          command=self._export_csv).pack(side="right", padx=(0, 4))
        self._count_lbl = ctk.CTkLabel(bar, text="", font=FONT_SMALL_BOLD,
                                        text_color=TEXT_SEC, width=80, anchor="e")
        self._count_lbl.pack(side="right")

    def _build_header(self):
        self._hdr = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=8, height=42)
        self._hdr.pack(fill="x", pady=(0, 4))
        self._hdr.pack_propagate(False)
        for i, col in enumerate(self.columns):
            cell = ctk.CTkFrame(self._hdr, fg_color="transparent",
                                 width=self.column_widths[i])
            cell.pack(side="left", padx=0, fill="y")
            cell.pack_propagate(False)
            btn = ctk.CTkButton(cell, text=col + "  ⇅", font=FONT_SMALL_BOLD,
                                fg_color="transparent", hover_color=BG_HOVER,
                                text_color=TEXT_SEC, anchor="w", height=38,
                                corner_radius=4,
                                command=lambda c=col, idx=i: self._toggle_sort(c, idx))
            btn.pack(fill="both", expand=True, padx=2, pady=2)

    def _on_filter(self, _):
        self._filter_text = self._filter_entry.get().lower()
        self._render()

    def _toggle_sort(self, col, idx):
        if self._sort_key == idx:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_key = idx
            self._sort_asc = True
        # Update header arrows
        for i, btn_frame in enumerate(self._hdr.winfo_children()):
            for btn in btn_frame.winfo_children():
                base = self.columns[i]
                if i == self._sort_key:
                    arrow = "  ▲" if self._sort_asc else "  ▼"
                else:
                    arrow = "  ⇅"
                btn.configure(text=base + arrow,
                              text_color=ACCENT if i == self._sort_key else TEXT_SEC)
        self._render()

    def _render(self):
        for w in self._body.winfo_children():
            w.destroy()

        rows = self.full_rows
        if self._filter_text:
            rows = [r for r in rows
                    if any(self._filter_text in str(v).lower() for v in r["cells"])]

        if self._sort_key is not None:
            def keyf(r):
                v = r["cells"][self._sort_key]
                if isinstance(v, (int, float)):
                    return v
                s = str(v)
                num = "".join(ch for ch in s if ch.isdigit() or ch in ".,-")
                try:
                    return float(num.replace(",", "."))
                except Exception:
                    return s.lower()
            rows = sorted(rows, key=keyf, reverse=not self._sort_asc)

        self._count_lbl.configure(text=f"{len(rows)} kayıt")

        for r in rows:
            rf = ctk.CTkFrame(self._body, fg_color=BG_PANEL,
                               corner_radius=6, height=40)
            rf.pack(fill="x", pady=2)
            rf.pack_propagate(False)
            for i, val in enumerate(r["cells"]):
                w = self.column_widths[i]
                col = TEXT_PRI
                if i == self.status_col:
                    col = self.status_colors.get(val, TEXT_PRI)
                cell = ctk.CTkFrame(rf, fg_color="transparent", width=w)
                cell.pack(side="left", fill="y")
                cell.pack_propagate(False)
                ctk.CTkLabel(cell, text=self._truncate(str(val), w),
                             font=FONT_SMALL, text_color=col, anchor="w",
                             justify="left").pack(side="left",
                                                    padx=10, pady=10, fill="both")
            if self.on_row_click:
                data = r.get("data")
                for w in [rf] + self._walk(rf):
                    try:
                        w.configure(cursor="hand2")
                    except Exception:
                        pass
                    w.bind("<Button-1>", lambda e, d=data: self.on_row_click(d), add="+")
                    w.bind("<Enter>", lambda e, f=rf: f.configure(fg_color=BG_HOVER), add="+")
                    w.bind("<Leave>", lambda e, f=rf: f.configure(fg_color=BG_PANEL), add="+")

    def _walk(self, parent):
        out = []
        for ch in parent.winfo_children():
            out.append(ch)
            out.extend(self._walk(ch))
        return out

    @staticmethod
    def _truncate(text: str, width_px: int) -> str:
        max_chars = max(8, width_px // 8)
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1] + "…"

    def _export_csv(self):
        from tkinter import filedialog
        import csv
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=self.export_filename or "veri.csv",
            filetypes=[("CSV (UTF-8 BOM)", "*.csv")])
        if not path:
            return
        rows = self.full_rows
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            wr = csv.writer(fh, delimiter=";")
            wr.writerow(self.columns)
            for r in rows:
                wr.writerow(r["cells"])

    def set_rows(self, rows):
        self.full_rows = rows
        self._render()


class NotificationBell(ctk.CTkButton):
    def __init__(self, parent, on_open):
        super().__init__(parent, text="🔔 0", width=64, height=34,
                         fg_color=BG_PANEL, hover_color=BG_HOVER,
                         text_color=TEXT_PRI, font=FONT_SMALL_BOLD,
                         corner_radius=8, command=on_open)
        self.count = 0

    def set_count(self, n):
        self.count = n
        color = DANGER if n > 0 else TEXT_PRI
        self.configure(text=f"🔔 {n}", text_color=color)


class ChartHover:
    """Matplotlib eksenine bağlanan canlı hover tooltip'i.
    Bar / Line / Scatter / Patches üzerinden geçince Tkinter Toplevel pencere
    açıp x,y veya custom metin gösterir.

    Kullanım:
        fig, ax = plt.subplots(...)
        ax.bar(...)
        canvas = FigureCanvasTkAgg(fig, parent)
        ChartHover(canvas, ax, fmt=lambda x, y: f"x={x:.0f}, y={y:.0f} TL")
    """

    def __init__(self, canvas, ax, fmt=None, x_labels=None, pie_data=None):
        self.canvas = canvas
        self.ax = ax
        self.fmt = fmt or (lambda x, y: f"{x:.1f}, {y:.1f}")
        self.x_labels = x_labels
        self.pie_data = pie_data  # [(label, value), ...] — wedge index ile eşler
        self._tip = None
        self._tip_label = None
        canvas.mpl_connect("motion_notify_event", self._on_motion)
        canvas.mpl_connect("figure_leave_event", self._hide)
        canvas.get_tk_widget().bind("<Leave>", lambda e: self._hide(None), add="+")

    def _on_motion(self, event):
        if event.inaxes != self.ax:
            self._hide(None)
            return
        text = None

        # Pie wedges (index ile pie_data eşle)
        if self.pie_data:
            for i, patch in enumerate(self.ax.patches):
                try:
                    if patch.contains(event)[0] and i < len(self.pie_data):
                        lbl, val = self.pie_data[i]
                        text = self.fmt(lbl, val)
                        break
                except Exception:
                    continue
            if text:
                self._show(text)
                return

        if event.xdata is None or event.ydata is None:
            self._hide(None)
            return
        # Bar/Rectangle patches
        for patch in self.ax.patches:
            try:
                if patch.contains(event)[0]:
                    x = patch.get_x() + patch.get_width() / 2
                    y = patch.get_height()
                    if self.x_labels and 0 <= int(round(x)) < len(self.x_labels):
                        x_disp = self.x_labels[int(round(x))]
                    else:
                        x_disp = x
                    text = self.fmt(x_disp, y)
                    break
            except (AttributeError, TypeError):
                continue
        # Line marker hit-test (for line plots)
        if text is None and self.ax.lines:
            try:
                xlim = self.ax.get_xlim()
                ylim = self.ax.get_ylim()
                x_span = max(1e-9, xlim[1] - xlim[0])
                y_span = max(1e-9, ylim[1] - ylim[0])
                best_dist = float("inf")
                best_x = None
                best_y = None
                best_label = None
                for line in self.ax.lines:
                    xs = line.get_xdata()
                    ys = line.get_ydata()
                    line_label = line.get_label()
                    for xv, yv in zip(xs, ys):
                        try:
                            xv_f = float(xv)
                            yv_f = float(yv)
                        except (TypeError, ValueError):
                            continue
                        dx = (xv_f - event.xdata) / x_span
                        dy = (yv_f - event.ydata) / y_span
                        d = (dx * dx + dy * dy) ** 0.5
                        if d < best_dist:
                            best_dist = d
                            best_x = xv_f
                            best_y = yv_f
                            best_label = line_label
                if best_dist < 0.04 and best_x is not None:
                    if (self.x_labels and
                            0 <= int(round(best_x)) < len(self.x_labels)):
                        x_disp = self.x_labels[int(round(best_x))]
                    else:
                        x_disp = best_x
                    series = best_label or ""
                    if series and not series.startswith("_"):
                        text = f"{series}  ·  {self.fmt(x_disp, best_y)}"
                    else:
                        text = self.fmt(x_disp, best_y)
            except Exception:
                pass
        if text is None:
            for line in self.ax.lines:
                xs, ys = line.get_xdata(), line.get_ydata()
                if not len(xs):
                    continue
                # find nearest x
                try:
                    import numpy as np
                    idx = int(np.argmin([abs(float(x) - event.xdata) for x in xs]))
                    if abs(float(xs[idx]) - event.xdata) < 0.6:
                        x_disp = (self.x_labels[idx]
                                  if self.x_labels and idx < len(self.x_labels)
                                  else xs[idx])
                        text = self.fmt(x_disp, float(ys[idx]))
                        break
                except Exception:
                    continue
        if text is None:
            self._hide(None)
            return
        self._show(text)

    def _show(self, text):
        widget = self.canvas.get_tk_widget()
        x = widget.winfo_pointerx() + 12
        y = widget.winfo_pointery() + 12
        if self._tip is None:
            self._tip = tk.Toplevel(widget)
            self._tip.wm_overrideredirect(True)
            self._tip.attributes("-topmost", True)
            self._tip.configure(bg=BORDER)
            f = tk.Frame(self._tip, bg=BG_CARD, bd=0)
            f.pack(padx=1, pady=1)
            self._tip_label = tk.Label(f, text=text, font=FONT_SMALL,
                                          fg=TEXT_PRI, bg=BG_CARD,
                                          padx=10, pady=6, justify="left")
            self._tip_label.pack()
        else:
            self._tip_label.config(text=text)
        self._tip.geometry(f"+{x}+{y}")

    def _hide(self, _):
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None
            self._tip_label = None
