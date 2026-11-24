#!/usr/bin/env python3
"""Assemble les fragments de site-src/ dans site/. Usage : python3 site-src/build.py"""
import hashlib
from pathlib import Path
S = Path(__file__).parent
O = S.parent / "site"
PAGES = [("index", "Accueil"), ("circuit", "L’équipe et le circuit"), ("billet", "Un billet à la loupe"),
         ("incidents", "Ce qui a raté"), ("modeles", "Les modèles"), ("protocole", "Protocole"), ("refaire", "Refaire")]
DESC = "Veiller et contredire : une expérimentation pédagogique de veille par cinq agents d’IA, avec des modèles servis par ILaaS et Albert. JEDI-OpenLab, Centrale Lille."
v = hashlib.sha1((O / "assets/site.css").read_bytes()).hexdigest()[:10]
for nom, titre in PAGES:
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
{(S / f"{nom}.html").read_text()}
</main>
<footer class="site-foot"><div class="in">
<span>JEDI-OpenLab, Centrale Lille. Expérimentation pédagogique, document de travail.</span>
<span>Voir aussi <a href="https://jedi-openlab.github.io/dire-et-taire/">Dire et taire</a> · <a href="https://jediopenlab.hypotheses.org/">Carnet de recherche</a> · <a href="https://github.com/JEDI-OpenLab/veille-agentique">Documents et code</a></span>
</div></footer>
</body>
</html>
''')
print(len(PAGES), "pages")
