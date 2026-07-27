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

from collections import deque

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
# Borné : on ne garde que les N derniers IDs (au-delà, un doublon si vieux est
# improbable) pour éviter une croissance mémoire sans fin.
_SEEN_MAX = 2000
_seen_ids_order: deque[str] = deque(maxlen=_SEEN_MAX)
_seen_message_ids: set[str] = set()


def _already_seen(msg_id: str) -> bool:
    """Vrai si l'ID a déjà été traité ; sinon le mémorise (en bornant la taille)."""
    if msg_id in _seen_message_ids:
        return True
    if len(_seen_ids_order) == _SEEN_MAX:
        _seen_message_ids.discard(_seen_ids_order[0])  # sera évincé par le maxlen
    _seen_ids_order.append(msg_id)
    _seen_message_ids.add(msg_id)
    return False


@app.get("/")
def health():
    return {
        "status": "ok",
        "produits": len(catalog),
        "ia": config.AI_PROVIDER,
        "whatsapp": "configuré" if whatsapp.is_configured() else "mode MOCK",
        "sessions_actives": store.active_count,
    }


@app.get("/ping")
def ping():
    """Point d'entrée ultra-léger pour le maintien en éveil (keep-alive).

    Renvoie 2 octets de texte brut : idéal pour un service de ping externe
    (cron-job.org…) qui limite la taille de réponse acceptée.
    """
    return Response(content="ok", media_type="text/plain")


@app.get("/admin/diag")
def admin_diag(request: Request):
    """Diagnostic de la liaison Meta. Protégé par ?key=<verify_token>.

    Exemple : /admin/diag?key=...&waba=<WHATSAPP_BUSINESS_ACCOUNT_ID>
    Vérifie et, si besoin, abonne le compte WhatsApp Business à l'application.
    """
    params = request.query_params
    if params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    try:
        report = whatsapp.diagnose(params.get("waba", "").strip())
    except Exception as e:
        return {"erreur": str(e)}
    return report


@app.get("/admin/testsend")
def admin_testsend(request: Request):
    """Teste l'envoi (template + texte libre). Protégé par ?key=<verify_token>.

    Exemple : /admin/testsend?key=...&to=33752565659
    """
    params = request.query_params
    if params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    to = params.get("to", "").strip()
    if not to:
        return {"erreur": "Fournir ?to=<numero international sans +>"}
    try:
        return whatsapp.test_send(to)
    except Exception as e:
        return {"erreur": str(e)}


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
    # L'envoi peut échouer (token, numéro non autorisé…) : on le rattrape ici pour
    # garder un log lisible, sans laisser remonter une pile d'appels illisible.
    try:
        whatsapp.send_text(sender, answer)
    except Exception as e:
        print(f"[ENVOI ÉCHOUÉ vers {sender}] {e}")


@app.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    """Reçoit les événements WhatsApp. On répond 200 tout de suite, on traite en fond."""
    data = await request.json()

    # Nettoyage opportuniste des sessions expirées (évite l'accumulation).
    store.cleanup_expired()

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                # On ne traite que les messages texte pour l'instant.
                if message.get("type") != "text":
                    continue
                msg_id = message.get("id", "")
                if not msg_id or _already_seen(msg_id):
                    continue

                sender = message.get("from", "")
                text = message.get("text", {}).get("body", "").strip()
                if sender and text:
                    print(f"[Reçu de {sender}] {text}")
                    background.add_task(_handle_message, sender, text)

    return Response(content="EVENT_RECEIVED", media_type="text/plain")
