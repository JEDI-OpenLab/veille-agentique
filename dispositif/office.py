#!/usr/bin/env python3
"""Circuit du PAPN : enchaîne les tâches Kanban et contrôle chaque sortie."""
import fcntl, html, json, re, shutil, subprocess, sys, time, unicodedata
from datetime import datetime
from pathlib import Path
L = Path.home() / "laboratoire-veille"
H = str(Path.home() / "hermes-agent/.hermes/bin/hermes")
verrou = open(L / ".office.lock", "w")
try: fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError: sys.exit("Un passage est déjà en cours.")
ESSAI = "--veille-seule" in sys.argv  # arrêt après Nestor, sans publier ni marquer les adresses
# --rejeu DOSSIER [--urls u1 u2] : repart de fiches existantes, va jusqu'à la contradiction, ne publie rien
REJEU = Path(sys.argv[sys.argv.index("--rejeu") + 1]).resolve() if "--rejeu" in sys.argv else None
FORCE = sys.argv[sys.argv.index("--urls") + 1:] if "--urls" in sys.argv else []
D = L / ("essais" if ESSAI or REJEU else "dossiers") / datetime.now().strftime("%Y-%m-%d-%Hh%M"); D.mkdir(parents=True)

def log(*a):
    s = datetime.now().strftime("%H:%M:%S ") + " ".join(map(str, a)); print(s, flush=True)
    with open(D / "journal.txt", "a") as f: f.write(s + "\n")
def fin(code, msg):
    log("FIN", msg); (D / "bilan.txt").write_text(msg + "\n"); sys.exit(code)
def hermes(*a):
    r = subprocess.run([H, "kanban", *a], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90)
    if r.returncode: raise RuntimeError(r.stderr[-400:] or r.stdout[-400:])
    return r.stdout
def tache(qui, titre, corps, sortie, minutes=20, controle=None):
    """Crée la tâche, attend, puis lit la sortie ; un second essai si elle manque ou est invalide."""
    erreur = ""
    for essai in (1, 2):
        (D / sortie).unlink(missing_ok=True)  # jamais une réponse d'une étape précédente
        c = f"Dossier de travail : {D}\nFichier à produire : {D/sortie}\n\n{corps}" + (f"\n\nEssai précédent refusé : {erreur}" if erreur else "")
        t = json.loads(hermes("create", titre, "--body", c, "--assignee", qui, "--workspace", f"dir:{D}", "--max-runtime", f"{minutes}m", "--max-retries", "2", "--created-by", "office", "--json"))
        tid = t.get("id") or t["task"]["id"]; log(qui, titre, tid); fini = time.time() + (minutes * 2 + 5) * 60; st = "?"
        while time.time() < fini:
            time.sleep(10); j = json.loads(hermes("show", tid, "--json")); st = (j.get("task") or j).get("status")
            if st in ("done", "blocked", "archived", "review"): break
        try:
            x = (D / sortie).read_text()
            if sortie.endswith(".json"):
                x = json.loads(re.sub(r"^```\w*\s*|\s*```$", "", x.strip())); (D / sortie).write_text(json.dumps(x, ensure_ascii=False, indent=1))
            if controle: controle(x)
            log(qui, "terminé,", st); return x
        except Exception as e:
            erreur = f"{sortie} : {e}"; log(qui, "sortie refusée", st, erreur)
            if st not in ("done", "blocked", "archived"):
                try: hermes("block", tid, "délai dépassé")
                except Exception: pass
    fin(1, f"Échec : {qui} n'a pas produit {sortie} ({erreur})")
from billet import analyser, assembler, defauts, norm, numeroter, passage, relie, rubrique
def ouvrir(url):
    """Page analysée : titre réel, texte, rubriques, liens."""
    if not re.match(r"https?://", url): return None
    b = subprocess.run(["curl", "-sL", "--proto", "=http,https", "-m", "30", "--max-filesize", "20000000", "-A", "Mozilla/5.0", "--", url], capture_output=True).stdout
    if b[:4] == b"%PDF":
        if not shutil.which("pdftotext"): return None
        t = subprocess.run(["pdftotext", "-", "-"], input=b, capture_output=True).stdout.decode("utf8", "replace")
        return {"titre": "", "segments": [], "liens": [], "texte": norm(t)}
    return analyser(b.decode("utf8", "replace")) if b else None
