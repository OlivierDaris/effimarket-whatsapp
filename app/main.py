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

import json
import threading

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import ai, config, dashboard, product_image, whatsapp
from app.catalog import Catalog
from app.conversations import ConversationStore
from app.stats import Stats

# Marqueur émis par l'IA pour signaler les produits à afficher en photos.
PRODUCTS_MARKER = "###PRODUITS###"

app = FastAPI(title="Effi-Market WhatsApp Bot")

# Chargé une fois au démarrage.
catalog = Catalog.load(config.CATALOG_PATH)
provider = ai.get_provider(catalog)
store = ConversationStore(provider)
stats = Stats(config.STATS_PATH)

# Numéro du client en cours de traitement (par thread), pour associer une
# recherche infructueuse à son auteur (zone « À rappeler »).
_ctx = threading.local()


def _on_search(query: str, found: bool) -> None:
    stats.record_search(query, found)
    if not found:
        stats.record_missed(getattr(_ctx, "sender", ""), query)


ai.on_search = _on_search

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


@app.get("/admin/testimage")
def admin_testimage(request: Request):
    """Teste l'extraction de la photo d'un produit. Protégé par ?key=<verify_token>.

    Exemple : /admin/testimage?key=...&url=https://effi-market.com/produit/xxx/
    """
    from app import product_image

    params = request.query_params
    if params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    url = params.get("url", "").strip()
    if not url:
        # à défaut, teste le premier produit du catalogue qui a un lien
        url = next((p.url for p in catalog.products if p.url), "")
    return {"produit": url, "image": product_image.get_image(url)}


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


@app.get("/dashboard")
def dashboard_page(request: Request):
    """Tableau de bord d'activité (lu depuis data/stats.json).

    Protégé par ?key=<verify_token> : ouvrez
    https://.../dashboard?key=effimarket_verify_2026
    """
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)

    # Produits jamais proposés (trous de mise en avant du catalogue).
    shown = stats.product_names()
    never = [p.name for p in catalog.products if p.name not in shown]
    never_info = {"count": len(never), "total": len(catalog.products), "sample": never[:15]}

    # Statut : moteur(s) IA actif(s) + WhatsApp.
    if isinstance(provider, ai.FallbackProvider):
        ai_label = " → ".join(p.label for p in provider.providers)
    else:
        ai_label = getattr(provider, "label", config.AI_PROVIDER)
    status = {
        "ai": ai_label,
        "whatsapp": "configuré" if whatsapp.is_configured() else "mode MOCK",
    }

    return HTMLResponse(
        content=dashboard.render(stats.summary(), config.WHATSAPP_VERIFY_TOKEN, never_info, status)
    )


@app.get("/dashboard/client")
def dashboard_client(request: Request):
    """Rapport détaillé d'un client. ?key=<verify_token>&num=<numero>."""
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    num = request.query_params.get("num", "").strip()
    rep = stats.report(num)
    if rep is None:
        back = f"/dashboard?key={config.WHATSAPP_VERIFY_TOKEN}"
        return HTMLResponse(
            f"<p>Client inconnu.</p><p><a href='{back}'>← Retour au tableau de bord</a></p>",
            status_code=404,
        )
    return HTMLResponse(content=dashboard.render_client(rep, config.WHATSAPP_VERIFY_TOKEN))


@app.get("/dashboard/export-clients")
def dashboard_export_clients(request: Request):
    """Exporte la liste des clients en CSV (numéro, messages, premier, dernier)."""
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    import csv
    import io

    buf = io.StringIO()
    buf.write("﻿")  # BOM pour Excel (accents)
    w = csv.writer(buf)
    w.writerow(["numero", "messages", "premier_contact", "dernier_contact", "lien_whatsapp"])
    for u in stats.summary()["users"]:
        w.writerow([u["num"], u["count"], u.get("first") or "", u.get("last") or "", f"https://wa.me/{u['num']}"])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=effimarket-clients.csv"},
    )


