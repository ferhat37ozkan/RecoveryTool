"""The Benchwise window: big category cards, then tool cards, then the tool itself.

    Home  ->  Disk  ->  File Recovery

A top bar shows where you are (each step can be clicked to go back), whether Benchwise runs as
administrator, and the language button.  Tools that were opened stay alive while you look
around, so a scan keeps running when you go back to the home page.
"""

from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from recoverytool import i18n
from recoverytool.i18n import t

from . import APP_NAME, DOMAIN, NAME, __version__, art, elevate, strings  # noqa: F401  (strings fills the table)
from .registry import CATEGORIES, find_tool

from .ui import ACCENT, BG, BORDER, CARD, CARD_HOVER, GOOD, MUTED, TEXT, WARN
CARD_W, CARD_H = 250, 210            # category cards
TOOL_W, TOOL_H = 250, 190            # tool cards
GAP = 16


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)


class Card(ctk.CTkFrame):
    """A clickable card: big icon, name, one line of description, optional badges."""

    def __init__(self, master, image, title, desc, command, badges=(), width=CARD_W, height=CARD_H, dim=False):
        super().__init__(master, width=width, height=height, fg_color=CARD, corner_radius=14,
                         border_width=1, border_color=BORDER)
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.command = command
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(18, 0))
        ctk.CTkLabel(top, text="", image=image).pack(side="left")
        for text, color, icon in badges:
            b = ctk.CTkLabel(top, text=(" " + text if text else "") if icon else text, image=icon, compound="left",
                             font=("Segoe UI Semibold", 10), text_color=color, fg_color=BG, corner_radius=8,
                             height=22, padx=8)
            b.pack(side="right", anchor="n", padx=(6, 0))
        ctk.CTkLabel(self, text=title, font=("Segoe UI Semibold", 16), text_color=MUTED if dim else TEXT,
                     anchor="w").pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(self, text=desc, font=("Segoe UI", 11), text_color=MUTED, anchor="nw", justify="left",
                     wraplength=width - 36).pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self._bind_all(self)

    def _bind_all(self, w):
        w.bind("<Enter>", lambda e: self.configure(fg_color=CARD_HOVER, border_color=ACCENT), add="+")
        w.bind("<Leave>", self._leave, add="+")
        w.bind("<Button-1>", lambda e: self.command(), add="+")
        try:
            w.configure(cursor="hand2")
        except (tk.TclError, ValueError):
            pass
        for ch in w.winfo_children():
            self._bind_all(ch)

    def _leave(self, e):
        x, y = self.winfo_pointerxy()
        inside = self.winfo_containing(x, y)
        while inside is not None and inside is not self:
            inside = inside.master
        if inside is None:
            self.configure(fg_color=CARD, border_color=BORDER)