def cle(u):
    """Adresse comparable : sans ancre ni paramètres de suivi, mais avec ceux qui désignent la page."""
    b, _, q = u.strip().partition("#")[0].partition("?")
    q = "&".join(sorted(x for x in q.split("&") if x and not re.match(r"(utm_\w+|lang|fbclid|gclid|xtor|at_\w+)(=|$)", x)))
    return (re.sub(r"^https?://(www\.)?", "https://", b).rstrip("/") + ("?" + q if q else ""))

vus = {cle(u) for u in (L / "deja_vu.txt").read_text().splitlines() if u.strip()}
AGE_MAX = 60  # jours, hors revues et archives de recherche
try:
    from recherche import chercher
    pub, pannes = chercher()
except Exception as e: pub, pannes = [], [str(e)[:150]]
pub = [x for x in pub if cle(x["url"]) not in vus]
resumes_hal = {cle(x["url"]): norm(x["titre"] + " " + x["resume"]) for x in pub if x["source"] == "HAL"}
(D / "recherche.json").write_text(json.dumps(pub, ensure_ascii=False, indent=1)); log(len(pub), "publications HAL et arXiv", *pannes)
try:
    from flux import collecter, jour, tournee
    actu, pannes = collecter(); sites = tournee()
except Exception as e:
    actu, pannes, sites = [], [str(e)[:150]], []
    def jour(x):
        try: return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
        except ValueError: return None
actu = [x for x in actu if cle(x["url"]) not in vus]
(D / "actualites.json").write_text(json.dumps([{k: v for k, v in x.items() if k != "age_max"} for x in actu], ensure_ascii=False, indent=1)); log(len(actu), "articles dans les flux", *pannes)
if REJEU: f = json.loads((REJEU / "fiches.json").read_text()); log("rejeu de", REJEU.name)
else: f = tache("nestor", "Veille du jour", "Propose 4 à 8 ressources récentes. Lis actualites.json (flux de nos sources) et recherche.json (HAL et arXiv) : choisis-y d'abord, en reprenant l'adresse exacte et la date indiquée. Ouvre la page de chaque ressource retenue ; pour HAL, ne tente pas d'ouvrir la page, elle refuse la lecture automatique : appuie-toi sur le champ resume. Va ensuite voir les nouveautés de : " + ", ".join(f"{n} ({u})" for n, u, *_ in sites) + ". Varie les sources, deux au plus par site, et les thèmes : évaluation, compétences, inclusion, formation d'ingénieurs, et pas seulement l'IA. Une ressource de plus de 60 jours ou sans date affichée sera écartée. Une prépublication est signalée comme telle. Ne force rien. Pas d'annonce de formation, d'événement, d'appel ou d'offre : leur date est celle de l'événement, et il n'y a rien à en apprendre. JSON : liste d'objets {titre (celui de la page, sans le modifier), url, nature (article, etude, prepublication, guide, rapport, ressource ou actualite), source, date (AAAA-MM-JJ, celle de la page), thematique, resume, interet}. Liste vide si rien de nouveau.", "fiches.json", 25)
sures = {cle(x["url"]): (x["date"], x["age_max"]) for x in actu} | {cle(x["url"]): (x.get("depot") or x["date"], AGE_MAX) for x in pub}
affichees = {cle(x["url"]): str(x["date"]) for x in actu + pub}
def motif(x, compte):
    """Pourquoi écarter une fiche, ou None. La date des flux et des interfaces prime sur celle de Nestor."""
    if not isinstance(x, dict) or not re.match(r"https?://", str(x.get("url", ""))): return "adresse absente"
    k = cle(x["url"]); site = k.split("/")[2]
    if re.search(r"calendrier|agenda|evenement|inscription|/events?/|offre-emploi|appel-a-", k): return "annonce ou événement"
    if str(x.get("nature", "")).lower() not in ("article", "etude", "étude", "prepublication", "prépublication", "guide", "rapport", "ressource", "actualite", "actualité"): return f"nature non admise ({x.get('nature')})"
    if k in vus: return "déjà vue"
    if k in compte["pages"]: return "en double"
    d, age = sures.get(k, (x.get("date"), AGE_MAX)); d = jour(d)
    if not d: return "date inconnue"
    n = (datetime.now().date() - d).days
    if n > age: return f"trop ancienne ({n} jours)"
    if n < -1: return "date à venir"
    if k not in resumes_hal and not REJEU:
        code = subprocess.run(["curl", "-sL", "--proto", "=http,https", "-m", "25", "-o", "/dev/null", "-w", "%{http_code}", "-A", "Mozilla/5.0", "--", x["url"]], capture_output=True, text=True).stdout.strip()
        if code in ("404", "410", "000"): return f"page introuvable ({code})"
    if compte["sites"].get(site, 0) >= 2: return "déjà deux ressources de ce site"
    x["date_verifiee"] = k in sures
    if x["date_verifiee"]: x["date"] = affichees[k]
    compte["pages"].add(k); compte["sites"][site] = compte["sites"].get(site, 0) + 1
