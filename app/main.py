"""Serveur FastAPI — webhook WhatsApp Cloud API.

Deux routes :
  GET  /webhook  : vérification du webhook par Meta (handshake initial).
  POST /webhook  : réception des messages entrants → réponse de l'IA → envoi WhatsApp.

Lancement (local) :
    uvicorn app.main:app --reload --port 8000
Puis exposer en HTTPS avec ngrok :
    ngrok http 8000
et configurer l'URL ngrok + le "verify token" dans Meta for Developers.
"""
from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, Request, Response

from app import config, whatsapp
from app.ai import get_provider
from app.catalog import Catalog
from app.conversations import ConversationStore

app = FastAPI(title="Effi-Market WhatsApp Bot")

# Chargé une fois au démarrage.
catalog = Catalog.load(config.CATALOG_PATH)
provider = get_provider(catalog)
store = ConversationStore(provider)

# Dédup : Meta réémet parfois le même message ; on ignore les IDs déjà traités.
_seen_message_ids: set[str] = set()


@app.get("/")
def health():
    return {
        "status": "ok",
        "produits": len(catalog),
        "ia": config.AI_PROVIDER,
        "whatsapp": "configuré" if whatsapp.is_configured() else "mode MOCK",
        "sessions_actives": store.active_count,
    }


@app.get("/webhook")
def verify_webhook(request: Request):
    """Handshake Meta : renvoyer le hub.challenge si le verify_token correspond."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge or "", media_type="text/plain")
    return Response(content="Verification échouée", status_code=403)


def _handle_message(sender: str, text: str) -> None:
    """Génère la réponse de l'IA et l'envoie. Exécuté en tâche de fond."""
    try:
        answer = store.reply(sender, text)
    except Exception as e:
        print(f"[IA ERREUR] {e}")
        answer = "Désolé, un souci technique est survenu. Réessayez dans un instant 🙏"
    whatsapp.send_text(sender, answer)


@app.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    """Reçoit les événements WhatsApp. On répond 200 tout de suite, on traite en fond."""
    data = await request.json()

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                # On ne traite que les messages texte pour l'instant.
                if message.get("type") != "text":
                    continue
                msg_id = message.get("id", "")
                if msg_id in _seen_message_ids:
                    continue
                _seen_message_ids.add(msg_id)

                sender = message.get("from", "")
                text = message.get("text", {}).get("body", "").strip()
                if sender and text:
                    print(f"[Reçu de {sender}] {text}")
                    background.add_task(_handle_message, sender, text)

    return Response(content="EVENT_RECEIVED", media_type="text/plain")
