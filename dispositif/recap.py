#!/usr/bin/env python3
"""Récapitulatif hebdomadaire : Moneypenny écrit, Alfred conteste, Hedwige met en page.
Options : --glissant (7 derniers jours, aujourd'hui compris) ; --essai (ne publie pas, ne dépose rien)."""
import fcntl, html, json, re, subprocess, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path
L, ESSAI = Path.home() / "laboratoire-veille", "--essai" in sys.argv
H = str(Path.home() / "hermes-agent/.hermes/bin/hermes")
verrou = open(L / ".recap.lock", "w")
try: fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError: sys.exit("Un récapitulatif est déjà en cours.")
auj = date.today()
debut, fin_s = (auj - timedelta(days=6), auj) if "--glissant" in sys.argv else (auj - timedelta(days=auj.weekday() + 7), auj - timedelta(days=auj.weekday() + 1))
a, s, _ = debut.isocalendar()
D = L / "semaines" / (f"{a}-S{s:02d}" + datetime.now().strftime("-essai-%d%Hh%M") * ESSAI); D.mkdir(parents=True, exist_ok=True)
if (D / "publie.json").exists(): sys.exit("Récapitulatif déjà publié : " + D.name)

def log(*x):
    m = datetime.now().strftime("%H:%M:%S ") + " ".join(map(str, x)); print(m, flush=True)
    with open(D / "journal.txt", "a") as f: f.write(m + "\n")
def fin(code, m): log("FIN", m); (D / "bilan.txt").write_text(m + "\n"); sys.exit(code)
def lire(p, defaut=None):
    try: return json.loads(p.read_text())
    except (OSError, ValueError): return defaut
def ecrire(n, x): (D / n).write_text(json.dumps(x, ensure_ascii=False, indent=1))
def hermes(*x):
    r = subprocess.run([H, "kanban", *x], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90)
    if r.returncode: raise RuntimeError((r.stderr or r.stdout)[-400:])
    return r.stdout
def tache(qui, titre, corps, sortie, controle, minutes=15):
    """Deux essais ; la sortie doit passer le contrôle."""
    erreur = ""
    for _ in (1, 2):
        (D / sortie).unlink(missing_ok=True)
        c = f"Dossier de travail : {D}\nFichier à produire : {D/sortie}\n\n{corps}" + (f"\n\nEssai précédent refusé : {erreur}" if erreur else "")
        j = json.loads(hermes("create", titre, "--body", c, "--assignee", qui, "--workspace", f"dir:{D}", "--max-runtime", f"{minutes}m", "--max-retries", "2", "--created-by", "office", "--json"))
        tid = j.get("id") or j["task"]["id"]; log(qui, titre, tid); limite = time.time() + (minutes * 2 + 5) * 60; st = "?"
        while time.time() < limite:
            time.sleep(10); k = json.loads(hermes("show", tid, "--json")); st = (k.get("task") or k).get("status")
            if st in ("done", "blocked", "archived", "review"): break
        try:
            x = json.loads(re.sub(r"^```\w*\s*|\s*```$", "", (D / sortie).read_text().strip())); controle(x); ecrire(sortie, x); log(qui, "terminé,", st); return x
        except Exception as e:
            erreur = f"{sortie} : {e}"; log(qui, "sortie refusée", st, erreur)
            if st not in ("done", "blocked", "archived"):
                try: hermes("block", tid, "délai dépassé")
                except Exception: pass
    return None

billets, ressources, vus, abandons = [], [], set(), 0
for d in sorted((L / "dossiers").glob("20*")):
    try: j = date.fromisoformat(d.name[:10])
    except ValueError: continue
    if not debut <= j <= fin_s: continue
    p, m, pris = lire(d / "publie.json") or {}, lire(d / "meta.json", {}) or {}, []
    if p.get("ok") and p.get("status") == "published":
        v = lire(d / "valide.json", {}) or {}; pris = [u for u in (lire(d / "selection.json", {}) or {}).get("urls", []) if re.match(r"https?://", u)]
        billets.append({"id": f"B{len(billets)+1}", "statut": "publié, accepté par Alfred", "date": str(j), "titre": p.get("title") or m.get("titre"), "extrait": m.get("extrait"), "url": p.get("url"), "sources": pris, "affirmations": [x.get("texte") for x in v.get("affirmations", [])]})
    elif (d / "bilan.txt").exists(): abandons += 1
    for f in lire(d / "fiches.json", []) or []:
        u = str(f.get("url", ""))
        if re.match(r"https?://", u) and u not in pris and u not in vus:
            vus.add(u); ressources.append({"id": f"R{len(ressources)+1}", "titre": f.get("titre"), "url": u, "source": f.get("source"), "date": f.get("date"), "resume_non_verifie": f.get("resume")})
sem = {"du": str(debut), "au": str(fin_s), "billets": billets, "ressources": ressources[:30], "passages_sans_billet": abandons}
ecrire("semaine.json", sem); log(len(billets), "billet(s),", len(ressources), "ressource(s),", abandons, "sans billet")
if not billets and not ressources: fin(0, "Rien à raconter cette semaine.")
ids = {x["id"] for x in billets + sem["ressources"]}