compte, gardees, ecartees = {"pages": set(), "sites": {}}, [], []
for x in f if isinstance(f, list) else []:
    m = motif(x, compte); (ecartees if m else gardees).append({**x, "motif": m} if m and isinstance(x, dict) else x)
if REJEU: gardees = [x for x in f if isinstance(x, dict)] if FORCE else [x for x in gardees + ecartees if x.get("motif") not in ("annonce ou événement",)]  # un rejeu ignore la date et les adresses vues
f = gardees; (D / "ecartees.json").write_text(json.dumps(ecartees, ensure_ascii=False, indent=1)); log(len(ecartees), "fiche(s) écartée(s)", *[str(x.get("motif")) for x in ecartees if isinstance(x, dict)])
(D / "fiches.json").write_text(json.dumps(f, ensure_ascii=False, indent=1)); log(len(f), "fiches nouvelles")
if ESSAI: fin(0, f"Essai de veille : {len(f)} fiche(s) gardée(s), {len(ecartees)} écartée(s).")
if not f: fin(0, "Aucune ressource nouvelle.")
exclues = set()
for essai_sujet in (1, 2):
    if FORCE: s = {"retenu": True, "angle": "rejeu", "urls": FORCE}
    else: s = tache("moneypenny", "Choix du sujet", "Lis fiches.json et choisis. Une question unique pour le billet. Une seule ressource suffit le plus souvent : n'en réunis plusieurs que si chacune répond à cette même question ; un thème commun ou un même établissement ne suffit pas. N'affirme aucun lien entre elles. " + (" Déjà jugées inutilisables par R2-D2, à ne pas reprendre : " + ", ".join(sorted(exclues)) + "." if exclues else "") + " JSON : {retenu: bool, angle (la question), urls: [1 à 3 adresses tirées de fiches.json], apport: {adresse: ce qu'elle apporte à la question}, raison}.", "selection.json", 10)
    urls = [u for u in s.get("urls", []) if cle(u) in {cle(x["url"]) for x in f} - exclues]
    if not REJEU and essai_sujet == 1:
        with open(L / "deja_vu.txt", "a") as o: o.write("".join("\n" + x["url"] for x in f))
    if not s.get("retenu") or not urls: fin(0, "Moneypenny n'a rien retenu : " + str(s.get("raison")))
    v = tache("r2d2", "Vérification scientifique", "Sources retenues : " + ", ".join(urls) + ". Pour une adresse HAL, lis seulement son champ resume dans recherche.json, n'ouvre pas la page, et note dans methode que seul le résumé a été lu. Juge d'abord chaque source : si c'est une annonce, une promotion, un sommaire ou une page sans contenu à apprendre (une fiche d'inscription à une formation l'est, même si elle énonce de beaux objectifs), déclare-la inutilisable et n'en tire aucune affirmation. JSON : {sources: [{url, nature, utilisable: bool, raison}], affirmations: [{texte, url, extrait}], methode: [{url, type, limites}], ecarte: [{quoi, pourquoi}]}. 4 à 12 affirmations.", "verification.json", 25)
    jug = {cle(x.get("url", "")): x for x in v.get("sources", []) if isinstance(x, dict)}
    hors = [u for u in urls if jug.get(cle(u), {}).get("utilisable") is False or re.search(r"annonce|promotion|événement|evenement|sommaire|inscription|calendrier|description d.une formation|fiche de formation|offre de formation", str(jug.get(cle(u), {}).get("nature", "")), re.I)]
    for u in hors: log("source écartée par R2-D2 :", u, str(jug.get(cle(u), {}).get("raison"))[:150])
    urls = [u for u in urls if u not in hors]
    if urls or FORCE: break
    exclues |= {cle(u) for u in hors}; log("sources inutilisables, nouveau choix" if essai_sujet == 1 else "second choix inutilisable")
