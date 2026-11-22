"""Display & Input > Keyboard Test: every key lights up on an on-screen keyboard when pressed."""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from recoverytool.i18n import t

from .. import ui
from ..toolkit import ToolView, card, note, texts

texts({
    "kb_how": ("Press every key. A key turns green once it has worked; the one held down is blue. Keys that "
               "stay grey after pressing them do not reach Windows.",
               "Bütün tuşlara basın. Çalışan tuş yeşile döner; basılı tutulan mavi görünür. Bastığınız halde gri "
               "kalan tuşlar Windows'a ulaşmıyor demektir."),
    "kb_count": ("{n} of {total} keys tested", "{total} tuştan {n} tanesi test edildi"),
    "kb_last": ("Last key: {name}  ·  code {code}", "Son tuş: {name}  ·  kod {code}"),
    "kb_reset": ("Start again", "Baştan başla"),
    "kb_note": ("Windows keeps a few keys for itself (Win+L, Alt+Tab, Ctrl+Alt+Del, Print Screen on some "
                "systems); they may not light up even when they work. Fn is handled by the keyboard itself.",
                "Windows bazı tuşları kendine ayırır (Win+L, Alt+Tab, Ctrl+Alt+Del, bazı sistemlerde Print Screen); "
                "çalışsalar bile yanmayabilirler. Fn tuşunu klavyenin kendisi işler."),
})

U = 40          # pixels per key unit
GAP = 4

# (label, id, width in units); id: Windows virtual-key code, or a name for left/right modifiers; None = gap
ROWS = [
    [("Esc", 27, 1), None, ("F1", 112, 1), ("F2", 113, 1), ("F3", 114, 1), ("F4", 115, 1), (None, None, 0.5),
     ("F5", 116, 1), ("F6", 117, 1), ("F7", 118, 1), ("F8", 119, 1), (None, None, 0.5), ("F9", 120, 1),
     ("F10", 121, 1), ("F11", 122, 1), ("F12", 123, 1), (None, None, 0.4), ("PrtSc", 44, 1), ("ScrLk", 145, 1),
     ("Pause", 19, 1)],
    [('"', 192, 1), ("1", 49, 1), ("2", 50, 1), ("3", 51, 1), ("4", 52, 1), ("5", 53, 1), ("6", 54, 1), ("7", 55, 1),
     ("8", 56, 1), ("9", 57, 1), ("0", 48, 1), ("*", 223, 1), ("-", 189, 1), ("⌫", 8, 2), (None, None, 0.4),
     ("Ins", 45, 1), ("Home", 36, 1), ("PgUp", 33, 1), (None, None, 0.4), ("Num", 144, 1), ("/", 111, 1),
     ("*", 106, 1), ("-", 109, 1)],
    [("Tab", 9, 1.5), ("Q", 81, 1), ("W", 87, 1), ("E", 69, 1), ("R", 82, 1), ("T", 84, 1), ("Y", 89, 1),
     ("U", 85, 1), ("I", 73, 1), ("O", 79, 1), ("P", 80, 1), ("Ğ", 219, 1), ("Ü", 221, 1), (",", 188, 1.5),
     (None, None, 0.4), ("Del", 46, 1), ("End", 35, 1), ("PgDn", 34, 1), (None, None, 0.4), ("7", 103, 1),
     ("8", 104, 1), ("9", 105, 1), ("+", 107, 1)],
    [("Caps", 20, 1.75), ("A", 65, 1), ("S", 83, 1), ("D", 68, 1), ("F", 70, 1), ("G", 71, 1), ("H", 72, 1),
     ("J", 74, 1), ("K", 75, 1), ("L", 76, 1), ("Ş", 186, 1), ("i", 222, 1), ("Enter", 13, 2.25),
     (None, None, 3.8), ("4", 100, 1), ("5", 101, 1), ("6", 102, 1)],
    [("Shift", "Shift_L", 1.25), ("<", 226, 1), ("Z", 90, 1), ("X", 88, 1), ("C", 67, 1), ("V", 86, 1),
     ("B", 66, 1), ("N", 78, 1), ("M", 77, 1), ("Ö", 191, 1), ("Ç", 220, 1), (".", 190, 1),
     ("Shift", "Shift_R", 2.75), (None, None, 1.4), ("↑", 38, 1), (None, None, 1.4), ("1", 97, 1),
     ("2", 98, 1), ("3", 99, 1)],
    [("Ctrl", "Control_L", 1.25), ("Win", 91, 1.25), ("Alt", "Alt_L", 1.25), ("", 32, 6.25),
     ("AltGr", "Alt_R", 1.25), ("Win", 92, 1.25), ("Menu", 93, 1.25), ("Ctrl", "Control_R", 1.25),
     (None, None, 0.4), ("←", 37, 1), ("↓", 40, 1), ("→", 39, 1), (None, None, 0.4), ("0", 96, 2), (",", 110, 1)],
]
MODIFIERS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}


