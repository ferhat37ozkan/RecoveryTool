"""Is there a newer Benchwise on GitHub?

One request to the public GitHub API (latest release of the repository), in the background,
shortly after start.  Only a "Benchwise/<version>" user agent is sent; no data about the user or
the computer.  Without network, or on any error, it simply says nothing.
Set BENCHWISE_NO_UPDATE_CHECK=1 to switch it off.  For testing the notice against a real release,
BENCHWISE_TEST_VERSION=1.0.9 makes the check (and only the check) treat this program as that version.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

from . import REPO, __version__

API = "https://api.github.com/repos/%s/releases/latest" % REPO


def version_tuple(text):
    """"v1.10.2" -> (1, 10, 2); anything unreadable -> ()."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def current_version():
    """The version the update check compares with: the real one, unless a test overrides it."""
    return os.environ.get("BENCHWISE_TEST_VERSION") or __version__


def newer(latest, current=None):
    a, b = version_tuple(latest), version_tuple(current or current_version())
    return bool(a) and a > b


_LANG_MARK = re.compile(r"^\s*(?:<!--\s*(tr|en)\s*-->|##\s*(Türkçe|Turkish|English|İngilizce)\s*)$", re.I | re.M)
_LANG_NAMES = {"türkçe": "tr", "turkish": "tr", "english": "en", "i̇ngilizce": "en", "ingilizce": "en"}


def notes_for(body, lang):
    """The part of the release notes in ``lang`` ("tr" / "en").

    Release notes carry both languages, each section started by ``<!-- tr -->`` / ``<!-- en -->``
    (or a ``## Türkçe`` / ``## English`` heading); inside, ``### Tool`` headings with ``- `` items.
    Notes without such sections are returned whole; a missing language falls back to the other."""
    body = (body or "").replace("\r\n", "\n")
    marks = list(_LANG_MARK.finditer(body))
    if not marks:
        return body.strip()
    parts = {}
    for i, m in enumerate(marks):
        code = (m.group(1) or _LANG_NAMES.get((m.group(2) or "").lower(), "")).lower()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        parts.setdefault(code, body[m.end():end].strip())
    return parts.get(lang) or parts.get("en") or parts.get("tr") or body.strip()


def note_lines(text):
    """Release notes as ``(kind, text)`` rows for display: "head" (a tool), "item" or "text"."""
    rows = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        plain = s.replace("**", "").replace("`", "")
        if s.startswith("#"):
            rows.append(("head", plain.lstrip("#").strip()))
        elif s[:2] in ("- ", "* ", "+ "):
            rows.append(("item", plain[2:].strip()))
        else:
            rows.append(("text", plain))
    return rows


def check(timeout=8):
    """The latest release when it is newer than this program, else None."""
    if os.environ.get("BENCHWISE_NO_UPDATE_CHECK"):
        return None
    req = urllib.request.Request(API, headers={"User-Agent": "Benchwise/%s" % __version__,
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read(1 << 20).decode("utf-8"))
    except Exception:                       # offline, rate limited, proxy...: no news is fine
        return None
    tag = rel.get("tag_name") or ""
    if rel.get("draft") or rel.get("prerelease") or not newer(tag):
        return None
    assets = [a for a in rel.get("assets") or () if a.get("name", "").lower().endswith(".exe")]
    named = [a for a in assets if a["name"].lower() == "benchwise.exe"]
    other = [a for a in assets if "-cli" not in a["name"].lower()]         # uploaded under another name
    asset = (named or other or [{}])[0]
    exe = asset.get("browser_download_url")
    return {"version": tag.lstrip("vV"), "name": rel.get("name") or tag, "notes": (rel.get("body") or "").strip(),
            "page": rel.get("html_url") or "https://github.com/%s/releases" % REPO, "exe": exe,
            "size": asset.get("size"), "digest": asset.get("digest"),       # "sha256:<hex>", checked on install
            "date": (rel.get("published_at") or "")[:10]}
