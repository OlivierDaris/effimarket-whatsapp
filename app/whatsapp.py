"""Envoi de messages via l'API WhatsApp Cloud (Meta Graph API).

Mode MOCK : si WHATSAPP_TOKEN n'est pas renseigné dans le .env, on n'appelle
pas Meta — on affiche simplement la réponse dans la console. Pratique pour
tester tout le pipeline en local avant d'avoir configuré Meta.
"""
from __future__ import annotations

import httpx

from app import config

GRAPH_API_VERSION = "v21.0"
GRAPH_API = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# WhatsApp limite un message texte à 4096 caractères.
MAX_LEN = 4096


def is_configured() -> bool:
    return bool(config.WHATSAPP_TOKEN and config.WHATSAPP_PHONE_ID)


def send_text(to: str, body: str) -> None:
    """Envoie un message texte au numéro `to` (format international sans '+')."""
    body = body[:MAX_LEN]

    if not is_configured():
        # Mode MOCK : pas d'identifiants Meta → on log au lieu d'envoyer.
        print(f"[MOCK WhatsApp → {to}]\n{body}\n")
        return

    url = f"{GRAPH_API}/{config.WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": True, "body": body},
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            print(f"[WhatsApp ERREUR {resp.status_code}] {resp.text}")
        resp.raise_for_status()


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"}


def diagnose(waba_id: str) -> dict:
    """Diagnostic de la liaison Meta (sans exposer le token).

    Vérifie : (1) le token voit bien le numéro, (2) le compte WhatsApp Business
    (WABA) est-il abonné à cette application ? Si non, tente de l'abonner.
    Renvoie un rapport lisible.
    """
    report: dict = {"phone_number_id": config.WHATSAPP_PHONE_ID, "waba_id": waba_id}
    with httpx.Client(timeout=20, headers=_auth_headers()) as client:
        # 1) Le token est-il valide et voit-il le numéro ?
        r = client.get(f"{GRAPH_API}/{config.WHATSAPP_PHONE_ID}",
                       params={"fields": "display_phone_number,verified_name,quality_rating"})
        report["numero"] = r.json()

        if not waba_id:
            report["erreur"] = "Fournir ?waba=<WHATSAPP_BUSINESS_ACCOUNT_ID>"
            return report

        # 2) Quelles apps sont abonnées à cette WABA ?
        r = client.get(f"{GRAPH_API}/{waba_id}/subscribed_apps")
        avant = r.json()
        report["subscribed_apps_avant"] = avant

        # 3) Abonner NOTRE app (celle du token). Idempotent : la présence d'autres
        #    apps (ex : l'app de test 1P de Meta) ne veut PAS dire que la nôtre l'est.
        r = client.post(f"{GRAPH_API}/{waba_id}/subscribed_apps")
        report["action_abonnement"] = {"status": r.status_code, "reponse": r.json()}

        # 4) Revérifier
        r = client.get(f"{GRAPH_API}/{waba_id}/subscribed_apps")
        report["subscribed_apps_apres"] = r.json()

    return report
