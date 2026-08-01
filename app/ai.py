"""Couche IA conversationnelle — interchangeable.

Moteurs disponibles :
  - "groq"   : Groq / Llama 3.3 (gratuit, sans facturation) — DÉFAUT
  - "gemini" : Google Gemini (nécessite la facturation activée)

Principe commun : l'IA ne connaît PAS le catalogue. Elle dispose d'un OUTIL
`rechercher_produits(requete)` qu'elle appelle elle-même (function calling)
autant de fois que nécessaire, lit les résultats, puis rédige sa réponse.
Elle ne peut donc jamais inventer un produit ou un lien.

Pour ajouter un moteur : implémenter `new_chat()` + `reply()` et l'enregistrer
dans `get_provider()`. Le reste de l'application n'a pas à changer.
"""
from __future__ import annotations

import json
from typing import Protocol

from app import config
from app.catalog import Catalog

SYSTEM_PROMPT = """Tu es l'assistant commercial de la marketplace Effi-Market \
(https://effi-market.com), spécialisée dans les produits et services afro-caribéens \
(alimentation, beauté & bien-être, mode africaine, art & culture, maison, services).

Ton rôle : aider le client, par WhatsApp, à trouver le produit qu'il cherche et lui \
donner le lien.

Règles :
- Réponds toujours en français, sur un ton chaleureux, poli et concis (messages courts, \
adaptés à WhatsApp).
- Pour trouver un produit, utilise TOUJOURS l'outil `rechercher_produits`. Choisis des \
mots-clés pertinents (nom du produit, catégorie). Tu peux l'appeler plusieurs fois avec \
des mots différents si le premier essai ne donne rien.
- N'invente JAMAIS un produit, un prix ou un lien. Utilise uniquement ce que l'outil renvoie.
- Si l'outil ne renvoie rien, ne dis pas simplement « non » : demande une précision ou \
propose de reformuler (couleur, taille, usage, catégorie…).
- Si la demande est vague, pose une petite question pour cerner le besoin avant de chercher.
- Reste dans ton rôle d'assistant Effi-Market ; ne réponds pas aux sujets hors marketplace.

PRÉSENTATION DES PRODUITS (très important — WhatsApp avec photos) :
- Quand tu proposes des produits, ta réponse doit contenir EXACTEMENT deux parties :
  1. Une courte phrase d'accroche chaleureuse (une seule ligne).
  2. Sur une NOUVELLE ligne, le marqueur littéral ###PRODUITS### suivi des LIENS des \
produits à montrer (3 maximum, les plus pertinents), séparés par «  |  ».
- Exemple de réponse produits :
  Voici de belles options pour hydrater vos cheveux ! 🌿
  ###PRODUITS### https://effi-market.com/produit/aaa/ | https://effi-market.com/produit/bbb/
- N'écris PAS toi-même le nom, le prix, la description ni le mot « lien » : le nom, le \
prix, la photo et le lien de chaque produit seront ajoutés AUTOMATIQUEMENT sous forme \
d'une image avec légende. Tu ne fournis que l'accroche + les liens après le marqueur.
- Utilise uniquement des liens EXACTEMENT tels que l'outil `rechercher_produits` te les a \
renvoyés (champ « lien »). N'invente ni ne modifie aucun lien.
- Si AUCUN produit ne convient, ou si tu poses une question de clarification, ou pour \
saluer/discuter : réponds normalement en texte, SANS le marqueur ###PRODUITS###.
- Pas de tableau ni de markdown complexe : WhatsApp n'affiche que *gras*, _italique_ et emojis."""

# Description de l'outil, réutilisée par les deux moteurs.
TOOL_NAME = "rechercher_produits"
TOOL_DESCRIPTION = (
    "Recherche des produits dans le catalogue Effi-Market à partir de mots-clés "
    "en français (nom du produit ou catégorie)."
)
TOOL_PARAM_DESCRIPTION = (
    "Mots-clés du produit à chercher (ex: 'beurre de karité', 'djembé', "
    "'robe en pagne', 'café')."
)


def run_search(catalog: Catalog, requete: str) -> str:
    """Exécute la recherche et renvoie un JSON que l'IA saura lire. Logique partagée."""
    results = catalog.search(requete, limit=5)
    if not results:
        return json.dumps(
            {"produits": [], "message": f"Aucun résultat pour « {requete} »"},
            ensure_ascii=False,
        )
    produits = [
        {
            "nom": p.name,
            "prix": p.price,
            "categorie": p.category,
            "marque": p.brand,
            "description": p.description,
            "lien": p.url,
        }
        for p, _score in results
    ]
    return json.dumps({"produits": produits}, ensure_ascii=False)


class AIProvider(Protocol):
    """Interface commune à tous les moteurs IA.

    L'HISTORIQUE est NEUTRE : une liste de messages {"role": "user"/"assistant",
    "content": "<texte>"} — indépendante du fournisseur. Chaque provider le
    convertit dans son propre format à chaque appel et NE LE MODIFIE PAS.
    C'est ce qui permet la bascule automatique : n'importe quel moteur peut
    reprendre le fil, quel que soit celui qui a répondu au tour précédent.
    """

    label: str

    def new_chat(self) -> list: ...
    def reply(self, history: list, user_message: str) -> str: ...


def _neutral(history: list) -> list:
    """Copie défensive de l'historique neutre (user/assistant en texte)."""
    return [{"role": h["role"], "content": h["content"]} for h in history]


