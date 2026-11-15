"""The catalogue of a scan as a folder tree: what was found, what is ticked, what is recovered.

This is the model behind the result browser.  It knows nothing about widgets, so it can be
tested without a window.  All counters are kept per folder and updated incrementally, which
keeps ticking a folder or finishing a file cheap even with a million entries.
"""

from __future__ import annotations

from .model import DAMAGED, RECOVERED, UNCERTAIN, is_pending

# what a file is, as far as the user is concerned
PENDING, DONE, DOUBT, BROKEN, FAILED = "pending", "ok", "warn", "bad", "fail"


def state_of(item):
    if item.status in RECOVERED:
        return BROKEN if item.status == DAMAGED else DOUBT if item.status == UNCERTAIN else DONE
    return PENDING if is_pending(item) else FAILED


class Entry:
    """A row of the tree.  Folders carry the totals of everything below them."""

    __slots__ = ("name", "item", "parent", "children", "state", "checked", "files", "size", "done", "done_size",
                 "pend", "pend_size", "sel", "sel_size", "iid")

    def __init__(self, name, parent=None, item=None, is_dir=True):
        self.name, self.parent, self.item = name, parent, item
        self.children = [] if is_dir else None
        self.state, self.checked, self.iid = PENDING, False, None
        self.files = self.size = self.done = self.done_size = self.pend = self.pend_size = self.sel = self.sel_size = 0

    @property
    def is_dir(self):
        return self.children is not None

    def path(self):
        parts, e = [], self
        while e.parent is not None:
            parts.append(e.name)
            e = e.parent
        return "\\".join(reversed(parts))

    def tick(self):
        """0 = not ticked, 1 = ticked, 2 = partly (folders only)."""
        if not self.is_dir:
            return int(self.checked)
        if not self.sel:
            return 0
        return 1 if self.pend and self.sel >= self.pend else 2

    def mark(self):
        """State of a row for its icon; a folder is done when nothing below it is left to recover."""
        if not self.is_dir:
            return self.state
        if self.done and not self.pend:
            return DONE
        if self.done:
            return "part"
        return PENDING if self.pend else "none"


class Catalog:
    def __init__(self, items):
        self.root = Entry("")
        self.by_id = {}
        order = [self.root]
        folders = {}
        last_key, last = None, None
        for it in items:
            key = (it.top, tuple(it.rel[:-1]))
            if key != last_key:
                last_key, last = key, self._folder(folders, order, it.top, key[1])
            if it.node.is_dir:
                me = folders.get((it.top, tuple(it.rel)))
                if me is None:
                    me = folders[(it.top, tuple(it.rel))] = Entry(it.rel[-1], last)
                    last.children.append(me)
                    order.append(me)
                me.item = it
                continue
            e = Entry(it.rel[-1], last, it, is_dir=False)
            e.state = state_of(it)
            e.files, e.size = 1, it.node.size
            if e.state == PENDING:
                e.pend, e.pend_size = 1, e.size
            elif e.state != FAILED:
                e.done, e.done_size = 1, e.size
            last.children.append(e)
            order.append(e)
            self.by_id[it.id] = e
        for e in reversed(order):                       # children were created after their parents
            p = e.parent
            if p is not None:
                p.files += e.files
                p.size += e.size
                p.done += e.done
                p.done_size += e.done_size
                p.pend += e.pend
                p.pend_size += e.pend_size

    def _folder(self, folders, order, top, rel):
        e = folders.get((top, rel))
        if e is None:
            parent = self._folder(folders, order, top, rel[:-1]) if rel else self.root
            e = folders[(top, rel)] = Entry(rel[-1] if rel else top, parent)
            parent.children.append(e)
            order.append(e)
        return e

    # -- ticking --------------------------------------------------------------------------------
    @staticmethod
    def _bubble(e, d_sel, d_size):
        while e is not None:
            e.sel += d_sel
            e.sel_size += d_size
            e = e.parent

    def set_checked(self, entry, on):
        """Tick or untick a row.  Ticking a folder ticks what is still to be recovered below it;
        files that are already recovered are only ticked one by one (to write them again)."""
        if not entry.is_dir:
            if entry.state == FAILED or entry.checked == on:
                return
            entry.checked = on
            self._bubble(entry, 1 if on else -1, entry.size if on else -entry.size)
            return
        before = (entry.sel, entry.sel_size)
        stack, post = [entry], []
        while stack:
            e = stack.pop()
            if e.is_dir:
                post.append(e)
                stack.extend(e.children)
            else:
                e.checked = on and e.state == PENDING
                e.sel, e.sel_size = (1, e.size) if e.checked else (0, 0)
        for e in reversed(post):
            e.sel = sum(c.sel for c in e.children)
            e.sel_size = sum(c.sel_size for c in e.children)
        self._bubble(entry.parent, entry.sel - before[0], entry.sel_size - before[1])

    def toggle(self, entry):
        self.set_checked(entry, entry.tick() != 1)

    def selected(self):
        """The ticked files, in catalogue order."""
        return [e.item for e in self.by_id.values() if e.checked]

    # -- progress -------------------------------------------------------------------------------
    def update(self, item):
        """A file was handled by the engine.  Returns the rows whose look changed (file and folders)."""
        e = self.by_id.get(item.id)
        if e is None:
            return []
        new = state_of(item)
        d_done = (new not in (PENDING, FAILED)) - (e.state not in (PENDING, FAILED))
        d_pend = (new == PENDING) - (e.state == PENDING)
        e.state = new
        untick = e.checked and new != PENDING
        if untick:
            e.checked = False
        changed, p = [e], e.parent
        e.done, e.pend = e.done + d_done, e.pend + d_pend
        while p is not None:
            p.done += d_done
            p.done_size += d_done * e.size
            p.pend += d_pend
            p.pend_size += d_pend * e.size
            if untick:
                p.sel -= 1
                p.sel_size -= e.size
            changed.append(p)
            p = p.parent
        if untick:
            e.sel, e.sel_size = 0, 0
        return changed

    def find(self, text, limit=2000):
        """Files whose name contains ``text`` (case-insensitive); at most ``limit``, plus the real count."""
        text, out, n = text.lower(), [], 0
        for e in self.by_id.values():
            if text in e.name.lower():
                n += 1
                if len(out) < limit:
                    out.append(e)
        return out, n
