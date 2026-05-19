# -*- coding: utf-8 -*-
import customtkinter as ctk


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _interp(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        r1 + (r2 - r1) * t,
        g1 + (g2 - g1) * t,
        b1 + (b2 - b1) * t)


def fade_color(widget, attr: str, from_color: str, to_color: str,
                  duration_ms: int = 220, steps: int = 11):
    if steps < 2:
        steps = 2
    delay = max(8, duration_ms // steps)

    def _tick(i: int):
        if i > steps:
            return
        try:
            t = i / steps
            kw = {attr: _interp(from_color, to_color, t)}
            widget.configure(**kw)
        except Exception:
            return
        widget.after(delay, lambda: _tick(i + 1))
    _tick(0)


def hover_lift(widget, normal_border: str, hover_border: str,
                 duration_ms: int = 180):
    def _on_enter(_e):
        fade_color(widget, "border_color",
                    normal_border, hover_border, duration_ms)
    def _on_leave(_e):
        fade_color(widget, "border_color",
                    hover_border, normal_border, duration_ms)
    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")


def hover_glow_bg(widget, normal_bg: str, hover_bg: str,
                    duration_ms: int = 160):
    def _on_enter(_e):
        fade_color(widget, "fg_color", normal_bg, hover_bg, duration_ms)
    def _on_leave(_e):
        fade_color(widget, "fg_color", hover_bg, normal_bg, duration_ms)
    widget.bind("<Enter>", _on_enter, add="+")
    widget.bind("<Leave>", _on_leave, add="+")


def count_up(label, start: float, end: float,
                duration_ms: int = 600, steps: int = 24,
                fmt: str = "{:,.0f}"):
    if steps < 2:
        steps = 2
    delay = max(8, duration_ms // steps)

    def _tick(i: int):
        if i > steps:
            try:
                label.configure(text=fmt.format(end))
            except Exception:
                pass
            return
        try:
            t = i / steps
            t_ease = 1 - (1 - t) ** 3
            val = start + (end - start) * t_ease
            label.configure(text=fmt.format(val))
        except Exception:
            return
        label.after(delay, lambda: _tick(i + 1))
    _tick(0)


def slide_in(widget, side: str = "right",
                duration_ms: int = 280, steps: int = 14, distance: int = 30):
    if steps < 2:
        steps = 2
    delay = max(8, duration_ms // steps)
    original_padx = None
    try:
        info = widget.pack_info()
        original_padx = info.get("padx", 0)
    except Exception:
        return

    def _tick(i: int):
        if i > steps:
            try:
                widget.pack_configure(padx=original_padx)
            except Exception:
                pass
            return
        try:
            t = i / steps
            t_ease = 1 - (1 - t) ** 3
            offset = int(distance * (1 - t_ease))
            if side == "right":
                widget.pack_configure(padx=(0, offset))
            else:
                widget.pack_configure(padx=(offset, 0))
        except Exception:
            return
        widget.after(delay, lambda: _tick(i + 1))
    _tick(0)


__all__ = [
    "fade_color", "hover_lift", "hover_glow_bg",
    "count_up", "slide_in",
]
