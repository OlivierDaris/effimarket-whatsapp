"""Rendu HTML du tableau de bord + de la page Admin/Réglages (Material 3, dark).

Les gabarits sont statiques ; on les remplit avec les vraies statistiques et on
câble les boutons (Sauvegarder / Charger) et les outils. Les fragments dynamiques
sont des jetons %%...%% remplacés par les fonctions render() — on n'utilise pas
.format()/f-string sur les gabarits pour ne pas doubler les accolades du CSS.
"""
from __future__ import annotations

import html
from datetime import datetime


def _esc(x) -> str:
    return html.escape(str(x))


def _fmt_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m %H:%M")
    except Exception:
        return _esc(iso)


# En-tête commun (doctype + <head> avec Tailwind CDN, polices, config, style).
_HEAD = """<!DOCTYPE html>
<html class="dark" lang="fr"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>%%TITLE%%</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Hanken+Grotesk:wght@600;700&family=Geist:wght@500&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script id="tailwind-config">
  tailwind.config = {
    darkMode: "class",
    theme: { extend: {
      colors: {
        "on-surface": "#e4e1e6", "primary": "#d0bcff", "secondary": "#ccbeff",
        "on-surface-variant": "#cbc3d7", "surface-container-low": "#1b1b1e",
        "on-primary": "#3c0091", "background": "#131316", "outline-variant": "#494454",
        "error-container": "#93000a", "surface-container-lowest": "#0e0e11",
        "surface": "#131316", "surface-container-high": "#2a2a2d", "outline": "#958ea0",
        "error": "#ffb4ab", "surface-container": "#1f1f22", "surface-variant": "#353438",
        "secondary-container": "#4a3d7c", "on-secondary-container": "#baabf3",
        "on-error-container": "#ffdad6", "tertiary": "#c4c1fb"
      },
      borderRadius: { "DEFAULT":"0.125rem","lg":"0.25rem","xl":"0.5rem","full":"0.75rem" },
      spacing: { "base":"8px","container-max":"1280px","gutter":"24px" },
      fontFamily: {
        "body-md":["Inter"],"body-sm":["Inter"],"label-md":["Geist"],"label-sm":["Geist"],
        "headline-md":["Hanken Grotesk"],"headline-sm":["Hanken Grotesk"]
      },
      fontSize: {
        "headline-md":["32px",{"lineHeight":"40px","fontWeight":"600"}],
        "label-md":["14px",{"lineHeight":"16px","letterSpacing":"0.05em","fontWeight":"500"}],
        "body-md":["16px",{"lineHeight":"24px","fontWeight":"400"}],
        "body-sm":["14px",{"lineHeight":"20px","fontWeight":"400"}],
        "label-sm":["12px",{"lineHeight":"14px","letterSpacing":"0.03em","fontWeight":"500"}],
        "headline-sm":["24px",{"lineHeight":"32px","fontWeight":"600"}]
      }
    } }
  }
</script>
<style>
  .material-symbols-outlined { font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24; display:inline-block; }
  .filled-icon { font-variation-settings:'FILL' 1; }
  body { background-color:#131316; font-family:'Inter',sans-serif; color:#e4e1e6; min-height:100dvh; }
  .bento-grid { display:grid; grid-template-columns:repeat(12,1fr); gap:24px; }
  .card-shadow { box-shadow:0 4px 20px rgba(0,0,0,0.2); }
  .fld { background:#2a2a2d; color:#e4e1e6; border:1px solid rgba(73,68,84,.5); border-radius:.5rem; padding:.55rem .8rem; outline:none; }
  .fld:focus { border-color:#d0bcff; }
</style>
</head>
"""

# Bouton "Charger" (upload) réutilisé dans les deux pages.
_UPLOAD = """<form action="/dashboard/import" method="post" enctype="multipart/form-data">
    <input type="hidden" name="key" value="%%K%%"/>
    <label class="bg-primary text-on-primary px-4 py-2 rounded-xl flex items-center gap-2 hover:bg-primary/90 transition-all active:scale-95 duration-100 cursor-pointer">
      <span class="material-symbols-outlined text-[20px]">upload_file</span>
      <span class="font-label-md text-label-md">Charger</span>
      <input type="file" name="file" accept=".json,application/json" class="hidden"
             onchange="if(this.files.length &amp;&amp; confirm('Remplacer les donnees actuelles par ce fichier ?')) this.form.submit(); else this.value='';"/>
    </label>
  </form>"""


