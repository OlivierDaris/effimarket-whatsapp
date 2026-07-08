"""Outil de test de l'Étape 2 : dialoguer avec l'IA en console.

L'IA (Gemini) comprend la demande, cherche dans le catalogue via son outil,
et répond en français avec le bon produit + lien. La conversation garde le
contexte d'un message à l'autre (comme le fera WhatsApp).

Usage :
    python chat_cli.py
"""
from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import config
from app.ai import get_provider
from app.catalog import Catalog


def main() -> None:
    print(f"Catalogue : {config.CATALOG_PATH}")
    catalog = Catalog.load(config.CATALOG_PATH)
    model = config.GROQ_MODEL if config.AI_PROVIDER == "groq" else config.GEMINI_MODEL
    print(f"→ {len(catalog)} produits.  Moteur IA : {config.AI_PROVIDER} ({model})\n")

    provider = get_provider(catalog)
    chat = provider.new_chat()

    print("Discutez avec l'assistant Effi-Market (tapez 'q' pour quitter).")
    print("Exemples : « bonjour », « je cherche de quoi hydrater mes cheveux », « un tambour »\n")

    while True:
        try:
            user = input("Vous > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user.lower() in ("q", "quit", "exit"):
            break
        if not user:
            continue
        try:
            answer = provider.reply(chat, user)
        except Exception as e:
            print(f"[erreur IA] {e}\n")
            continue
        print(f"\nEffi-Market > {answer}\n")


if __name__ == "__main__":
    main()
