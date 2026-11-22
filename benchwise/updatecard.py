"""The "new version" card (bottom right) and the panel it opens, both with a blinking amber frame."""

from __future__ import annotations

import webbrowser

import customtkinter as ctk

from recoverytool import i18n
from recoverytool.i18n import t

from . import __version__, update
from .ui import BG, CARD, MUTED, TEXT, button

BLINK = ("#f5b84b", "#ff8a3d", "#c9772c", "#ff8a3d")       # amber -> orange -> dim -> orange
BLINK_MS = 420


class UpdateNotice:
    def __init__(self, shell, info):
        self.shell, self.info = shell, info
        self.card = self.panel = None
        self.step = 0
        self.hidden = False
        self.show_card()
        self.blink()

    # -- card -----------------------------------------------------------------------------------
    def show_card(self):
        if self.hidden:
            return
        c = self.card = ctk.CTkFrame(self.shell, fg_color=CARD, corner_radius=14, border_width=2,
                                     border_color=BLINK[0], cursor="hand2")
        c.place(relx=1.0, rely=1.0, anchor="se", x=-18, y=-18)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(padx=(14, 8), pady=10)
        ctk.CTkLabel(row, text="", image=self.shell.image("refresh", "display", 34)).pack(side="left", padx=(0, 10))
        box = ctk.CTkFrame(row, fg_color="transparent")
        box.pack(side="left")
        ctk.CTkLabel(box, text=t("up_card_title"), font=("Segoe UI Semibold", 14), text_color=BLINK[0],
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(box, text=t("up_card_sub", v=self.info["version"]), font=("Segoe UI", 11), text_color=TEXT,
                     anchor="w").pack(fill="x")
        close = ctk.CTkLabel(row, text="✕", font=("Segoe UI", 12), text_color=MUTED, width=24, cursor="hand2")
        close.pack(side="left", anchor="n", padx=(10, 0))
        for w in (c, row, box) + tuple(row.winfo_children()) + tuple(box.winfo_children()):
            if w is not close:
                w.bind("<Button-1>", lambda e: self.open_panel())
        close.bind("<Button-1>", lambda e: self.hide_card())

    def hide_card(self):
        self.hidden = True
        if self.card is not None:
            self.card.destroy()
            self.card = None

    # -- panel ----------------------------------------------------------------------------------
    def open_panel(self):
        if self.panel is not None:
            return
        info = self.info
        p = self.panel = ctk.CTkFrame(self.shell, fg_color=BG, corner_radius=16, border_width=3,
                                      border_color=BLINK[0], width=600, height=470)
        p.place(relx=0.5, rely=0.5, anchor="center")
        p.pack_propagate(False)
        head = ctk.CTkFrame(p, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(head, text="", image=self.shell.image("refresh", "display", 52)).pack(side="left", padx=(0, 14))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(titles, text=t("up_panel_title", v=info["version"]), font=("Segoe UI Semibold", 22),
                     text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(titles, text=t("up_panel_sub", cur=update.current_version(), date=info["date"] or "–"), font=("Segoe UI", 12),
                     text_color=MUTED, anchor="w").pack(fill="x")
        ctk.CTkLabel(p, text=t("up_recommend"), font=("Segoe UI", 13), text_color=BLINK[0], anchor="w",
                     justify="left", wraplength=540).pack(fill="x", padx=24, pady=(6, 8))
        ctk.CTkLabel(p, text=t("up_notes"), font=("Segoe UI Semibold", 12), text_color=TEXT, anchor="w").pack(
            fill="x", padx=24)
        notes = ctk.CTkTextbox(p, fg_color=CARD, text_color=TEXT, font=("Segoe UI", 12), corner_radius=10,
                               wrap="word", border_width=0)
        notes.pack(fill="both", expand=True, padx=24, pady=(4, 12))
        box = notes._textbox
        box.tag_config("head", font=("Segoe UI Semibold", 13), foreground=BLINK[0], spacing1=8, spacing3=2)
        box.tag_config("item", lmargin1=8, lmargin2=24, spacing1=1)
        box.tag_config("text", spacing1=2)
        rows = update.note_lines(update.notes_for(info["notes"], i18n.language()))
        for kind, text in rows or [("text", t("up_no_notes"))]:
            box.insert("end", ("•  " + text if kind == "item" else text) + "\n", kind)
        notes.configure(state="disabled")
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 20))
        button(row, t("up_download"), self.download, 190, primary=True).pack(side="left")
        button(row, t("up_page"), lambda: webbrowser.open(info["page"]), 130).pack(side="left", padx=(8, 0))
        button(row, t("up_later"), self.close_panel, 110).pack(side="right")
        self.raise_()

    def download(self):
        webbrowser.open(self.info["exe"] or self.info["page"])
        self.close_panel()

    def close_panel(self):
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None

    # -- life -----------------------------------------------------------------------------------
    def blink(self):
        self.step = (self.step + 1) % len(BLINK)
        color = BLINK[self.step]
        for w in (self.card, self.panel):
            if w is not None and w.winfo_exists():
                w.configure(border_color=color)
        if self.shell.winfo_exists():
            self.shell.after(BLINK_MS, self.blink)

    def raise_(self):
        """Keep the card and the panel above pages and tool views (they are raised on navigation)."""
        for w in (self.card, self.panel):
            if w is not None and w.winfo_exists():
                w.lift()

    def rebuild(self):
        """After a language switch the window was rebuilt: draw again in the new language."""
        had_panel = self.panel is not None
        self.card = self.panel = None
        self.show_card()
        if had_panel:
            self.open_panel()
