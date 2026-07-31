"""Chargement du catalogue produits (Excel ou CSV) et recherche floue.

Le chargeur détecte automatiquement les colonnes à partir de leur nom
(français ou anglais), donc il s'adapte au fichier Excel réel d'effi-market
sans configuration : il suffit que les en-têtes ressemblent à "nom", "prix",
"lien", "catégorie", etc.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

# --- Détection automatique des colonnes ---------------------------------------
# Pour chaque champ interne, la liste des noms de colonnes possibles (après
# normalisation : minuscules, sans accents). Le premier qui matche gagne.
COLUMN_ALIASES: dict[str, list[str]] = {
    "name": ["nom", "name", "produit", "product", "titre", "title",
             "designation", "libelle", "article", "intitule"],
    "price": ["prix", "price", "tarif", "montant", "cout"],
    "url": ["url", "lien", "link", "permalink", "page", "adresse"],
    "description": ["description", "desc", "detail", "details", "resume", "texte"],
    "category": ["categorie", "category", "cat", "rayon", "type", "famille", "rubrique"],
    "image": ["image", "img", "photo", "visuel", "picture"],
    "stock": ["stock", "quantite", "dispo", "disponibilite", "qty", "disponible"],
    "brand": ["marque", "brand", "vendeur", "boutique", "magasin", "seller", "shop", "fournisseur"],
    "sku": ["sku", "ref", "reference", "code"],
}


def _norm(text: str) -> str:
    """Minuscule, sans accents, sans espaces superflus — pour comparer noms de colonnes et requêtes."""
    text = str(text).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text)


def _detect_columns(df_columns: list[str]) -> dict[str, str]:
    """Associe chaque champ interne à une colonne réelle du fichier."""
    normalized = {_norm(c): c for c in df_columns}
    mapping: dict[str, str] = {}
    for field_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            # match exact d'abord
            if alias in normalized:
                mapping[field_name] = normalized[alias]
                break
        else:
            # sinon, match partiel (ex. "nom du produit" contient "nom")
            for norm_col, real_col in normalized.items():
                if any(alias in norm_col for alias in aliases):
                    mapping[field_name] = real_col
                    break
    return mapping


@dataclass
class Product:
    name: str
    price: str = ""
    url: str = ""
    description: str = ""
    category: str = ""
    brand: str = ""
    stock: str = ""
    image: str = ""
    # texte pré-calculé (normalisé) utilisé pour la recherche
    _haystack: str = field(default="", repr=False)

    def as_line(self) -> str:
        """Représentation courte pour un message WhatsApp."""
        parts = [f"*{self.name}*"]
        if self.price:
            parts.append(f"— {self.price}")
        line = " ".join(parts)
        if self.url:
            line += f"\n{self.url}"
        return line


def _norm_link(url: str) -> str:
    """Normalise un lien pour comparaison (sans espaces, sans '/' final)."""
    return str(url).strip().rstrip("/")


class Catalog:
    def __init__(self, products: list[Product], columns: dict[str, str], source: Path):
        self.products = products
        self.columns = columns          # mapping champ interne -> colonne réelle
        self.source = source
        # Index pour retrouver un produit à partir de son lien.
        self._by_link = {_norm_link(p.url): p for p in products if p.url}

    def by_link(self, url: str) -> Optional[Product]:
        """Retrouve un produit à partir de son lien (ou None)."""
        return self._by_link.get(_norm_link(url))

    # -- chargement ------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Catalogue introuvable : {path}")

        if path.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(path, dtype=str)
        elif path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str)
        else:
            raise ValueError(f"Format non supporté : {path.suffix} (utilisez .xlsx, .xls ou .csv)")

        df = df.fillna("")
        mapping = _detect_columns(list(df.columns))
        if "name" not in mapping:
            raise ValueError(
                "Impossible de détecter la colonne du NOM de produit. "
                f"Colonnes trouvées : {list(df.columns)}"
            )

        products: list[Product] = []
        for _, row in df.iterrows():
            def get(field_name: str) -> str:
                col = mapping.get(field_name)
                return str(row[col]).strip() if col else ""

            name = get("name")
            if not name:
                continue  # ignore les lignes sans nom
            p = Product(
                name=name,
                price=get("price"),
                url=get("url"),
                description=get("description"),
                category=get("category"),
                brand=get("brand"),
                stock=get("stock"),
                image=get("image"),
            )
            # haystack : tout le texte cherchable, normalisé
            p._haystack = _norm(" ".join([p.name, p.category, p.brand, p.description]))
            products.append(p)

        return cls(products, mapping, path)

    # -- recherche -------------------------------------------------------------
    def search(self, query: str, limit: int = 5, min_score: float = 55.0) -> list[tuple[Product, float]]:
        """Retourne les meilleurs produits (produit, score 0-100) pour une requête en langage naturel."""
        q = _norm(query)
        if not q:
            return []

        results: list[tuple[Product, float]] = []
        for p in self.products:
            name_n = _norm(p.name)
            # Score combiné : le nom compte le plus, puis le reste du texte.
            score_name = max(
                fuzz.WRatio(q, name_n),
                fuzz.token_set_ratio(q, name_n),
            )
            score_hay = fuzz.token_set_ratio(q, p._haystack)
            score = 0.7 * score_name + 0.3 * score_hay
            # bonus si tous les mots de la requête sont présents dans le texte
            words = [w for w in q.split() if len(w) > 2]
            if words and all(w in p._haystack for w in words):
                score = min(100.0, score + 15.0)
            if score >= min_score:
                results.append((p, round(score, 1)))

        results.sort(key=lambda t: t[1], reverse=True)
        return results[:limit]

    def __len__(self) -> int:
        return len(self.products)