if not urls: fin(0, "Abandon : R2-D2 juge les sources inutilisables.")
pages, sources, ids = {}, [], {}
for u in urls:
    k = cle(u); p = {"titre": next((x["titre"] for x in pub if cle(x["url"]) == k), ""), "segments": [], "liens": [], "texte": resumes_hal[k]} if k in resumes_hal else ouvrir(u)
    pages[k] = p or {"titre": "", "segments": [], "liens": [], "texte": ""}; ids[k] = f"S{len(sources) + 1}"
    sources.append({"id": ids[k], "url": u, "titre": pages[k]["titre"] or next((x.get("titre") for x in f if cle(x["url"]) == k), u), "titre_verifie": bool(pages[k]["titre"]), "nature": jug.get(k, {}).get("nature", "")})
relations = [[ids[a], ids[b]] for a in pages for b in pages if a < b and (relie(pages[a], b, cle) or relie(pages[b], a, cle))]
ok, ko = [], []
for a in v.get("affirmations", []):
    k = cle(a.get("url", "")); e = norm(a.get("extrait", ""))
    if k in pages and len(e.split()) >= 6 and e in pages[k]["texte"]: ok.append({"id": f"A{len(ok) + 1}", "texte": a["texte"], "source": ids[k], "extrait": a["extrait"], "rubrique": rubrique(pages[k], a["extrait"]), "lien": a["url"].split("#")[0] if k in resumes_hal else passage(a["url"], a["extrait"])})
    else: ko.append(a)
log(len(ok), "extraits retrouvés,", len(ko), "écartés")
valide = {"angle": s.get("angle"), "sources": sources, "relations": relations, "note_relations": "Paires de sources dont l'une renvoie à l'autre. Toute autre relation entre sources est une invention.", "affirmations": ok, "methode": [m for m in v.get("methode", []) if isinstance(m, dict) and cle(m.get("url", "")) in pages]}
(D / "valide.json").write_text(json.dumps(valide, ensure_ascii=False, indent=1))
(D / "extraits_ecartes.json").write_text(json.dumps(ko, ensure_ascii=False, indent=1))
if len(ok) < 3: fin(0, f"Abandon : {len(ok)} affirmation(s) vérifiée(s), il en faut 3.")
objections, verdict = "", None
def bon_brouillon(b):
    d = defauts(b, valide)
    assert not d, "; ".join(d)
