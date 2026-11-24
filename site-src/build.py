#!/usr/bin/env python3
"""Assemble les fragments de site-src/ dans site/. Usage : python3 site-src/build.py"""
import ast, hashlib, html
from pathlib import Path
S = Path(__file__).parent
O = S.parent / "site"
PAGES = [("index", "Accueil"), ("circuit", "L’équipe et le circuit"), ("consignes", "Les consignes"), ("billet", "Un billet à la loupe"),
         ("incidents", "Ce qui a raté"), ("modeles", "Les modèles"), ("protocole", "Protocole"), ("refaire", "Refaire"), ("technique", "Technique")]
DESC = "Veiller et contredire : une expérimentation pédagogique de veille par cinq agents d’IA, avec des modèles servis par ILaaS et Albert. JEDI-OpenLab, Centrale Lille."
DISPO = S.parent / "dispositif"
EQUIPE = [("nestor", "Nestor", "Cherche"), ("jarvis", "Jarvis", "Choisit"), ("r2d2", "R2-D2", "Vérifie"), ("watson", "Watson", "Écrit"), ("alfred", "Alfred", "Conteste"), ("moneypenny", "Moneypenny", "Résume la semaine"), ("hedwige", "Hedwige", "Met en page le courrier")]

def texte(n):
    """Texte d'un ordre de mission ; les parties calculées apparaissent entre ‹ ›."""
    if isinstance(n, ast.Constant): return str(n.value)
    if isinstance(n, ast.JoinedStr): return "".join(texte(x) for x in n.values)
    if isinstance(n, ast.FormattedValue): return {"n": "‹n›", "L": "‹dossier commun›", "D": "‹dossier du jour›"}.get(ast.unparse(n.value), "‹valeur›")
    if isinstance(n, ast.BinOp): return texte(n.left) + texte(n.right)
    if isinstance(n, ast.Name): return {"suite": " ‹à partir de la version 2 : corriger selon la revue précédente, sans ajouter de fait›", "objections": " ‹à partir de la version 2 : corriger selon la revue précédente, en traitant chaque objection majeure›"}.get(n.id, "‹valeur›")
    return "‹adresses retenues›"

def consignes(page):
    missions = {}
    noeuds = [n for f in ("office.py", "recap.py") for n in ast.walk(ast.parse((DISPO / f).read_text()))]
    for n in noeuds:
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tache":
            missions.setdefault(n.args[0].value, []).append((n.lineno, texte(n.args[1]), texte(n.args[2])))
    para = lambda t: "".join(f"<p>{html.escape(x)}</p>" for x in t.strip().splitlines() if x.strip())
    blocs, communes = "", set()
    for i, (cle, nom, verbe) in enumerate(EQUIPE):
        propre, commun = (DISPO / "consignes" / f"{cle}.md").read_text().split("## Règles communes")
        communes.add(commun.strip())
        m = "".join(f"<h4>{html.escape(t)}</h4><div class=\"consigne mission\">{para(c)}</div>" for _, t, c in sorted(missions.get(cle, [])))
        blocs += f'<section class="band{" alt" if i % 2 else ""}"><div class="wrap"><div class="prose"><h2 id="{cle}">{nom} <span class="muted">· {verbe}</span></h2><h3>Consignes permanentes</h3><div class="consigne">{para(propre)}</div><h3>Missions</h3>{m}</div></div></section>'
    assert len(communes) == 1, "les règles communes diffèrent entre agents"
    regles = "<ul>" + "".join(f"<li>{html.escape(x.removeprefix('- '))}</li>" for x in communes.pop().splitlines() if x.strip()) + "</ul>"
    sommaire = "".join(f'<a class="btn" href="#{c}">{n}</a>' for c, n, _ in EQUIPE)
    return page.replace("{{COMMUNES}}", regles).replace("{{AGENTS}}", blocs).replace("{{SOMMAIRE}}", sommaire)

v = hashlib.sha1((O / "assets/site.css").read_bytes()).hexdigest()[:10]
for nom, titre in PAGES:
    corps = (S / f"{nom}.html").read_text()
    if nom == "consignes": corps = consignes(corps)
    menu = "".join(f'<li><a href="{n}.html"{" aria-current=page" if n == nom else ""}>{t}</a></li>' for n, t in PAGES)
    t = "Veiller et contredire" if nom == "index" else f"{titre} · Veiller et contredire"
    (O / f"{nom}.html").write_text(f'''<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<title>{t}</title>
<meta name="description" content="{DESC}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,650&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@500&display=swap">
<link rel="stylesheet" href="assets/site.css?v={v}">
</head>
<body>
<nav class="site-nav" aria-label="Sections du site"><div class="in">
<div class="marque"><a class="portail" href="https://jedi-openlab.github.io/jedi/" title="Portail JEDI-OpenLab"><img src="https://jedi-openlab.github.io/jedi/PIX/jedi-favicon-180-2026.png" alt="JEDI-OpenLab, retour au portail" width="40" height="40"></a>
<a class="brand" href="index.html">Veiller et contredire</a></div>
<ul>{menu}</ul></div></nav>
<main>
{corps}
</main>
<footer class="site-foot"><div class="in">
<span>JEDI-OpenLab, Centrale Lille. Expérimentation pédagogique, document de travail.</span>
<span>Voir aussi <a href="https://jedi-openlab.github.io/dire-et-taire/">Dire et taire</a> · <a href="https://jediopenlab.hypotheses.org/">Carnet de recherche</a> · <a href="https://github.com/JEDI-OpenLab/veille-agentique">Documents et code</a></span>
</div></footer>
</body>
</html>
''')
print(len(PAGES), "pages")
