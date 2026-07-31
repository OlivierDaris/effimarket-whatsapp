"""Récupération de la photo d'un produit depuis sa page effi-market.

Les pages WordPress/WooCommerce exposent la photo principale via la balise
meta `og:image`. On la lit à la volée depuis le lien du produit, et on met
le résultat en cache (pour ne fetcher chaque page qu'une seule fois).

Le serveur d'hébergement (Render) a accès à Internet ; c'est donc lui qui
récupère les images, pas le catalogue Excel (qui n'a pas de colonne image).
"""
from __future__ import annotations

import re

import httpx

# Deux ordres possibles des attributs (property avant/après content).
_OG_RE_A = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
_OG_RE_B = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', re.I
)
# Repli : première image du dossier d'upload WordPress.
_IMG_RE = re.compile(
    r'https://[^"\' ]*wp-content/uploads/[^"\' ]+\.(?:jpg|jpeg|png|webp)', re.I
)

_cache: dict[str, str | None] = {}


def get_image(link: str) -> str | None:
    """Renvoie l'URL de la photo du produit (ou None). Mise en cache."""
    if not link:
        return None
    if link in _cache:
        return _cache[link]

    image: str | None = None
    try:
        with httpx.Client(
            timeout=12,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EffimarketBot/1.0)"},
        ) as client:
            resp = client.get(link)
            if resp.status_code == 200:
                html = resp.text
                m = _OG_RE_A.search(html) or _OG_RE_B.search(html)
                if m:
                    image = m.group(1).strip()
                else:
                    m = _IMG_RE.search(html)
                    if m:
                        image = m.group(0)
    except Exception:
        image = None

    _cache[link] = image
    return image