# ---------------------------------------------------------------------------
# TABLEAU DE BORD
# ---------------------------------------------------------------------------
_BODY_DASHBOARD = """<body class="bg-background text-on-surface pb-10 md:pb-0">

<header class="bg-surface-container-low border-b border-white/5 fixed top-0 w-full z-50 flex justify-between items-center px-5 h-16">
  <div class="flex items-center gap-3">
    <span class="material-symbols-outlined text-primary">smart_toy</span>
    <h1 class="font-headline-sm text-headline-sm font-bold text-primary">Effi-Market Bot</h1>
  </div>
  <div class="flex items-center gap-3">
    <a href="/admin?key=%%K%%" title="Réglages / Admin" class="w-10 h-10 flex items-center justify-center rounded-xl text-on-surface-variant hover:text-primary hover:bg-white/5 transition-all">
      <span class="material-symbols-outlined">settings</span>
    </a>
    %%UPLOAD%%
  </div>
</header>

<main class="max-w-container-max mx-auto p-gutter space-y-gutter mt-20 md:pl-28">

  <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
    <div>
      <h2 class="font-headline-md text-headline-md text-primary">Tableau de bord</h2>
      <p class="font-body-md text-on-surface-variant">Depuis le %%STARTED%%</p>
    </div>
    <a href="/dashboard/export?key=%%K%%" class="flex items-center gap-2 px-4 py-2 bg-secondary-container text-on-secondary-container rounded-lg font-label-md text-label-md transition-all hover:brightness-110 active:scale-95">
      <span class="material-symbols-outlined text-[18px]">save</span> Sauvegarder
    </a>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-gutter">
    <div class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10 flex flex-col justify-between h-32">
      <span class="font-label-sm text-label-sm text-on-surface-variant uppercase">Messages reçus</span>
      <div class="flex items-end justify-between"><span class="text-[32px] font-bold text-primary">%%MSG%%</span>
        <span class="material-symbols-outlined text-primary opacity-20 text-[32px]">chat_bubble</span></div>
    </div>
    <div class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10 flex flex-col justify-between h-32">
      <span class="font-label-sm text-label-sm text-on-surface-variant uppercase">Clients uniques</span>
      <div class="flex items-end justify-between"><span class="text-[32px] font-bold text-primary">%%USERS%%</span>
        <span class="material-symbols-outlined text-primary opacity-20 text-[32px]">group</span></div>
    </div>
    <div class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10 flex flex-col justify-between h-32">
      <span class="font-label-sm text-label-sm text-on-surface-variant uppercase">Jours actifs</span>
      <div class="flex items-end justify-between"><span class="text-[32px] font-bold text-primary">%%DAYS%%</span>
        <span class="material-symbols-outlined text-primary opacity-20 text-[32px]">event_available</span></div>
    </div>
  </div>

  <section class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
    <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-primary">bar_chart</span>
      <h3 class="font-headline-sm text-headline-sm">Messages par jour</h3></div>
    <div class="h-64 flex items-end gap-6 md:gap-10 px-2 md:px-6 border-b border-outline-variant/30 pb-2 overflow-x-auto">%%BARS%%</div>
  </section>

  <div class="bento-grid">
    <section class="col-span-12 md:col-span-6 bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
      <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-primary">search</span>
        <h3 class="font-headline-sm text-headline-sm">Recherches les plus fréquentes</h3></div>
      <div class="overflow-x-auto"><table class="w-full"><thead><tr class="border-b border-outline-variant/20">
        <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">Recherche</th>
        <th class="text-right py-3 font-label-sm text-on-surface-variant uppercase">Nb</th></tr></thead>
        <tbody class="divide-y divide-outline-variant/10">%%QUERIES%%</tbody></table></div>
    </section>
    <section class="col-span-12 md:col-span-6 bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
      <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-primary">shopping_cart</span>
        <h3 class="font-headline-sm text-headline-sm">Produits les plus proposés</h3></div>
      <div class="overflow-x-auto"><table class="w-full"><thead><tr class="border-b border-outline-variant/20">
        <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">Produit</th>
        <th class="text-right py-3 font-label-sm text-on-surface-variant uppercase">Nb</th></tr></thead>
        <tbody class="divide-y divide-outline-variant/10">%%PRODUCTS%%</tbody></table></div>
    </section>
    <section class="col-span-12 md:col-span-8 bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
      <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-primary">contact_phone</span>
        <h3 class="font-headline-sm text-headline-sm">Numéros qui ont contacté le bot</h3></div>
      <div class="overflow-x-auto"><table class="w-full"><thead><tr class="border-b border-outline-variant/20">
        <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">Numéro</th>
        <th class="text-center py-3 font-label-sm text-on-surface-variant uppercase">Messages</th>
        <th class="text-right py-3 font-label-sm text-on-surface-variant uppercase">Dernier</th></tr></thead>
        <tbody class="divide-y divide-outline-variant/10">%%CLIENTS%%</tbody></table></div>
    </section>
    <section class="col-span-12 md:col-span-4 bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
      <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-error">search_off</span>
        <h3 class="font-headline-sm text-headline-sm">Recherches sans résultat</h3></div>
      <div class="space-y-2">%%FAILED%%</div>
    </section>
  </div>

  <section class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
    <div class="flex items-center gap-2 mb-6"><span class="material-symbols-outlined text-primary">forum</span>
      <h3 class="font-headline-sm text-headline-sm">Derniers messages</h3></div>
    <div class="overflow-x-auto"><table class="w-full"><thead><tr class="border-b border-outline-variant/20">
      <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">Quand</th>
      <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">De</th>
      <th class="text-left py-3 font-label-sm text-on-surface-variant uppercase">Message</th></tr></thead>
      <tbody class="divide-y divide-outline-variant/10">%%RECENT%%</tbody></table></div>
  </section>

  <p class="text-center text-on-surface-variant font-label-sm pt-2">Données lues depuis data/stats.json · remises à zéro au redéploiement (voir ⚙️ Réglages pour Sauvegarder / Charger).</p>
</main>

<aside class="hidden md:flex fixed left-0 top-16 bottom-0 w-20 flex-col items-center py-6 gap-4 bg-surface-container-low border-r border-white/5 z-40">
  <span class="w-12 h-12 flex items-center justify-center bg-primary text-on-primary rounded-xl shadow-lg"><span class="material-symbols-outlined filled-icon">dashboard</span></span>
  <a href="/admin?key=%%K%%" title="Réglages / Admin" class="w-12 h-12 flex items-center justify-center text-on-surface-variant hover:text-primary hover:bg-white/5 rounded-xl transition-all mt-auto"><span class="material-symbols-outlined">settings</span></a>
</aside>

<script>
  document.addEventListener('DOMContentLoaded',()=>{const b=document.querySelector('.bg-primary.rounded-t-lg');if(b){b.classList.add('animate-pulse');setTimeout(()=>b.classList.remove('animate-pulse'),2500);}});
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# PAGE ADMIN / RÉGLAGES
# ---------------------------------------------------------------------------
_BODY_ADMIN = """<body class="bg-background text-on-surface pb-10">