class View(ToolView):
    title_key = "tool_keyboard"

    def fill(self):
        self.done, self.down = set(), set()
        c = card(self.body, t("tool_keyboard"))
        note(c, t("kb_how"), color=ui.TEXT)
        width = int(sum(k[2] if k else 0.5 for k in ROWS[1]) * U + 40)
        self.canvas = tk.Canvas(c, width=width, height=len(ROWS) * (U + GAP) + U // 2, bg=ui.CARD,
                                highlightthickness=0, bd=0)
        self.canvas.pack(padx=18, pady=(4, 8), anchor="w")
        self.keys = {}
        self.draw()
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 6))
        self.count = ctk.CTkLabel(row, text=" ", font=("Segoe UI Semibold", 13), text_color=ui.TEXT)
        self.count.pack(side="left")
        self.last = ctk.CTkLabel(row, text=" ", font=("Segoe UI", 12), text_color=ui.MUTED)
        self.last.pack(side="left", padx=20)
        ui.button(row, t("kb_reset"), self.reset, 130).pack(side="right")
        note(c, t("kb_note"))
        self.update_count()
        if not getattr(self, "bound", False):       # fill() runs again after a language switch
            self.bound = True
            top = self.winfo_toplevel()
            top.bind("<KeyPress>", self.on_key, add="+")
            top.bind("<KeyRelease>", self.on_release, add="+")

    def draw(self):
        y = 8
        for r, row in enumerate(ROWS):
            x = 8
            if r == 1:
                y += U // 2 - GAP            # a little space under the function keys
            for key in row:
                if key is None:
                    x += U // 2
                    continue
                label, kid, units = key
                w = units * U - GAP
                if kid is not None:
                    rect = self.canvas.create_rectangle(x, y, x + w, y + U - GAP, fill="#222c42", outline="#33405c",
                                                        width=1)
                    text = self.canvas.create_text(x + w / 2, y + (U - GAP) / 2, text=label, fill=ui.TEXT,
                                                   font=("Segoe UI", 9 if len(label) > 3 else 10))
                    self.keys[kid] = (rect, text)
                x += units * U
            y += U + GAP

    def active(self):
        """Only while this tool is the page on screen (tool views stay alive behind other pages)."""
        top = self.winfo_toplevel()
        page = getattr(top, "page", None)
        return bool(page) and page[0] == "tool" and getattr(top, "views", {}).get(page[2].id) is self

    def key_id(self, e):
        return e.keysym if e.keysym in MODIFIERS else e.keycode

    def paint(self, kid):
        if kid not in self.keys:
            return
        rect, text = self.keys[kid]
        fill = ui.ACCENT if kid in self.down else ("#1f7a4a" if kid in self.done else "#222c42")
        self.canvas.itemconfigure(rect, fill=fill)

    def on_key(self, e):
        if not self.active():
            return
        kid = self.key_id(e)
        self.down.add(kid)
        self.done.add(kid)
        self.paint(kid)
        name = e.keysym if e.keysym and e.keysym != "??" else "?"
        self.last.configure(text=t("kb_last", name=name, code=e.keycode))
        self.update_count()
        return "break"                         # Tab, Alt, F10 must not move focus or open menus

    def on_release(self, e):
        if not self.active():
            return
        kid = self.key_id(e)
        self.down.discard(kid)
        if e.keycode == 44:                      # Print Screen only sends a release
            self.done.add(kid)
            self.update_count()
        self.paint(kid)
        return "break"

    def update_count(self):
        tested = len([k for k in self.done if k in self.keys])
        self.count.configure(text=t("kb_count", n=tested, total=len(self.keys)))

    def reset(self):
        self.done.clear()
        self.down.clear()
        for kid in self.keys:
            self.paint(kid)
        self.last.configure(text=" ")
        self.update_count()
