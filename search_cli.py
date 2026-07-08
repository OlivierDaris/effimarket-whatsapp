"""Outil de test de l'Étape 1 : recherche produit en ligne de commande.

Usage :
    python search_cli.py                 # mode interactif
    python search_cli.py "beurre karité" # recherche directe

Le catalogue chargé est celui défini par CATALOG_PATH dans .env
(par défaut data/sample_catalog.csv).
"""
from __future__ import annotations

import sys

# Console Windows : forcer l'UTF-8 pour afficher accents et symboles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import config
from app.catalog import Catalog


def show(results):
    if not results:
        print("  Aucun produit trouvé.")
        return
    for i, (p, score) in enumerate(results, 1):
        print(f"  {i}. [{score:5.1f}] {p.name}  —  {p.price}  ({p.category})")
        if p.url:
            print(f"        {p.url}")


def main() -> None:
    print(f"Chargement du catalogue : {config.CATALOG_PATH}")
    catalog = Catalog.load(config.CATALOG_PATH)
    print(f"→ {len(catalog)} produits chargés.")
    print(f"→ Colonnes détectées : {catalog.columns}\n")

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"Recherche : « {query} »")
        show(catalog.search(query))
        return

    print("Mode interactif — tapez une recherche (ou 'q' pour quitter).")
    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if query.lower() in ("q", "quit", "exit"):
            break
        if query:
            show(catalog.search(query))


if __name__ == "__main__":
    main()
