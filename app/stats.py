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

try:
    from zoneinfo import ZoneInfo
    PARIS = ZoneInfo("Europe/Paris")
except Exception:  # repli si la base de fuseaux est absente
    PARIS = timezone.utc


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
        data.setdefault("missed_total", len(data.get("missed", [])))  # compteur cumulé
        data.setdefault("recent", [])      # derniers messages [{t, from, text}]
        data.setdefault("days", {})        # "YYYY-MM-DD" -> détail du jour
        # migration : ancien format produits (nom -> int)
        for name, v in list(data["products"].items()):
            if not isinstance(v, dict):
                data["products"][name] = {"count": int(v) if isinstance(v, int) else 0, "url": ""}
        # backfill des sous-champs par utilisateur (rapport détaillé)
        for info in data["users"].values():
            if isinstance(info, dict):
                info.setdefault("count", 0)
                info.setdefault("first", None)
                info.setdefault("last", None)
                info.setdefault("products", {})   # nom -> {count, url}
                info.setdefault("missed", [])     # [{t, query}]
                info.setdefault("messages", [])   # [{t, text}]
        return data

    def _user(self, sender: str, now_iso: str) -> dict:
        """Renvoie (en créant au besoin) la fiche d'un utilisateur."""
        u = self._data["users"].get(sender)
        if not isinstance(u, dict):
            u = {"count": 0, "first": now_iso, "last": None, "products": {}, "missed": [], "messages": []}
            self._data["users"][sender] = u
        return u

    @staticmethod
    def _today_key() -> str:
        return _now().astimezone(PARIS).strftime("%Y-%m-%d")

    def _day(self, day_key: str) -> dict:
        """Renvoie (en créant au besoin) le détail d'un jour."""
        db = self._data["days"].get(day_key)
        if not isinstance(db, dict):
            db = {"messages": 0, "users": {}, "products": {}, "missed": [], "queries": {}, "recent": []}
            self._data["days"][day_key] = db
            if len(self._data["days"]) > 90:  # garde ~3 mois
                for old in sorted(self._data["days"])[:-90]:
                    self._data["days"].pop(old, None)
        return db

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

            local = now.astimezone(PARIS)  # jours/heures en heure de France
            day = local.strftime("%Y-%m-%d")
            d["by_day"][day] = d["by_day"].get(day, 0) + 1
            hour = str(local.hour)
            d["by_hour"][hour] = d["by_hour"].get(hour, 0) + 1

            u = self._user(sender, now.isoformat())
            u["count"] += 1
            u["last"] = now.isoformat()
            u["messages"].insert(0, {"t": now.isoformat(), "text": (text or "")[:200]})
            u["messages"] = u["messages"][:20]

            q = (text or "").strip().lower()[:80]
            if q:
                d["queries"][q] = d["queries"].get(q, 0) + 1

            d["recent"].insert(0, {"t": now.isoformat(), "from": sender, "text": (text or "")[:200]})
            d["recent"] = d["recent"][:50]

            # détail du jour
            db = self._day(day)
            db["messages"] += 1
            db["users"][sender] = db["users"].get(sender, 0) + 1
            if q:
                db["queries"][q] = db["queries"].get(q, 0) + 1
            db["recent"].insert(0, {"t": now.isoformat(), "from": sender, "text": (text or "")[:200]})
            db["recent"] = db["recent"][:200]
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
            now = _now().isoformat()
            self._data["missed"].insert(0, {"t": now, "from": sender or "?", "query": q})
            self._data["missed"] = self._data["missed"][:60]
            self._data["missed_total"] = self._data.get("missed_total", 0) + 1
            u = self._data["users"].get(sender)
            if isinstance(u, dict):
                u.setdefault("missed", []).insert(0, {"t": now, "query": q})
                u["missed"] = u["missed"][:20]
            db = self._day(self._today_key())
            db["missed"].insert(0, {"t": now, "from": sender or "?", "query": q})
            db["missed"] = db["missed"][:200]
            self._save()

    def record_products(self, sender: str, items: list[tuple[str, str]]) -> None:
        """items : liste de (nom, lien) des produits proposés à `sender`."""
        if not items:
            return
        with self._lock:
            prods = self._data["products"]
            u = self._data["users"].get(sender)
            uprods = u["products"] if isinstance(u, dict) else None
            dprods = self._day(self._today_key())["products"]  # produits du jour
            for name, url in items:
                if not name:
                    continue
                # global
                e = prods.get(name)
                if not isinstance(e, dict):
                    e = {"count": 0, "url": ""}
                    prods[name] = e
                e["count"] += 1
                if url and not e.get("url"):
                    e["url"] = url
                # par utilisateur (produits « préférés »)
                if uprods is not None:
                    pe = uprods.get(name)
                    if not isinstance(pe, dict):
                        pe = {"count": 0, "url": url or ""}
                        uprods[name] = pe
                    pe["count"] += 1
                    if url and not pe.get("url"):
                        pe["url"] = url
                # par jour
                de = dprods.get(name)
                if not isinstance(de, dict):
                    de = {"count": 0, "url": url or ""}
                    dprods[name] = de
                de["count"] += 1
                if url and not de.get("url"):
                    de["url"] = url
            self._save()

    def report(self, num: str) -> dict | None:
        """Rapport détaillé d'un client (produits préférés, demandes ratées, messages)."""
        with self._lock:
            u = self._data["users"].get(num)
            if not isinstance(u, dict):
                return None
            products = sorted(
                (
                    {"name": n, "count": v.get("count", 0), "url": v.get("url", "")}
                    for n, v in u.get("products", {}).items()
                ),
                key=lambda p: p["count"],
                reverse=True,
            )
            return {
                "num": num,
                "count": u.get("count", 0),
                "first": u.get("first"),
                "last": u.get("last"),
                "products": products,
                "missed": list(u.get("missed", []))[:20],
                "messages": list(u.get("messages", []))[:20],
            }

    def product_names(self) -> set:
        """Ensemble des noms de produits déjà proposés (pour les 'jamais proposés')."""
        with self._lock:
            return set(self._data["products"].keys())

    def day_report(self, date: str) -> dict:
        """Détail d'un jour (pour la page de détail par date)."""
        with self._lock:
            db = self._data["days"].get(date)
            if not isinstance(db, dict):
                db = {"messages": 0, "users": {}, "products": {}, "missed": [], "queries": {}, "recent": []}
            clients = sorted(
                ({"num": n, "count": c} for n, c in db.get("users", {}).items()),
                key=lambda x: x["count"], reverse=True,
            )
            products = sorted(
                (
                    {"name": n, "count": v.get("count", 0), "url": v.get("url", "")}
                    for n, v in db.get("products", {}).items()
                ),
                key=lambda p: p["count"], reverse=True,
            )
            top_queries = sorted(db.get("queries", {}).items(), key=lambda kv: kv[1], reverse=True)[:10]
            return {
                "date": date,
                "messages": db.get("messages", 0),
                "clients": clients,
                "products": products,
                "top_queries": top_queries,
                "missed": list(db.get("missed", []))[:50],
                "recent": list(db.get("recent", []))[:50],
            }

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
                "missed_total": d.get("missed_total", len(d["missed"])),
                "dates": sorted(d["days"].keys(), reverse=True),
                "today": self._today_key(),
                "by_day": by_day,
                "by_hour": by_hour,
                "top_queries": top_queries,
                "top_products": top_products,
                "failed_searches": failed,
                "missed": d["missed"][:30],
                "users": users,
                "recent": d["recent"][:20],
            }
