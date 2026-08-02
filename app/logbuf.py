"""Capture des logs du serveur en mémoire, pour les afficher dans l'admin.

On « duplique » (tee) sys.stdout / sys.stderr : chaque ligne imprimée par le
bot (messages reçus, erreurs d'envoi, bascule IA…) est aussi conservée dans un
tampon circulaire borné, exposé ensuite via /admin/logs.
"""
from __future__ import annotations

import sys
import threading
from collections import deque
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:
    _PARIS = timezone.utc

_MAX = 600
_buffer: deque[tuple[str, str]] = deque(maxlen=_MAX)
_lock = threading.Lock()
_installed = False


class _Tee:
    """Écrit sur le flux d'origine ET mémorise les lignes non vides."""

    def __init__(self, stream):
        self._s = stream

    def write(self, text: str):
        try:
            self._s.write(text)
        except Exception:
            pass
        if text:
            ts = datetime.now(_PARIS).strftime("%H:%M:%S")
            for line in text.split("\n"):
                if line.strip():
                    with _lock:
                        _buffer.append((ts, line.rstrip()))
        return len(text)

    def flush(self):
        try:
            self._s.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._s, name)


def install() -> None:
    """Active la capture (idempotent)."""
    global _installed
    if _installed:
        return
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
    _installed = True


def text(limit: int = 400) -> str:
    """Renvoie les dernières lignes, la plus récente en bas."""
    with _lock:
        items = list(_buffer)[-limit:]
    return "\n".join(f"{t}  {line}" for t, line in items)