def bon_recap(r):
    assert isinstance(r.get("titre"), str) and isinstance(r.get("intro"), str) and r.get("themes"), "titre, intro et themes attendus"
    for t in r["themes"]:
        assert isinstance(t.get("titre"), str) and isinstance(t.get("texte"), str) and t.get("refs"), "chaque thème : titre, texte, refs"
        assert set(t["refs"]) <= ids, f"identifiant inconnu : {set(t['refs']) - ids}"
    assert not re.search(r"https?://|www\.", json.dumps(r, ensure_ascii=False)), "aucun lien dans le texte"
    assert len(" ".join([r["intro"]] + [t["texte"] for t in r["themes"]]).split()) <= 600, "600 mots au plus"
def bonne_revue(r): assert r.get("verdict") in ("accepte", "corriger", "rejete") and isinstance(r.get("objections"), list), "verdict et objections attendus"
suite = ""
for n in (1, 2, 3):
    r = tache("moneypenny", f"Récapitulatif, version {n}", "Lis semaine.json. JSON : {titre, intro, themes: [{titre, texte, refs: [identifiants]}]}. 1 à 4 thèmes, 600 mots au plus. Présente les R comme repérés, non vérifiés." + suite, "recap.json", bon_recap)
    if not r: fin(1, "Échec : Moneypenny n'a pas rendu un récapitulatif valable.")
    v = tache("alfred", f"Revue du récapitulatif {n}", "Confronte recap.json à semaine.json, ta seule base factuelle ici. Les règles de longueur et d'accroche des billets ne s'appliquent pas. JSON : {verdict: \"accepte\"|\"corriger\"|\"rejete\", objections: [{gravite: \"majeure\"|\"mineure\", phrase, probleme, correction}]}.", f"revue-{n}.json", bonne_revue)
    if not v: fin(1, "Échec : Alfred n'a pas rendu de revue valable.")
    maj = [o for o in v["objections"] if isinstance(o, dict) and "maj" in str(o.get("gravite"))]
    ok = v["verdict"] == "accepte" or (v["verdict"] == "corriger" and not maj); log("Alfred :", v["verdict"], len(maj), "objection(s) majeure(s)")
    if ok or v["verdict"] == "rejete": break
    suite = f" Corrige selon revue-{n}.json : traite chaque objection majeure, sans ajouter de fait."
if not ok: fin(0, "Récapitulatif non accepté par Alfred.")

# Les blocs sont numérotés : Hedwige les ordonne, elle ne peut pas en changer le texte.
tout = {x["id"]: x for x in billets + sem["ressources"]}
def lien(i):
    x = tout[i]
    if i[0] == "R": return {"titre": x["titre"], "url": x["url"], "nature": f"{i}, repéré, non vérifié"}
    return {"titre": x["titre"], "url": x["url"], "nature": f"{i}, billet publié"} if x.get("url") else {"titre": x["titre"], "url": (x["sources"] or [None])[0], "nature": f"{i}, source du billet"}
blocs = {f"T{k}": {"titre": t["titre"], "texte": t["texte"], "liens": [lien(i) for i in t["refs"]]} for k, t in enumerate(r["themes"], 1)}
ecrire("blocs.json", blocs)
def bon_ordre(x):
    assert sorted(x.get("ordre", [])) == sorted(blocs), f"ordre doit contenir exactement une fois : {sorted(blocs)}"
    assert x.get("en_avant") in blocs, "en_avant : un identifiant de bloc"
h = tache("hedwige", "Mise en page du courrier", "Lis blocs.json. Choisis l'ordre de lecture et un bloc à mettre en avant. JSON : {ordre: [tous les identifiants, une fois chacun], en_avant: un identifiant}. Aucun autre texte.", "mise_en_page.json", bon_ordre, 8)
if not h: log("Hedwige indisponible : ordre d'origine conservé"); h = {"ordre": list(blocs), "en_avant": "T1"}
ordre = [h["en_avant"]] + [i for i in h["ordre"] if i != h["en_avant"]]
courrier = {"id": D.name, "objet": f"[PAPN] La veille du {debut:%d/%m} au {fin_s:%d/%m}", "titre": r["titre"], "intro": r["intro"], "blocs": [blocs[i] for i in ordre]}
ecrire("courrier.json", courrier)
e = lambda t: "".join(f"<p>{html.escape(x.strip())}</p>" for x in str(t).split("\n") if x.strip())
corps = e(r["intro"]) + "".join(f"<h2>{html.escape(b['titre'])}</h2>{e(b['texte'])}<ul>" + "".join(
    f'<li><a href="{html.escape(l["url"] or "", quote=True)}">{html.escape(str(l["titre"]))}</a> ({l["nature"]})</li>' for l in b["liens"] if l["url"]) + "</ul>" for b in courrier["blocs"])
(D / "billet.html").write_text(corps); ecrire("meta.json", {"titre": r["titre"], "extrait": r["intro"][:250], "tags": ["Récap de la semaine"]}); ecrire("decision.json", {"verdict": "accepte", "versions": n})
if ESSAI: fin(0, "Essai terminé : rien publié, rien déposé.")
depart = Path("/var/spool/papn-mail")  # boîte de départ, si l'envoi est installé
if not depart.is_dir(): depart = L / "courrier"
depart.mkdir(exist_ok=True); t = depart / f".{D.name}.tmp"; t.write_text(json.dumps(courrier, ensure_ascii=False)); t.chmod(0o640); t.rename(depart / f"{D.name}.json")
p = subprocess.run([sys.executable, str(L / "publier.py"), str(D)], capture_output=True, text=True)
fin(p.returncode, ("Publié. " if not p.returncode else "Échec de publication. ") + (p.stdout or p.stderr)[:300])
