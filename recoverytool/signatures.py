"""File-type signatures used to judge whether recovered content matches its extension."""

from __future__ import annotations

ARCHIVE_EXT = {"xlsx", "docx", "pptx", "xlsm", "docm", "pptm", "zip", "odt", "ods", "odp", "epub", "jar", "apk"}
_MAGIC = {
    "jpg": [b"\xff\xd8"], "jpeg": [b"\xff\xd8"], "png": [b"\x89PNG"], "gif": [b"GIF8"], "bmp": [b"BM"],
    "pdf": [b"%PDF"], "psd": [b"8BPS"], "tif": [b"II*\0", b"MM\0*"], "tiff": [b"II*\0", b"MM\0*"],
    "doc": [b"\xd0\xcf\x11\xe0"], "xls": [b"\xd0\xcf\x11\xe0"], "ppt": [b"\xd0\xcf\x11\xe0"], "msi": [b"\xd0\xcf\x11\xe0"],
    "rar": [b"Rar!"], "7z": [b"7z\xbc\xaf"], "gz": [b"\x1f\x8b"], "exe": [b"MZ"], "dll": [b"MZ"],
    "avi": [b"RIFF"], "wav": [b"RIFF"], "webp": [b"RIFF"], "mkv": [b"\x1a\x45\xdf\xa3"], "webm": [b"\x1a\x45\xdf\xa3"],
    "mp3": [b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xfa", b"\xff\xf2", b"\xff\xe3"], "flac": [b"fLaC"],
    "sqlite": [b"SQLite"], "lnk": [b"L\0\0\0"],
}
for _e in ARCHIVE_EXT:
    _MAGIC[_e] = [b"PK"]
_ISO_MEDIA = {"mp4", "mov", "m4a", "m4v", "3gp", "heic"}
_ISO_BOXES = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip")


def magic_matches(name, head):
    """True / False when the extension has a known signature, None when it cannot be judged."""
    if name.startswith("~$") or "." not in name or not head:
        return None
    ext = name.rsplit(".", 1)[1].lower()
    if ext in _ISO_MEDIA:
        return head[4:8] in _ISO_BOXES
    sigs = _MAGIC.get(ext)
    if not sigs:
        return None
    if any(head.startswith(s) for s in sigs):
        return True
    if ext in ("doc", "xls") and head.lstrip()[:1] in (b"<", b"{", b"P"):
        return None                                   # HTML / RTF / OOXML saved under a legacy extension
    return False