for n in (1, 2, 3):
    (D / "brouillon.json").unlink(missing_ok=True)
    b = tache("watson", f"Rédaction, version {n}", "À partir de valide.json uniquement. Tu n'écris ni HTML, ni lien, ni titre de source : le code les pose à partir des numéros. JSON : {titre, extrait (250 caractères au plus), tags: [..], sections: [{titre, nature, paragraphes: [{texte, affirmations: [\"A1\"]}]}]}. Natures : accroche (situation hypothétique, sans numéro), faits (chaque paragraphe cite ses affirmations, une seule source par paragraphe sauf si relations dit qu'elles sont reliées), pistes (tes suggestions, sans numéro), limites. 500 à 700 mots." + objections, "brouillon.json", 15, bon_brouillon)
    (D / "meta.json").write_text(json.dumps({"titre": b["titre"], "extrait": b["extrait"], "tags": b.get("tags") or []}, ensure_ascii=False, indent=1))
    (D / "billet.html").write_text(assembler(b, valide)); shutil.copy(D / "billet.html", D / f"billet-v{n}.html"); shutil.copy(D / "brouillon.json", D / f"brouillon-v{n}.json")
    par = numeroter(b); (D / "a-contester.json").write_text(json.dumps({"titre": b["titre"], "extrait": b["extrait"], "paragraphes": par}, ensure_ascii=False, indent=1)); faits = {p["n"] for p in par if p["nature"] != "accroche"}
    def bonne_revue(r):
        assert r.get("verdict") in ("accepte", "corriger", "rejete") and isinstance(r.get("objections"), list), "verdict et objections attendus"
        vus_ = {x.get("n") for x in r.get("paragraphes", []) if isinstance(x, dict) and x.get("verdict") in ("fidele", "infidele") and len(str(x.get("pourquoi", ""))) > 15}
        assert faits <= vus_, f"paragraphes non examinés : {sorted(faits - vus_)}"
    r = tache("velma", f"Revue adversariale {n}", "Confronte a-contester.json à valide.json, paragraphe par paragraphe. Dans les pistes, une suggestion est permise, mais un effet promis (« garantit », « permet de limiter », « évite ») est un fait sans source : infidèle. Pour chaque paragraphe de faits ou de limites, isole d'abord ce qu'il affirme sur les RELATIONS (associé, issu de, illustre, en lien, cause, conséquence, même projet), puis vérifie : cette relation est-elle écrite dans une affirmation citée, ou dans relations ? Sinon le paragraphe est infidèle, même si chaque mot est exact. Vérifie ensuite attribution, généralisation, force des verbes, limites oubliées, titre et extrait. Relis aussi les phrases que tu n'as pas contestées à la version précédente. JSON : {verdict: \"accepte\"|\"corriger\"|\"rejete\", paragraphes: [{n, relations, verdict: \"fidele\"|\"infidele\", pourquoi}], objections: [{gravite: \"majeure\"|\"mineure\", phrase, probleme, correction}]}.", f"revue-{n}.json", 18, bonne_revue)
    inf = [x["n"] for x in r["paragraphes"] if isinstance(x, dict) and x.get("verdict") == "infidele"]; maj = [o for o in r["objections"] if isinstance(o, dict) and "maj" in str(o.get("gravite"))]
    verdict = "rejete" if r["verdict"] == "rejete" else "corriger" if inf or maj else "accepte"
    log("Velma :", r["verdict"], len(maj), "objection(s) majeure(s),", len(inf), "paragraphe(s) infidèle(s)", f"=> {verdict}" if verdict != r["verdict"] else "")
    if verdict != "corriger": break
    objections = f" Corrige selon revue-{n}.json : chaque objection majeure et chaque paragraphe infidèle, sans toucher au reste ; ton texte précédent est brouillon-v{n}.json."
(D / "decision.json").write_text(json.dumps({"verdict": verdict, "versions": n}))
if REJEU: fin(0, f"Essai de rejeu : {verdict} après {n} version(s), rien publié.")
if verdict != "accepte":
    tache("moneypenny", "Abandon du sujet", "Velma n'a pas accepté le billet. Lis les revues et explique la raison en 5 lignes.", "abandon.md", 10); fin(0, "Sujet abandonné, voir abandon.md.")
tache("watson", "Publication", f"Exécute une seule fois : python3 {L}/publier.py {D}\nLa commande écrit elle-même publie.json. Ne modifie rien.", "publie.json", 10)
fin(0, "Publié : " + (D / "publie.json").read_text().strip())