<header class="bg-surface-container-low border-b border-white/5 fixed top-0 w-full z-50 flex justify-between items-center px-5 h-16">
  <div class="flex items-center gap-3">
    <span class="material-symbols-outlined text-primary">settings</span>
    <h1 class="font-headline-sm text-headline-sm font-bold text-primary">Réglages — Admin</h1>
  </div>
  <a href="/dashboard?key=%%K%%" class="flex items-center gap-2 px-4 py-2 bg-secondary-container text-on-secondary-container rounded-xl font-label-md text-label-md hover:brightness-110 active:scale-95 transition-all">
    <span class="material-symbols-outlined text-[20px]">arrow_back</span> Tableau de bord
  </a>
</header>

<main class="max-w-3xl mx-auto p-gutter space-y-gutter mt-20">

  <section class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
    <div class="flex items-center gap-2 mb-4"><span class="material-symbols-outlined text-primary">database</span>
      <h3 class="font-headline-sm text-headline-sm">Sauvegarde de la base</h3></div>
    <p class="font-body-md text-on-surface-variant mb-5">Sur l'offre gratuite, le fichier <code>data/stats.json</code> est remis à zéro à chaque redéploiement. Pensez à <b>Sauvegarder</b> avant, puis <b>Charger</b> après.</p>
    <div class="flex flex-wrap items-center gap-3">
      <a href="/dashboard/export?key=%%K%%" class="bg-secondary-container text-on-secondary-container px-4 py-2 rounded-xl flex items-center gap-2 font-label-md text-label-md hover:brightness-110 active:scale-95 transition-all">
        <span class="material-symbols-outlined text-[20px]">save</span> Sauvegarder (télécharger)
      </a>
      %%UPLOAD%%
    </div>
  </section>

  <section class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
    <div class="flex items-center gap-2 mb-4"><span class="material-symbols-outlined text-primary">dashboard</span>
      <h3 class="font-headline-sm text-headline-sm">Liens rapides</h3></div>
    <div class="flex flex-wrap gap-3">
      <a href="/dashboard?key=%%K%%" class="fld hover:border-primary flex items-center gap-2 font-body-md"><span class="material-symbols-outlined text-[20px] text-primary">insights</span> Tableau de bord</a>
      <a href="/" target="_blank" class="fld hover:border-primary flex items-center gap-2 font-body-md"><span class="material-symbols-outlined text-[20px] text-primary">favorite</span> État du service</a>
      <a href="/admin/testimage?key=%%K%%" target="_blank" class="fld hover:border-primary flex items-center gap-2 font-body-md"><span class="material-symbols-outlined text-[20px] text-primary">image</span> Tester une photo produit</a>
    </div>
  </section>

  <section class="bg-surface-container-lowest p-6 rounded-xl card-shadow border border-outline-variant/10">
    <div class="flex items-center gap-2 mb-4"><span class="material-symbols-outlined text-primary">build</span>
      <h3 class="font-headline-sm text-headline-sm">Outils WhatsApp</h3></div>

    <p class="font-label-sm text-on-surface-variant uppercase mb-2">Diagnostic Meta</p>
    <form action="/admin/diag" method="get" target="_blank" class="flex flex-col sm:flex-row gap-2 mb-6">
      <input type="hidden" name="key" value="%%K%%"/>
      <input name="waba" placeholder="ID du compte WhatsApp Business" class="fld flex-1 font-body-md"/>
      <button class="bg-primary text-on-primary px-4 py-2 rounded-xl font-label-md text-label-md hover:bg-primary/90 active:scale-95 transition-all">Diagnostiquer</button>
    </form>

    <p class="font-label-sm text-on-surface-variant uppercase mb-2">Test d'envoi (template + texte)</p>
    <form action="/admin/testsend" method="get" target="_blank" class="flex flex-col sm:flex-row gap-2">
      <input type="hidden" name="key" value="%%K%%"/>
      <input name="to" placeholder="Numéro international sans + (ex: 33612345678)" class="fld flex-1 font-body-md"/>
      <button class="bg-primary text-on-primary px-4 py-2 rounded-xl font-label-md text-label-md hover:bg-primary/90 active:scale-95 transition-all">Envoyer un test</button>
    </form>
  </section>

  <p class="text-center text-on-surface-variant font-label-sm pt-2">Page réservée — accès protégé par la clé.</p>
