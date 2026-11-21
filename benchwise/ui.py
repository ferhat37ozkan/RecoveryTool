"""Colours and small building blocks shared by the Benchwise window and its tools."""

from __future__ import annotations

import customtkinter as ctk

BG, CARD, CARD_HOVER, BORDER = "#0f1420", "#182033", "#1d2740", "#263149"
TEXT, MUTED, ACCENT, ACCENT_HOVER = "#e8ecf4", "#8b96ad", "#2f7cf6", "#2467d3"
GOOD, WARN, BAD = "#3ecf8e", "#f5b84b", "#f26d6d"
LEVEL = {"good": GOOD, "warning": WARN, "bad": BAD, "unknown": MUTED, "info": ACCENT}


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
