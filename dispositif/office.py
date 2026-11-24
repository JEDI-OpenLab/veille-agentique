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
D = L / "dossiers" / datetime.now().strftime("%Y-%m-%d-%Hh%M"); D.mkdir(parents=True)

def log(*a):
    s = datetime.now().strftime("%H:%M:%S ") + " ".join(map(str, a)); print(s, flush=True)
    with open(D / "journal.txt", "a") as f: f.write(s + "\n")
def fin(code, msg):
    log("FIN", msg); (D / "bilan.txt").write_text(msg + "\n"); sys.exit(code)
def hermes(*a):
    r = subprocess.run([H, "kanban", *a], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90)
    if r.returncode: raise RuntimeError(r.stderr[-400:] or r.stdout[-400:])
    return r.stdout
def tache(qui, titre, corps, sortie, minutes=20):
    """Crée la tâche, attend, puis lit la sortie ; un second essai si elle manque ou est invalide."""
    erreur = ""
    for essai in (1, 2):
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
            log(qui, "terminé,", st); return x
        except Exception as e:
            erreur = f"{sortie} : {e}"; log(qui, "sortie refusée", st, erreur)
            if st not in ("done", "blocked", "archived"):
                try: hermes("block", tid, "délai dépassé")
                except Exception: pass
    fin(1, f"Échec : {qui} n'a pas produit {sortie} ({erreur})")
def norm(s):
    s = unicodedata.normalize("NFKC", html.unescape(s)).lower()
    return re.sub(r"[\W_]+", " ", s).strip()
def texte(url):
    if not re.match(r"https?://", url): return ""
    r = subprocess.run(["curl", "-sL", "--proto", "=http,https", "-m", "30", "--max-filesize", "20000000", "-A", "Mozilla/5.0", "--", url], capture_output=True)
    b = r.stdout
    if b[:4] == b"%PDF":
        if not shutil.which("pdftotext"): return ""
        return norm(subprocess.run(["pdftotext", "-", "-"], input=b, capture_output=True).stdout.decode("utf8", "replace"))
    s = b.decode("utf8", "replace"); s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    return norm(re.sub(r"(?s)<[^>]+>", " ", s))
def cle(u): return re.sub(r"[?#].*$", "", u.strip()).rstrip("/").replace("http://", "https://").replace("https://www.", "https://")

vus = {cle(u) for u in (L / "deja_vu.txt").read_text().splitlines() if u.strip()}
f = tache("nestor", "Veille du jour", "Propose 4 à 8 ressources récentes. JSON : liste d'objets {titre, url, source, date, thematique, resume, interet}. Liste vide si rien de nouveau.", "fiches.json", 25)
f = [x for x in f if isinstance(x, dict) and x.get("url") and cle(x["url"]) not in vus]
(D / "fiches.json").write_text(json.dumps(f, ensure_ascii=False, indent=1)); log(len(f), "fiches nouvelles")
if not f: fin(0, "Aucune ressource nouvelle.")
s = tache("jarvis", "Choix du sujet", "Lis fiches.json et choisis. JSON : {retenu: bool, angle, urls: [1 à 3 adresses tirées de fiches.json], raison}.", "selection.json", 10)
urls = [u for u in s.get("urls", []) if cle(u) in {cle(x["url"]) for x in f}]
with open(L / "deja_vu.txt", "a") as o: o.write("".join("\n" + x["url"] for x in f))
if not s.get("retenu") or not urls: fin(0, "Jarvis n'a rien retenu : " + str(s.get("raison")))
v = tache("r2d2", "Vérification scientifique", "Sources retenues : " + ", ".join(urls) + ". JSON : {affirmations: [{texte, url, extrait}], methode: [{url, type, limites}], ecarte: [{quoi, pourquoi}]}. 4 à 12 affirmations.", "verification.json", 25)
cache, ok, ko = {}, [], []
for a in v.get("affirmations", []):
    u = a.get("url", ""); e = norm(a.get("extrait", "")); cache.setdefault(u, texte(u) if cle(u) in {cle(x) for x in urls} else "")
    (ok if len(e.split()) >= 6 and e in cache[u] else ko).append(a)
log(len(ok), "extraits retrouvés,", len(ko), "écartés")
(D / "valide.json").write_text(json.dumps({"angle": s.get("angle"), "affirmations": ok, "methode": v.get("methode")}, ensure_ascii=False, indent=1))
(D / "extraits_ecartes.json").write_text(json.dumps(ko, ensure_ascii=False, indent=1))
if len(ok) < 3: fin(0, f"Abandon : {len(ok)} affirmation(s) vérifiée(s), il en faut 3.")
objections = ""
for n in (1, 2, 3):
    b = tache("watson", f"Rédaction, version {n}", "À partir de valide.json uniquement, écris billet.html (corps HTML, sans titre), puis meta.json : {titre, extrait (250 caractères au plus), tags: [..]}. Si ces fichiers existent, lis-les puis remplace-les." + objections, "meta.json", 15)
    if not (D / "billet.html").exists(): fin(1, "billet.html absent.")
    shutil.copy(D / "billet.html", D / f"billet-v{n}.html")
    r = tache("alfred", f"Revue adversariale {n}", "Confronte billet.html et meta.json à valide.json. JSON : {verdict: \"accepte\"|\"corriger\"|\"rejete\", objections: [{gravite: \"majeure\"|\"mineure\", phrase, probleme, correction}]}.", f"revue-{n}.json", 15)
    verdict = r.get("verdict"); log("Alfred :", verdict, len(r.get("objections", [])), "objection(s)")
    if verdict in ("accepte", "rejete"): break
    objections = f" Corrige selon revue-{n}.json : traite chaque objection majeure."
(D / "decision.json").write_text(json.dumps({"verdict": verdict, "versions": n}))
if verdict != "accepte":
    tache("jarvis", "Abandon du sujet", "Alfred n'a pas accepté le billet. Lis les revues et explique la raison en 5 lignes.", "abandon.md", 10); fin(0, "Sujet abandonné, voir abandon.md.")
tache("watson", "Publication", f"Exécute une seule fois : python3 {L}/publier.py {D}\nLa commande écrit elle-même publie.json. Ne modifie rien.", "publie.json", 10)
fin(0, "Publié : " + (D / "publie.json").read_text().strip())