</main>
</body></html>"""


# --- fragments dynamiques ----------------------------------------------------
_TABLE_ROW = (
    '<tr class="hover:bg-white/5 transition-colors">'
    '<td class="py-4 font-body-md">{label}</td>'
    '<td class="py-4 text-right"><span class="bg-secondary-container text-on-secondary-container '
    'px-2 py-0.5 rounded-full font-label-sm">{v}</span></td></tr>'
)


def _two_col(items, empty):
    if not items:
        return f'<tr><td colspan="2" class="py-4 font-body-md text-on-surface-variant">{empty}</td></tr>'
    return "".join(_TABLE_ROW.format(label=_esc(k), v=_esc(v)) for k, v in items)


def render(summary: dict, key: str = "") -> str:
    k = _esc(key)
    by_day = summary["by_day"]
    max_day = max(by_day.values(), default=1) or 1

    bars = "".join(
        f'<div class="flex flex-col items-center gap-2 w-full max-w-[40px] shrink-0">'
        f'<div class="relative w-full bg-primary rounded-t-lg transition-all duration-700 hover:brightness-125" '
        f'style="height:{max(4, round(v / max_day * 200))}px;">'
        f'<span class="absolute -top-8 left-1/2 -translate-x-1/2 font-label-sm text-primary">{v}</span></div>'
        f'<span class="font-label-sm text-on-surface-variant text-[10px]">{_esc(d[5:])}</span></div>'
        for d, v in by_day.items()
    ) or '<p class="text-on-surface-variant font-body-md">Aucune donnée pour l\'instant.</p>'

    clients = "".join(
        '<tr class="hover:bg-white/5 transition-colors">'
        f'<td class="py-4 font-body-md font-semibold text-primary">{_esc(u["num"])}</td>'
        f'<td class="py-4 text-center font-body-md">{_esc(u["count"])}</td>'
        f'<td class="py-4 text-right font-body-md text-on-surface-variant">'
        f'{_fmt_dt(u["last"]) if u["last"] else "—"}</td></tr>'
        for u in summary["users"]
    ) or '<tr><td colspan="3" class="py-4 font-body-md text-on-surface-variant">Aucun client pour l\'instant.</td></tr>'

    failed = "".join(
        '<div class="flex justify-between items-center p-3 bg-error-container/10 border '
        'border-error-container/20 rounded-lg hover:bg-error-container/20 transition-all">'
        f'<span class="font-body-md text-on-surface-variant">{_esc(q)}</span>'
        f'<span class="bg-error-container text-on-error-container px-2 py-0.5 rounded-full font-label-sm">{_esc(v)}</span></div>'
        for q, v in summary["failed_searches"]
    ) or '<p class="text-on-surface-variant font-body-md">Aucune — tout a été trouvé 🎉</p>'

    recent = "".join(
        '<tr class="hover:bg-white/5 transition-colors">'
        f'<td class="py-3 font-body-sm text-on-surface-variant whitespace-nowrap">{_fmt_dt(r["t"])}</td>'
        f'<td class="py-3 font-body-sm font-semibold text-primary whitespace-nowrap">{_esc(r["from"])}</td>'
        f'<td class="py-3 font-body-md">{_esc(r["text"])}</td></tr>'
        for r in summary["recent"]
    ) or '<tr><td colspan="3" class="py-4 font-body-md text-on-surface-variant">Aucun message pour l\'instant.</td></tr>'

    out = _HEAD + _BODY_DASHBOARD
    for token, value in {
        "%%TITLE%%": "Effi-Market Bot — Tableau de bord",
        "%%UPLOAD%%": _UPLOAD,
        "%%K%%": k,
        "%%STARTED%%": _fmt_dt(summary["started_at"]),
        "%%MSG%%": _esc(summary["messages_total"]),
        "%%USERS%%": _esc(summary["users_total"]),
        "%%DAYS%%": _esc(len(by_day)),
        "%%BARS%%": bars,
        "%%QUERIES%%": _two_col(summary["top_queries"], "Aucune recherche."),
        "%%PRODUCTS%%": _two_col(summary["top_products"], "Aucun produit affiché."),
        "%%CLIENTS%%": clients,
        "%%FAILED%%": failed,
        "%%RECENT%%": recent,
    }.items():
        out = out.replace(token, value)
    return out


def render_admin(key: str = "") -> str:
    """Page Admin/Réglages : sauvegarde/restauration + outils."""
    k = _esc(key)
    out = _HEAD + _BODY_ADMIN
    for token, value in {
        "%%TITLE%%": "Effi-Market Bot — Réglages",
        "%%UPLOAD%%": _UPLOAD,
        "%%K%%": k,
    }.items():
        out = out.replace(token, value)
    return out
