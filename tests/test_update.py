"""Update check: version comparison and the bilingual release notes.  No network needed.

    python tests\\test_update.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from benchwise import update  # noqa: E402


def test_versions():
    assert update.version_tuple("v1.10.2") == (1, 10, 2) and update.version_tuple("x") == ()
    assert update.newer("v1.10.0", "1.9.9") and update.newer("1.1.1", "1.1.0") and update.newer("2", "1.9")
    assert not update.newer("v1.1.0", "1.1.0") and not update.newer("v1.0.2", "1.1.0") and not update.newer("", "1.0")


def test_notes():
    body = open(os.path.join(ROOT, "docs", "release-notes", "1.1.0.md"), encoding="utf-8").read()
    tr, en = update.notes_for(body, "tr"), update.notes_for(body, "en")
    assert tr.startswith("### Benchwise") and "Disk Sağlığı" in tr and "Disk Health" not in tr
    assert en.startswith("### Benchwise") and "Disk Health" in en and "Disk Sağlığı" not in en
    rows = update.note_lines(en)
    assert rows[0] == ("head", "Benchwise") and rows[1][0] == "item"
    assert ("head", "Disk Health (new)") in rows
    # headings in the other style, CRLF line ends, and a missing language
    alt = "## English\r\n### Tool\r\n- **Fixed** `x`\r\n## Türkçe\r\n### Araç\r\n- düzeltildi\r\n"
    assert update.note_lines(update.notes_for(alt, "en")) == [("head", "Tool"), ("item", "Fixed x")]
    assert update.note_lines(update.notes_for(alt, "tr")) == [("head", "Araç"), ("item", "düzeltildi")]
    assert update.notes_for("<!-- en -->\nonly english", "tr") == "only english"
    assert update.notes_for("plain notes", "tr") == "plain notes"


if __name__ == "__main__":
    test_versions()
    test_notes()
    print("update tests passed")
