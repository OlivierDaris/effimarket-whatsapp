"""Rendu HTML du tableau de bord à partir du résumé des statistiques."""
from __future__ import annotations

import html
from datetime import datetime


def _esc(x) -> str:
    return html.escape(str(x))


def _fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return _esc(iso)


def _mask(num: str) -> str:
    """Masque partiellement un numéro (vie privée)."""
    s = str(num)
    return s if len(s) <= 5 else s[:4] + "•••" + s[-2:]


def render(summary: dict) -> str:
    by_day = summary["by_day"]
    max_day = max(by_day.values(), default=1) or 1
    bars = "".join(
        f'<div class="bar"><div class="bar-fill" style="height:{max(6, round(v / max_day * 100))}%">'
        f'<span class="bar-val">{v}</span></div><div class="bar-lbl">{_esc(d[5:])}</div></div>'
        for d, v in by_day.items()
    ) or '<p class="muted">Aucune donnée pour l\'instant.</p>'

    def rows(items, empty):
        if not items:
            return f'<tr><td colspan="2" class="muted">{empty}</td></tr>'
        return "".join(
            f"<tr><td>{_esc(k)}</td><td class='num'>{_esc(v)}</td></tr>" for k, v in items
        )

    recent = "".join(
        f"<tr><td class='mono'>{_fmt_dt(r['t'])}</td><td class='mono'>{_esc(_mask(r['from']))}</td>"
        f"<td>{_esc(r['text'])}</td></tr>"
        for r in summary["recent"]
    ) or '<tr><td colspan="3" class="muted">Aucun message pour l\'instant.</td></tr>'

    return f"""<!doctype html>
<html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tableau de bord — Effi-Market Bot</title>
<style>
  :root {{ --bg:#f4f6f5; --card:#fff; --ink:#17211c; --soft:#5a6660; --line:#e3e7e4;
           --accent:#1f6f52; --accent-soft:#e7efea; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
          font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1000px; margin:0 auto; padding:24px 18px 60px; }}
  header {{ display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:8px;
            border-bottom:2px solid var(--ink); padding-bottom:14px; margin-bottom:22px; }}
  h1 {{ font-size:1.5rem; margin:0; }}
  .muted {{ color:var(--soft); }}
  .since {{ font-size:.8rem; color:var(--soft); font-family:ui-monospace,monospace; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:26px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:16px 18px; }}
  .card .k {{ font-size:.72rem; letter-spacing:.08em; text-transform:uppercase; color:var(--soft); }}
  .card .v {{ font-size:2rem; font-weight:700; margin-top:4px; color:var(--accent); }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:18px; margin-bottom:22px; }}
  section h2 {{ font-size:1rem; margin:0 0 14px; }}
  .chart {{ display:flex; align-items:flex-end; gap:8px; height:160px; overflow-x:auto; padding-top:10px; }}
  .bar {{ display:flex; flex-direction:column; align-items:center; justify-content:flex-end; min-width:34px; height:100%; }}
  .bar-fill {{ width:26px; background:var(--accent); border-radius:4px 4px 0 0; position:relative;
               display:flex; align-items:flex-start; justify-content:center; }}
  .bar-val {{ font-size:.68rem; color:#fff; padding-top:2px; }}
  .bar-lbl {{ font-size:.66rem; color:var(--soft); margin-top:6px; font-family:ui-monospace,monospace; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:22px; }}
  @media (max-width:640px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:.7rem; letter-spacing:.06em; text-transform:uppercase; color:var(--soft); font-weight:600; }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:600; }}
  .mono {{ font-family:ui-monospace,monospace; font-size:.82rem; white-space:nowrap; }}
  .foot {{ text-align:center; color:var(--soft); font-size:.75rem; margin-top:10px; }}
</style></head>
<body><div class="wrap">
  <header>
    <h1>🛍️ Tableau de bord — Effi-Market Bot</h1>
    <span class="since">depuis le {_fmt_dt(summary["started_at"])}</span>
  </header>

  <div class="cards">
    <div class="card"><div class="k">Messages reçus</div><div class="v">{summary["messages_total"]}</div></div>
    <div class="card"><div class="k">Clients uniques</div><div class="v">{summary["users_total"]}</div></div>
    <div class="card"><div class="k">Jours actifs</div><div class="v">{len(by_day)}</div></div>
  </div>

  <section>
    <h2>📈 Messages par jour</h2>
    <div class="chart">{bars}</div>
  </section>

  <div class="grid2">
    <section>
      <h2>🔎 Recherches les plus fréquentes</h2>
      <table><thead><tr><th>Recherche</th><th class="num">Nb</th></tr></thead>
      <tbody>{rows(summary["top_queries"], "Aucune recherche.")}</tbody></table>
    </section>
    <section>
      <h2>🛒 Produits les plus proposés</h2>
      <table><thead><tr><th>Produit</th><th class="num">Nb</th></tr></thead>
      <tbody>{rows(summary["top_products"], "Aucun produit affiché.")}</tbody></table>
    </section>
  </div>

  <section>
    <h2>💬 Derniers messages</h2>
    <table><thead><tr><th>Quand</th><th>De</th><th>Message</th></tr></thead>
    <tbody>{recent}</tbody></table>
  </section>

  <p class="foot">Données lues depuis data/stats.json · sur l'offre gratuite, remises à zéro au redéploiement.</p>
</div></body></html>"""
