"""Gestion des conversations, une par numéro WhatsApp.

Chaque utilisateur (identifié par son numéro) a son propre fil de discussion,
donc l'IA garde le contexte de CE client sans mélanger avec les autres.

- Isolation : un fil par numéro.
- Expiration : après SESSION_TTL_MINUTES d'inactivité, on repart de zéro
  (le client qui revient le lendemain ne reprend pas une vieille conversation).
- Réinitialisation manuelle : la commande « recommencer » efface le fil.

Stockage en mémoire (dictionnaire). Suffisant pour la V1 : les sessions sont
courtes et l'expiration nettoie toute seule. La persistance sur disque pourra
être ajoutée plus tard si besoin.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app import config
from app.ai import AIProvider

# Mots (message entier, normalisé) qui réinitialisent la conversation.
RESET_KEYWORDS = {"recommencer", "reset", "restart", "menu", "annuler"}


@dataclass
class _Session:
    chat: object
    last_activity: float


class ConversationStore:
    def __init__(self, provider: AIProvider, ttl_minutes: int | None = None):
        self.provider = provider
        self.ttl_seconds = (ttl_minutes if ttl_minutes is not None else config.SESSION_TTL_MINUTES) * 60
        self._sessions: dict[str, _Session] = {}

    def _get_session(self, user_id: str) -> _Session:
        """Renvoie la session de l'utilisateur, en créant/renouvelant si expirée."""
        now = time.time()
        sess = self._sessions.get(user_id)
        if sess is None or (now - sess.last_activity) > self.ttl_seconds:
            sess = _Session(chat=self.provider.new_chat(), last_activity=now)
            self._sessions[user_id] = sess
        return sess

    def reset(self, user_id: str) -> None:
        """Efface le fil d'un utilisateur (repart de zéro)."""
        self._sessions.pop(user_id, None)

    def reply(self, user_id: str, message: str) -> str:
        """Traite un message d'un utilisateur et renvoie la réponse de l'IA."""
        if message.strip().lower() in RESET_KEYWORDS:
            self.reset(user_id)
            return ("C'est reparti sur de nouvelles bases ! 🌿 "
                    "Que recherchez-vous sur Effi-Market ?")

        sess = self._get_session(user_id)
        answer = self.provider.reply(sess.chat, message)
        sess.last_activity = time.time()
        return answer

    def cleanup_expired(self) -> int:
        """Supprime les sessions inactives. Renvoie le nombre supprimé."""
        now = time.time()
        expired = [uid for uid, s in self._sessions.items()
                   if (now - s.last_activity) > self.ttl_seconds]
        for uid in expired:
            del self._sessions[uid]
        return len(expired)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
