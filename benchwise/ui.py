"""Colours and small building blocks shared by the Benchwise window and its tools."""

from __future__ import annotations

import customtkinter as ctk

BG, CARD, CARD_HOVER, BORDER = "#0f1420", "#182033", "#1d2740", "#263149"
TEXT, MUTED, ACCENT, ACCENT_HOVER = "#e8ecf4", "#8b96ad", "#2f7cf6", "#2467d3"
GOOD, WARN, BAD = "#3ecf8e", "#f5b84b", "#f26d6d"
LEVEL = {"good": GOOD, "warning": WARN, "bad": BAD, "unknown": MUTED, "info": ACCENT}


def _fast_scrollbars():
    """customtkinter's scrollbar calls update_idletasks() at the end of every redraw, which forces a layout
    pass of the whole window, and it redraws on every set() even when nothing moved.  A page with a few
    tables then spends most of its build time in those passes, and a window being resized redraws in
    steps.  Tk draws the canvas on its own at the next idle moment, so the forced pass is dropped, and an
    unchanged position is not drawn again."""
    cls = ctk.CTkScrollbar
    if getattr(cls, "_benchwise_fast", False):
        return
    draw, set_ = cls._draw, cls.set

    def _draw(self, no_color_updates=False):
        canvas = self._canvas
        canvas.update_idletasks = lambda: None          # instance attribute: hides the method for this call
        try:
            return draw(self, no_color_updates)
        finally:
            del canvas.update_idletasks

    def set(self, start_value, end_value):
        value = (float(start_value), float(end_value))
        if getattr(self, "_benchwise_last", None) == value:
            return
        self._benchwise_last = value
        set_(self, start_value, end_value)

    cls._draw, cls.set, cls._benchwise_fast = _draw, set, True


_fast_scrollbars()


# -- skeletons: grey "ghost" bars where content will appear --------------------------------------
# A light wave runs across them from left to right, as on web pages: every bar takes its shade from a
# sine wave of time and of its x position on screen, redrawn ~30 times a second.  The bars are plain Tk
# frames, so a frame costs one colour change per bar, and only for bars whose shade actually moved.
GHOST_BASE, GHOST_LIGHT = (0x1f, 0x27, 0x3a), (0x33, 0x40, 0x5e)
SHIMMER_PERIOD = 1.5          # seconds for one wave to pass a point
SHIMMER_WAVE = 700            # wave length on screen, in pixels
_STEPS = 24
_SHADES = ["#%02x%02x%02x" % tuple(round(a + (b - a) * k / (_STEPS - 1)) for a, b in zip(GHOST_BASE, GHOST_LIGHT))
           for k in range(_STEPS)]
_ghosts = {}                   # bar -> [x on screen or None, current shade index]
_pulse = {"on": False, "xs_at": 0.0}


def ghost(parent, width, height=10, bg=CARD, **pack):
    """A ghost bar ``width`` x ``height`` (unscaled px) packed into ``parent``.  Plain Tk frames: cheap
    to create and to recolour, so a page full of them costs nothing.  The shimmer runs on all of them."""
    import tkinter as tk
    k = ctk.ScalingTracker.get_widget_scaling(parent)
    bar = tk.Frame(parent, width=round(width * k), height=round(height * k), bg=_SHADES[0], bd=0,
                   highlightthickness=0)
    pady = pack.pop("pady", 3)
    bar.pack(anchor=pack.pop("anchor", "w"), pady=_scaled(pady, k), padx=_scaled(pack.pop("padx", 0), k), **pack)
    _ghosts[bar] = [None, 0]
    if not _pulse["on"]:
        _pulse["on"] = True
        bar.after(33, _tick, bar.winfo_toplevel())
    return bar


def _scaled(v, k):
    return tuple(round(x * k) for x in v) if isinstance(v, tuple) else round(v * k)


def _tick(top):
    import math
    import time
    for bar in [b for b in _ghosts if not b.winfo_exists()]:
        del _ghosts[bar]
    if not _ghosts or not top.winfo_exists():
        _pulse["on"] = False
        _ghosts.clear()
        return
    now = time.monotonic()
    if now - _pulse["xs_at"] > 0.5:                 # positions change only on layout / scroll
        _pulse["xs_at"] = now
        left = top.winfo_rootx()
        for bar, st in _ghosts.items():
            st[0] = bar.winfo_rootx() - left if bar.winfo_ismapped() else None
    for bar, st in _ghosts.items():
        if st[0] is None:
            continue
        phase = now / SHIMMER_PERIOD - st[0] / SHIMMER_WAVE
        level = (1 - math.cos(2 * math.pi * phase)) / 2           # 0..1, smooth
        idx = round(level ** 2 * (_STEPS - 1))                    # squared: a narrower, brighter crest
        if idx != st[1]:
            st[1] = idx
            bar.configure(bg=_SHADES[idx])
    top.after(33, _tick, top)


def ghost_card(parent, rows=4, title=True, **pack):
    """A card-shaped skeleton: a title bar and ``rows`` label / value bars."""
    import tkinter as tk
    c = card(parent)
    c.pack(fill="x", **({"pady": (0, 8)} | pack))
    k = ctk.ScalingTracker.get_widget_scaling(parent)
    inner = tk.Frame(c, bg=CARD, bd=0, highlightthickness=0)
    inner.pack(fill="x", padx=round(16 * k), pady=round(12 * k))
    if title:
        ghost(inner, 150, 14, pady=(0, 10))
    for i in range(rows):
        row = tk.Frame(inner, bg=CARD, bd=0, highlightthickness=0)
        row.pack(fill="x")
        ghost(row, 90 + (i * 23) % 40, side="left", padx=(0, 24))
        ghost(row, 120 + (i * 47) % 110, side="left")
    return c


def card(parent, title=None, **kw):
    frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER, **kw)
    if title:
        ctk.CTkLabel(frame, text=title, font=("Segoe UI Semibold", 14), text_color=TEXT, anchor="w").pack(
            fill="x", padx=18, pady=(12, 6))
    return frame


def button(parent, text, command, width=110, primary=False, **kw):
    if primary:
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=34, fg_color=ACCENT,
                             hover_color=ACCENT_HOVER, font=("Segoe UI Semibold", 12), **kw)
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=30, fg_color=CARD,
                         hover_color=BORDER, border_width=1, border_color=BORDER, text_color=TEXT, **kw)


def tool_header(parent, title, subtitle=None):
    """Title row of a tool screen; returns the frame so the tool can add buttons on the right."""
    head = ctk.CTkFrame(parent, fg_color=BG)
    head.pack(fill="x")
    ctk.CTkLabel(head, text=title, font=("Segoe UI Semibold", 22), text_color=TEXT).pack(side="left")
    if subtitle:
        ctk.CTkLabel(parent, text=subtitle, font=("Segoe UI", 12), text_color=MUTED, anchor="w").pack(
            fill="x", pady=(0, 10))
    return head
