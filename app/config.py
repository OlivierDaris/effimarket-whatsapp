"""Configuration centrale : lit le fichier .env (si présent) et l'environnement."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- Console Windows en UTF-8 ------------------------------------------------
# Évite les crashs d'affichage (cp1252) sur accents et symboles, aussi bien en
# ligne de commande que dans les logs du serveur uvicorn.
for _stream in (sys.stdout, sys.stderr):
    try:
        # line_buffering=True : les logs du serveur s'affichent immédiatement.
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

# --- Correctif SSL Windows ---------------------------------------------------
# Sur Windows, un antivirus/proxy peut inspecter le HTTPS avec son propre
# certificat racine, que Python ne connaît pas (erreur CERTIFICATE_VERIFY_FAILED).
# truststore fait utiliser à Python le magasin de certificats de Windows.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from dotenv import load_dotenv

# Racine du projet (dossier qui contient ce fichier app/)
ROOT = Path(__file__).resolve().parent.parent

# Charge .env s'il existe (sans écraser les variables déjà définies dans l'environnement)
load_dotenv(ROOT / ".env")


def _path(value: str) -> Path:
    """Résout un chemin relatif par rapport à la racine du projet."""
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p)


# --- Catalogue ---
CATALOG_PATH = _path(os.getenv("CATALOG_PATH", "data/sample_catalog.csv"))

# --- IA ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
# OpenAI (payant, fiable)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# Groq (gratuit, par défaut)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Gemini (alternative)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- Conversations ---
# Après ce délai d'inactivité, la conversation d'un utilisateur repart de zéro.
SESSION_TTL_MINUTES = int(os.getenv("SESSION_TTL_MINUTES", "30"))

# --- WhatsApp ---
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "effimarket_verify_2026")
