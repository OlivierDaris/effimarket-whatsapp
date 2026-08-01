"""Statistiques d'usage du bot, persistées dans un fichier JSON.

La « base de données » est un simple fichier JSON (data/stats.json). Chaque
message entrant y est enregistré, et le tableau de bord (/dashboard) le relit.

⚠️ Sur l'offre gratuite Render, le disque est éphémère : ce fichier est remis à
zéro à chaque redéploiement/redémarrage complet. Les stats reflètent donc
l'activité depuis le dernier démarrage. Pour un historique durable, il faudrait
un disque persistant ou une vraie base de données.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Stats:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        # valeurs par défaut (robuste si le fichier est partiel)
        data.setdefault("messages_total", 0)
        data.setdefault("started_at", _now().isoformat())
        data.setdefault("users", {})       # numéro -> {count, first, last}
        data.setdefault("by_day", {})      # "YYYY-MM-DD" -> nb de messages
        data.setdefault("queries", {})     # texte recherché -> nb
        data.setdefault("products", {})    # nom produit affiché -> nb
        data.setdefault("recent", [])      # derniers messages [{t, from, text}]
        return data

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[STATS] sauvegarde échouée : {e}")

    # -- enregistrement --------------------------------------------------------
    def record_message(self, sender: str, text: str) -> None:
        with self._lock:
            d = self._data
            now = _now()
            d["messages_total"] += 1

            day = now.strftime("%Y-%m-%d")
            d["by_day"][day] = d["by_day"].get(day, 0) + 1

            u = d["users"].setdefault(sender, {"count": 0, "first": now.isoformat(), "last": None})
            u["count"] += 1
            u["last"] = now.isoformat()

            q = (text or "").strip().lower()[:80]
            if q:
                d["queries"][q] = d["queries"].get(q, 0) + 1

            d["recent"].insert(0, {"t": now.isoformat(), "from": sender, "text": (text or "")[:200]})
            d["recent"] = d["recent"][:50]
            self._save()

    def record_products(self, names: list[str]) -> None:
        if not names:
            return
        with self._lock:
            for n in names:
                if n:
                    self._data["products"][n] = self._data["products"].get(n, 0) + 1
            self._save()

    # -- lecture ---------------------------------------------------------------
    def summary(self) -> dict:
        with self._lock:
            d = self._data
            by_day = dict(sorted(d["by_day"].items()))
            top_queries = sorted(d["queries"].items(), key=lambda kv: kv[1], reverse=True)[:10]
            top_products = sorted(d["products"].items(), key=lambda kv: kv[1], reverse=True)[:10]
            return {
                "messages_total": d["messages_total"],
                "users_total": len(d["users"]),
                "started_at": d["started_at"],
                "by_day": by_day,
                "top_queries": top_queries,
                "top_products": top_products,
                "recent": d["recent"][:20],
            }