# --- Base commune aux API au format OpenAI (Groq, OpenAI…) -------------------
class _OpenAICompatProvider:
    """Boucle d'appel d'outil pour toute API au format OpenAI (Groq, OpenAI).

    Ne modifie pas l'historique neutre : il construit une liste de messages
    locale à chaque appel et renvoie seulement le texte final.
    """

    label = "openai-compat"

    def __init__(self, catalog: Catalog, client, model_name: str):
        self.catalog = catalog
        self.client = client
        self.model_name = model_name
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": TOOL_DESCRIPTION,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requete": {"type": "string", "description": TOOL_PARAM_DESCRIPTION}
                        },
                        "required": ["requete"],
                    },
                },
            }
        ]

    def new_chat(self) -> list:
        return []

    def reply(self, history: list, user_message: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(_neutral(history))
        messages.append({"role": "user", "content": user_message})

        for _ in range(6):  # garde-fou anti-boucle infinie
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=0.3,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return (msg.content or "").strip()

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_search(self.catalog, args.get("requete", ""))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        return "Désolé, je n'ai pas réussi à traiter votre demande. Pouvez-vous reformuler ?"


# --- Groq (gratuit, limité) --------------------------------------------------
class GroqProvider(_OpenAICompatProvider):
    label = "Groq"

    def __init__(self, catalog: Catalog, api_key: str, model_name: str):
        if not api_key:
            raise ValueError("GROQ_API_KEY manquante")
        from groq import Groq

        super().__init__(catalog, Groq(api_key=api_key), model_name)


# --- OpenAI (payant, fiable) -------------------------------------------------
class OpenAIProvider(_OpenAICompatProvider):
    label = "OpenAI"

    def __init__(self, catalog: Catalog, api_key: str, model_name: str):
        if not api_key:
            raise ValueError("OPENAI_API_KEY manquante")
        from openai import OpenAI

        super().__init__(catalog, OpenAI(api_key=api_key), model_name)


# --- Claude / Anthropic (payant) ---------------------------------------------
class AnthropicProvider:
    """Format Messages d'Anthropic : le prompt système est séparé, et les
    appels d'outil utilisent des blocs `tool_use` / `tool_result`.
    """

    label = "Claude"

    def __init__(self, catalog: Catalog, api_key: str, model_name: str):
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY manquante")
        from anthropic import Anthropic

        self.catalog = catalog
        self.model_name = model_name
        self.client = Anthropic(api_key=api_key)
        self.tools = [
            {
                "name": TOOL_NAME,
                "description": TOOL_DESCRIPTION,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "requete": {"type": "string", "description": TOOL_PARAM_DESCRIPTION}
                    },
                    "required": ["requete"],
                },
            }
        ]

    def new_chat(self) -> list:
        return []

    def reply(self, history: list, user_message: str) -> str:
        messages = _neutral(history)
        messages.append({"role": "user", "content": user_message})

        for _ in range(6):
            resp = self.client.messages.create(
                model=self.model_name,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=self.tools,
            )
            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text").strip()

            # L'IA demande une ou plusieurs recherches.
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for b in resp.content:
                if b.type == "tool_use":
                    requete = b.input.get("requete", "") if isinstance(b.input, dict) else ""
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": run_search(self.catalog, requete),
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

        return "Désolé, je n'ai pas réussi à traiter votre demande. Pouvez-vous reformuler ?"


# --- Bascule automatique (fallback) ------------------------------------------
class FallbackProvider:
    """Essaie les moteurs dans l'ordre de priorité ; si l'un est indisponible
    (limite atteinte, panne, clé invalide…), passe automatiquement au suivant.
    """

    label = "fallback"

    def __init__(self, providers: list):
        if not providers:
            raise ValueError("Aucun moteur IA disponible pour la bascule.")
        self.providers = providers

    def new_chat(self) -> list:
        return []

    def reply(self, history: list, user_message: str) -> str:
        last_err: Exception | None = None
        for p in self.providers:
            try:
                return p.reply(history, user_message)
            except Exception as e:  # limite atteinte, panne réseau, clé HS…
                last_err = e
                print(f"[IA bascule] {p.label} indisponible → moteur suivant. ({e})")
        raise RuntimeError(f"Tous les moteurs IA sont indisponibles. Dernière erreur : {last_err}")


# Ordre de priorité et fabrique de chaque moteur (uniquement si sa clé existe).
_PROVIDER_ORDER = ["groq", "openai", "anthropic"]


def _make_provider(name: str, catalog: Catalog):
    if name == "groq" and config.GROQ_API_KEY:
        return GroqProvider(catalog, config.GROQ_API_KEY, config.GROQ_MODEL)
    if name == "openai" and config.OPENAI_API_KEY:
        return OpenAIProvider(catalog, config.OPENAI_API_KEY, config.OPENAI_MODEL)
    if name == "anthropic" and config.ANTHROPIC_API_KEY:
        return AnthropicProvider(catalog, config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
    return None


def get_provider(catalog: Catalog) -> AIProvider:
    """Fabrique le moteur IA selon AI_PROVIDER.

    "auto" (défaut) : chaîne de bascule Groq → OpenAI → Claude, en n'incluant
    que les moteurs dont la clé est renseignée. Sinon, un moteur unique imposé.
    """
    prov = config.AI_PROVIDER
    if prov in ("auto", "fallback"):
        chain = [p for p in (_make_provider(n, catalog) for n in _PROVIDER_ORDER) if p]
        if not chain:
            raise ValueError(
                "Aucune clé IA configurée (GROQ_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)."
            )
        return chain[0] if len(chain) == 1 else FallbackProvider(chain)

    single = _make_provider(prov, catalog)
    if single is None:
        raise ValueError(
            f"AI_PROVIDER='{prov}' inconnu ou sans clé. "
            "Valeurs : 'auto', 'groq', 'openai', 'anthropic'."
        )
    return single