@app.get("/admin")
def admin_page(request: Request):
    """Page Admin/Réglages : sauvegarde/restauration + outils. ?key=<verify_token>."""
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    return HTMLResponse(
        content=dashboard.render_admin(config.WHATSAPP_VERIFY_TOKEN, config.WHATSAPP_WABA_ID)
    )


@app.get("/admin/logs")
def admin_logs(request: Request):
    """Renvoie les derniers logs du serveur (texte brut). ?key=<verify_token>."""
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    from app import logbuf

    return Response(content=logbuf.text(400), media_type="text/plain; charset=utf-8")


@app.get("/dashboard/export")
def dashboard_export(request: Request):
    """Télécharge data/stats.json (sauvegarde avant un déploiement)."""
    if request.query_params.get("key") != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    return Response(
        content=stats.raw_json(),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=effimarket-stats.json"},
    )


@app.post("/dashboard/import")
async def dashboard_import(key: str = Form(""), file: UploadFile = File(...)):
    """Recharge les données depuis un JSON importé (restauration après déploiement)."""
    if key != config.WHATSAPP_VERIFY_TOKEN:
        return Response(content="Accès refusé", status_code=403)
    back = f"/dashboard?key={config.WHATSAPP_VERIFY_TOKEN}"
    try:
        raw = await file.read()
        stats.replace(json.loads(raw.decode("utf-8")))
    except Exception as e:
        return HTMLResponse(
            f"<p>Import échoué : {e}</p><p><a href='{back}'>← Retour au tableau de bord</a></p>",
            status_code=400,
        )
    return RedirectResponse(url=back, status_code=303)


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


def _safe_send_text(sender: str, body: str) -> None:
    try:
        whatsapp.send_text(sender, body)
    except Exception as e:
        print(f"[ENVOI ÉCHOUÉ vers {sender}] {e}")


def _product_caption(product) -> str:
    """Légende d'une fiche produit (sous la photo)."""
    lines = [f"*{product.name}*"]
    if product.price:
        lines.append(f"💰 {product.price}")
    if product.url:
        lines.append(f"🔗 {product.url}")
    return "\n".join(lines)


def _send_products(sender: str, links: list[str]) -> int:
    """Envoie une photo (ou une fiche texte en repli) pour chaque produit. Renvoie le nb envoyé."""
    sent = 0
    shown: list[tuple[str, str]] = []
    for link in links[:3]:
        product = catalog.by_link(link)
        if product is None:
            continue
        shown.append((product.name, product.url))
        caption = _product_caption(product)
        image = product_image.get_image(product.url)
        try:
            if image:
                whatsapp.send_image(sender, image, caption)
            else:
                whatsapp.send_text(sender, caption)  # repli si pas de photo
            sent += 1
        except Exception as e:
            print(f"[ENVOI produit échoué] {e}")
            _safe_send_text(sender, caption)  # dernier repli : la fiche en texte
    stats.record_products(sender, shown)
    return sent


def _handle_message(sender: str, text: str) -> None:
    """Génère la réponse de l'IA et l'envoie. Exécuté en tâche de fond."""
    stats.record_message(sender, text)
    _ctx.sender = sender  # pour associer une recherche sans résultat à ce client
    try:
        answer = store.reply(sender, text)
    except Exception as e:
        print(f"[IA ERREUR] {e}")
        _safe_send_text(sender, "Désolé, un souci technique est survenu. Réessayez dans un instant 🙏")
        return

    # Réponse avec produits : intro en texte + une photo par produit.
    if PRODUCTS_MARKER in answer:
        intro, _, rest = answer.partition(PRODUCTS_MARKER)
        intro = intro.strip()
        links = [l.strip() for l in rest.split("|") if l.strip()]
        if intro:
            _safe_send_text(sender, intro)
        sent = _send_products(sender, links)
        if sent == 0 and not intro:
            _safe_send_text(sender, "Désolé, je n'ai pas pu afficher ces produits. Pouvez-vous reformuler ?")
    else:
        _safe_send_text(sender, answer)


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
