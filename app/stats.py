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
        return self._normalize(data)

    @staticmethod
    def _normalize(data: dict) -> dict:
        """Complète les champs manquants (robuste si le JSON est partiel/importé)."""
        if not isinstance(data, dict):
            data = {}
        data.setdefault("messages_total", 0)
        data.setdefault("started_at", _now().isoformat())
        data.setdefault("users", {})       # numéro -> {count, first, last}
        data.setdefault("by_day", {})      # "YYYY-MM-DD" -> nb de messages
        data.setdefault("by_hour", {})     # "0".."23" -> nb de messages
        data.setdefault("queries", {})     # texte recherché -> nb
        data.setdefault("products", {})    # nom produit -> {count, url}
        data.setdefault("failed_searches", {})  # recherche sans résultat -> nb
        data.setdefault("missed", [])      # demandes sans produit [{t, from, query}]
        data.setdefault("recent", [])      # derniers messages [{t, from, text}]
        # migration : ancien format produits (nom -> int)
        for name, v in list(data["products"].items()):
            if not isinstance(v, dict):
                data["products"][name] = {"count": int(v) if isinstance(v, int) else 0, "url": ""}
        return data

    # -- sauvegarde / restauration (contourne le disque éphémère) --------------
    def raw_json(self) -> str:
        """Contenu JSON complet, pour téléchargement (sauvegarde avant déploiement)."""
        with self._lock:
            return json.dumps(self._data, ensure_ascii=False, indent=2)

    def replace(self, new_data: dict) -> None:
        """Remplace toutes les données par un JSON importé (restauration)."""
        normalized = self._normalize(new_data)
        with self._lock:
            self._data = normalized
            self._save()

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
            hour = str(now.hour)
            d["by_hour"][hour] = d["by_hour"].get(hour, 0) + 1

            u = d["users"].setdefault(sender, {"count": 0, "first": now.isoformat(), "last": None})
            u["count"] += 1
            u["last"] = now.isoformat()

            q = (text or "").strip().lower()[:80]
            if q:
                d["queries"][q] = d["queries"].get(q, 0) + 1

            d["recent"].insert(0, {"t": now.isoformat(), "from": sender, "text": (text or "")[:200]})
            d["recent"] = d["recent"][:50]
            self._save()

    def record_search(self, query: str, found: bool) -> None:
        """Enregistre une recherche : on ne garde que celles SANS résultat."""
        if found:
            return
        q = (query or "").strip().lower()[:80]
        if not q:
            return
        with self._lock:
            fs = self._data["failed_searches"]
            fs[q] = fs.get(q, 0) + 1
            self._save()

    def record_missed(self, sender: str, query: str) -> None:
        """Client + demande dont aucun produit n'a été trouvé (zone 'À rappeler')."""
        q = (query or "").strip()[:120]
        if not q:
            return
        with self._lock:
            self._data["missed"].insert(0, {"t": _now().isoformat(), "from": sender or "?", "query": q})
            self._data["missed"] = self._data["missed"][:60]
            self._save()

    def record_products(self, items: list[tuple[str, str]]) -> None:
        """items : liste de (nom, lien) des produits proposés."""
        if not items:
            return
        with self._lock:
            prods = self._data["products"]
            for name, url in items:
                if not name:
                    continue
                e = prods.get(name)
                if not isinstance(e, dict):
                    e = {"count": 0, "url": ""}
                    prods[name] = e
                e["count"] += 1
                if url and not e.get("url"):
                    e["url"] = url
            self._save()

    def product_names(self) -> set:
        """Ensemble des noms de produits déjà proposés (pour les 'jamais proposés')."""
        with self._lock:
            return set(self._data["products"].keys())

    # -- lecture ---------------------------------------------------------------
    def summary(self) -> dict:
        with self._lock:
            d = self._data
            by_day = dict(sorted(d["by_day"].items()))
            by_hour = [d["by_hour"].get(str(h), 0) for h in range(24)]
            top_queries = sorted(d["queries"].items(), key=lambda kv: kv[1], reverse=True)[:10]
            top_products = sorted(
                (
                    {"name": n, "count": v.get("count", 0), "url": v.get("url", "")}
                    for n, v in d["products"].items()
                ),
                key=lambda p: p["count"],
                reverse=True,
            )[:10]
            failed = sorted(d["failed_searches"].items(), key=lambda kv: kv[1], reverse=True)[:15]
            users = sorted(
                (
                    {
                        "num": num,
                        "count": info.get("count", 0),
                        "first": info.get("first"),
                        "last": info.get("last"),
                    }
                    for num, info in d["users"].items()
                ),
                key=lambda u: u["last"] or "",
                reverse=True,
            )
            return {
                "messages_total": d["messages_total"],
                "users_total": len(d["users"]),
                "started_at": d["started_at"],
                "by_day": by_day,
                "by_hour": by_hour,
                "top_queries": top_queries,
                "top_products": top_products,
                "failed_searches": failed,
                "missed": d["missed"][:30],
                "users": users,
                "recent": d["recent"][:20],
            }