class CardGrid(ctk.CTkScrollableFrame):
    """Cards in as many columns as the width allows."""

    def __init__(self, master, card_width):
        super().__init__(master, fg_color=BG, scrollbar_button_color=BORDER, scrollbar_button_hover_color="#33405c")
        self.card_width, self.cards, self.cols = card_width, [], 0
        self._parent_canvas.bind("<Configure>", lambda e: self.layout(), add="+")

    def add(self, card):
        self.cards.append(card)

    def layout(self):
        cols = max(1, (self._parent_canvas.winfo_width() - 8) // (self.card_width + GAP))
        if cols == self.cols:
            return
        self.cols = cols
        for i, c in enumerate(self.cards):
            c.grid(row=i // cols, column=i % cols, padx=(0, GAP), pady=(0, GAP), sticky="nw")


class Shell(ctk.CTk):
    def __init__(self, open_tool=None):
        super().__init__(fg_color=BG)
        self.title("%s  v%s" % (APP_NAME, __version__))
        self.minsize(1000, 700)
        self.center(1180, 800)
        try:
            self.iconbitmap(resource("icon.ico"))
        except tk.TclError:
            pass
        self.admin = elevate.is_admin()
        self.views = {}             # tool id -> its frame, kept while the window is open
        self.page = ("home",)       # ("home",) | ("category", cat) | ("tool", cat, tool)
        self.images = {}
        self.notice = None          # the "new version" card, once the check found one
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.build()
        self.after(2500, self.check_update)
        cat, tool = find_tool(open_tool) if open_tool else (None, None)
        if os.environ.get("RECOVERYTOOL_SELFTEST") or os.environ.get("RECOVERYTOOL_UITEST"):
            cat, tool = find_tool("disk.recovery")
        if tool is not None:
            self.after(10, lambda: self.open_tool(cat, tool))

    def center(self, width, height):
        """Open in the middle of the screen, never larger than it.

        customtkinter scales every geometry value by the display scaling, so the sums are done
        in its unscaled units."""
        scale = self._get_window_scaling()
        sw, sh = self.winfo_screenwidth() / scale, self.winfo_screenheight() / scale
        width, height = min(width, int(sw) - 40), min(height, int(sh) - 80)
        x, y = max(int((sw - width) / 2), 0), max(int((sh - height) / 2) - 20, 0)   # a little above centre: taskbar
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    # -- images ---------------------------------------------------------------------------------
    def image(self, name, color, size, enabled=True):
        key = (name, color, size, enabled)
        if key not in self.images:
            pil = art.tile(name, color, size * 2, enabled)            # twice the size: sharp on scaled displays
            self.images[key] = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
        return self.images[key]

    def shield(self, color=WARN):
        key = ("shield-badge", color)
        if key not in self.images:
            rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            pil = art.badge("shield", 28, rgb)
            self.images[key] = ctk.CTkImage(light_image=pil, dark_image=pil, size=(14, 14))
        return self.images[key]

    # -- frame ----------------------------------------------------------------------------------
    def build(self):
        for w in self.winfo_children():
            if w not in self.views.values():
                w.destroy()
        bar = ctk.CTkFrame(self, fg_color=BG)
        bar.pack(fill="x", padx=22, pady=(14, 6))
        brand = ctk.CTkLabel(bar, text="", image=self.image("windows", "disk", 30), cursor="hand2")
        brand.pack(side="left")
        brand.bind("<Button-1>", lambda e: self.go_home())
        name = ctk.CTkLabel(bar, text=NAME, font=("Segoe UI Semibold", 22), text_color=TEXT, cursor="hand2")
        name.pack(side="left", padx=(10, 0))
        name.bind("<Button-1>", lambda e: self.go_home())
        ctk.CTkLabel(bar, text="@" + DOMAIN, font=("Segoe UI", 13), text_color=MUTED).pack(side="left", pady=(7, 0))
        self.crumbs = ctk.CTkFrame(bar, fg_color=BG, height=30)
        self.crumbs.pack(side="left", padx=(14, 0), pady=(4, 0))
        top = dict(height=28, fg_color=CARD, hover_color=BORDER, border_width=1, border_color=BORDER, text_color=TEXT)
        ctk.CTkButton(bar, text=t("lang"), width=84, command=self.switch_language, **top).pack(side="right")
        mode = ctk.CTkLabel(bar, text=" " + t("bw_admin_mode" if self.admin else "bw_user_mode"),
                            image=self.shield(GOOD if self.admin else MUTED), compound="left",
                            font=("Segoe UI Semibold", 11), text_color=GOOD if self.admin else MUTED,
                            fg_color=CARD, corner_radius=8, height=28, padx=10)
        mode.pack(side="right", padx=(0, 8))
        # Every page and tool view sits in the same cell of the body and stays there; switching only
        # raises one above the others.  Nothing is unmapped and re-laid out, so there is no flicker.
        self.body = ctk.CTkFrame(self, fg_color=BG)
        self.body.pack(fill="both", expand=True)
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for view in self.views.values():
            view.grid(in_=self.body, row=0, column=0, sticky="nsew")
        self.show(self.page)
        self.after(300, self.prebuild)
        if getattr(self, "notice", None) is not None:
            self.notice.rebuild()

    def check_update(self):
        """Ask GitHub in the background; show the card if a newer release exists."""
        from . import update
        found = []
        worker = threading.Thread(target=lambda: found.append(update.check()), daemon=True)
        worker.start()

        def wait():
            if worker.is_alive():
                return self.after(300, wait)
            if found and found[0]:
                self.show_update(found[0])
        self.after(300, wait)

    def show_update(self, info):
        from .updatecard import UpdateNotice
        self.notice = UpdateNotice(self, info)

    def prebuild(self):
        """Build the category pages while the user looks at the home page, so they open at once."""
        for cat in CATEGORIES:
            if "cat:" + cat.id not in self.pages:
                self.category_page(cat)
                self.update_idletasks()
        self.show(self.page)                # keep whatever is on screen in front

    def crumb(self, text, command=None):
        ctk.CTkLabel(self.crumbs, text="›", font=("Segoe UI", 18), text_color=MUTED).pack(side="left", padx=8)
        lab = ctk.CTkLabel(self.crumbs, text=text, font=("Segoe UI Semibold" if command is None else "Segoe UI", 15),
                           text_color=TEXT if command is None else MUTED, cursor="hand2" if command else "")
        lab.pack(side="left")
        if command:
            lab.bind("<Button-1>", lambda e: command())

    def show(self, page):
        self.page = page
        for w in self.crumbs.winfo_children():
            w.destroy()
        kind = page[0]
        if kind == "tool":
            cat, tool = page[1], page[2]
            self.crumb(t(cat.key), lambda: self.open_category(cat))
            self.crumb(t(tool.key))
            for other in self.views.values():
                if other is not self.views[tool.id]:
                    other.lower(self.body)
            self.views[tool.id].lift(self.body)     # tool views belong to the window: raise above the body
            self.raise_notice()
            return
        for view in self.views.values():
            view.lower(self.body)
        if kind == "home":
            self.home_page().tkraise()
        else:
            self.crumb(t(page[1].key))
            self.category_page(page[1]).tkraise()
        self.raise_notice()

    def raise_notice(self):
        if self.notice is not None:
            self.notice.raise_()

    def place_page(self, page):
        page.grid(row=0, column=0, sticky="nsew", padx=(22, 6), pady=(4, 12))
        return page

    # -- pages ----------------------------------------------------------------------------------
    def home_page(self):
        if "home" in self.pages:
            return self.pages["home"]
        page = self.pages["home"] = self.place_page(ctk.CTkFrame(self.body, fg_color=BG))
        ctk.CTkLabel(page, text=t("bw_tagline"), font=("Segoe UI", 13), text_color=MUTED, anchor="w").pack(
            fill="x", pady=(0, 14))
        grid = CardGrid(page, CARD_W)
        grid.pack(fill="both", expand=True)
        for cat in CATEGORIES:
            ready = sum(tool.ready for tool in cat.tools)
            badges = [] if ready else [(t("bw_soon"), MUTED, None)]
            info = t("bw_tools_ready", ready=ready, n=len(cat.tools)) if ready else t("bw_tools_n", n=len(cat.tools))
            card = Card(grid, self.image(cat.icon, cat.id, 64), t(cat.key), t(cat.key + "_d") + "\n\n" + info,
                        lambda c=cat: self.open_category(c), badges=badges, dim=not ready)
            grid.add(card)
        return page

    def category_page(self, cat):
        key = "cat:" + cat.id
        if key in self.pages:
            return self.pages[key]
        page = self.pages[key] = self.place_page(ctk.CTkFrame(self.body, fg_color=BG))
        ctk.CTkLabel(page, text=t(cat.key + "_d"), font=("Segoe UI", 13), text_color=MUTED, anchor="w").pack(
            fill="x", pady=(0, 4))
        if not self.admin and any(tool.admin for tool in cat.tools):
            ctk.CTkLabel(page, text=" " + t("bw_admin_tip"), image=self.shield(), compound="left",
                         font=("Segoe UI", 11), text_color=MUTED, anchor="w").pack(fill="x", pady=(0, 10))
        grid = CardGrid(page, TOOL_W)
        grid.pack(fill="both", expand=True)
        for tool in cat.tools:
            badges = []
            if not tool.ready:
                badges.append((t("bw_soon"), MUTED, None))
            if tool.admin and not self.admin:
                # next to "coming soon" there is only room for the shield itself
                badges.append(("" if not tool.ready else t("bw_admin_badge"), WARN, self.shield()))
            card = Card(grid, self.image(tool.icon, cat.id, 52, tool.ready), t(tool.key), t(tool.key + "_d"),
                        lambda c=cat, x=tool: self.open_tool(c, x), badges=badges, width=TOOL_W, height=TOOL_H,
                        dim=not tool.ready)
            grid.add(card)
        return page

    # -- navigation -----------------------------------------------------------------------------
    def go_home(self):
        self.show(("home",))

    def open_category(self, cat):
        self.show(("category", cat))

    def open_tool(self, cat, tool):
        if not tool.ready:
            return messagebox.showinfo(t("bw_soon_title"), t("bw_soon_body", tool=t(tool.key)))
        if tool.admin and not self.admin:
            return self.ask_admin(tool)
        if tool.id not in self.views:
            view = self.views[tool.id] = tool.view(self)
            view.grid(in_=self.body, row=0, column=0, sticky="nsew")
        self.show(("tool", cat, tool))

    def open_tool_id(self, tool_id):
        cat, tool = find_tool(tool_id)
        if tool is not None:
            self.open_tool(cat, tool)

    def busy_views(self):
        return [v for v in self.views.values() if getattr(v, "busy", lambda: False)()]

    def ask_admin(self, tool):
        if not messagebox.askyesno(t("bw_admin_title"), t("bw_admin_body", tool=t(tool.key)), icon="warning"):
            return
        if self.busy_views() and not messagebox.askyesno(APP_NAME, t("bw_admin_busy"), icon="warning"):
            return
        if not elevate.restart_as_admin(tool.id):
            return messagebox.showinfo(APP_NAME, t("bw_admin_failed"))
        self.close_now()

    # -- language and closing -------------------------------------------------------------------
    def switch_language(self):
        if self.busy_views():
            return messagebox.showinfo(APP_NAME, t("bw_lang_busy"))
        i18n.set_language("en" if i18n.language() == "tr" else "tr")
        for view in self.views.values():
            view.grid_forget()
            if hasattr(view, "relabel"):
                view.relabel()
        self.build()

    def close_now(self):
        for view in self.views.values():
            if hasattr(view, "close_session"):
                view.close_session()
        self.destroy()

    def on_close(self):
        for view in list(self.views.values()):
            if hasattr(view, "on_close") and not view.on_close():
                return              # that tool stops its work first, then closes the window itself
        self.destroy()


def main(open_tool=None):
    forced = os.environ.get("RECOVERYTOOL_LANG")          # "en" or "tr" overrides the Windows language
    i18n.set_language(forced) if forced else i18n.detect()
    ctk.set_appearance_mode("dark")
    Shell(open_tool).mainloop()
