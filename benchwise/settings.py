"""Benchwise settings, in %LOCALAPPDATA%\\Benchwise\\settings.json (per Windows user)."""

from __future__ import annotations

import json
import os
import threading

_lock = threading.Lock()


def folder():
    path = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Benchwise")
    os.makedirs(path, exist_ok=True)
    return path


def _path():
    return os.path.join(folder(), "settings.json")


def load():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get(key, default=None):
    return load().get(key, default)


def put(key, value):
    with _lock:
        data = load()
        data[key] = value
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, _path())
