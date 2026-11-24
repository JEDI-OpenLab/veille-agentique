#!/usr/bin/env python3
"""Surveillance du PAPN, sans IA : regarde les faits, écrit etat.json, et prépare une alerte s'il y a un problème.
Niveaux : ok, attention (à voir), probleme (à traiter). --essai n'écrit aucune alerte."""
import json, os, re, shutil, subprocess, sys, urllib.request
from datetime import datetime, timedelta
from pathlib import Path
L, PROFILS = Path.home() / "laboratoire-veille", Path.home() / ".hermes/profiles"
MNT = datetime.now(); AUJ = MNT.strftime("%Y-%m-%d"); OUVRE, LUNDI = MNT.weekday() < 5, MNT.weekday() == 0
points = []
def note(niveau, nom, detail): points.append({"niveau": niveau, "nom": nom, "detail": str(detail)[:280]})
def cmd(*a):
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=25); return r.returncode, r.stdout.strip()
    except Exception as e: return 99, str(e)
def lire(p):
    try: return json.loads(p.read_text())
    except (OSError, ValueError): return None
def controle(f):
    """Un contrôle qui plante est signalé, il n'arrête pas les autres."""
    try: f()
    except Exception as e: note("attention", f"Contrôle {f.__name__}", f"n'a pas pu se faire : {type(e).__name__} {e}")

def horaires():
    for nom, u, quoi in (("office-veille.timer", ["--user"], "de la veille"), ("papn-recap.timer", ["--user"], "du récapitulatif"), ("papn-mail.timer", [], "du courriel")):
        _, x = cmd("systemctl", *u, "is-active", nom)
        note("ok" if x == "active" else "probleme", f"Horaire {quoi}", "actif" if x == "active" else f"arrêté ({x or 'inconnu'})")
def services():
    for nom, quoi in (("hermes-gateway", "Hermes"), ("papn-direct", "PAPN en direct")):
        _, x = cmd("systemctl", "--user", "is-active", nom); note("ok" if x == "active" else "probleme", quoi, "en marche" if x == "active" else f"arrêté ({x})")
    for url, quoi, grave in (("http://127.0.0.1:2368/", "Blog Ghost", True), ("http://127.0.0.1:8765/", "Interface Hermes", False), ("http://127.0.0.1:3300/office", "Virtual Office", False)):
        try: c = urllib.request.urlopen(url, timeout=12).status
        except urllib.error.HTTPError as e: c = e.code
        except Exception as e: c = type(e).__name__
        bon = isinstance(c, int) and c < 500; note("ok" if bon else "probleme" if grave else "attention", quoi, "répond" if bon else f"ne répond pas ({c})")
def disque():
    d = shutil.disk_usage("/"); p = round(100 * d.used / d.total); note("ok" if p < 85 else "attention" if p < 93 else "probleme", "Disque", f"occupé à {p} %")
def veille():
    if not OUVRE: return
    ds = sorted((L / "dossiers").glob(AUJ + "-*"))
    if not ds: return note("probleme", "Veille du jour", "aucun passage aujourd'hui")
    d = ds[-1]; b = (d / "bilan.txt").read_text().strip() if (d / "bilan.txt").exists() else ""
    if not b:
        _, x = cmd("systemctl", "--user", "is-active", "office-veille.service")
        return note("attention" if x == "activating" else "probleme", "Veille du jour", "encore en cours" if x == "activating" else "interrompue, sans bilan")
    if b.startswith("Échec"): return note("probleme", "Veille du jour", b)
    p = lire(d / "publie.json")
    if not p and (b.startswith("Publié") or (d / "publie.json").exists()): return note("probleme", "Veille du jour", "dit avoir publié, mais la trace de publication est illisible ou absente")
    if not p: return note("ok", "Veille du jour", "terminée sans billet : " + b)
    note("ok", "Veille du jour", "terminée, billet annoncé : " + str(p.get("title")))
    ghost(p, "Billet dans Ghost")
def ghost(p, nom):
    sys.dont_write_bytecode = True; sys.path.insert(0, str(L)); import ghost_draft as g
    e = g.load_env(); u = e.get("GHOST_API_URL", "").rstrip("/") + f"/ghost/api/admin/posts/{p.get('id')}/"
    try: x = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"Authorization": "Ghost " + g.make_jwt(e["GHOST_ADMIN_API_KEY"]), "Accept-Version": "v5.0"}), timeout=20))["posts"][0]
    except urllib.error.HTTPError as err: return note("probleme", nom, "annoncé publié, mais introuvable" if err.code == 404 else f"vérification refusée ({err.code})")
    note("ok" if x["status"] == "published" else "probleme", nom, "bien publié" if x["status"] == "published" else f"annoncé publié, mais son état est « {x['status']} »")
def doublons():
    n = len(list((L / "dossiers").glob(AUJ + "-*/publie.json"))); 
    if n > 1: note("attention", "Billets du jour", f"{n} publications aujourd'hui")
def lettre():
    if not LUNDI: return
    a, s, _ = (MNT - timedelta(days=7)).isocalendar(); d = L / "semaines" / f"{a}-S{s:02d}"
    b = (d / "bilan.txt").read_text().strip() if (d / "bilan.txt").exists() else ""
    if not b: return note("probleme", "Lettre de la semaine", "absente ou interrompue")
    if not (d / "publie.json").exists(): return note("probleme" if b.startswith("Échec") else "attention", "Lettre de la semaine", b)
    note("ok", "Lettre de la semaine", "publiée"); ghost(lire(d / "publie.json") or {}, "Lettre dans Ghost")
    _, j = cmd("journalctl", "-u", "papn-mail", "--since", "today", "--no-pager", "-o", "cat")
    note("ok" if f"envoyé {d.name}.json" in j else "probleme", "Courriel de la semaine", "envoyé" if f"envoyé {d.name}.json" in j else "pas de trace d'envoi aujourd'hui")
def bascules():
    r = []
    for p in sorted(PROFILS.glob("*/logs/agent.log")):
        with open(p, "rb") as h: h.seek(max(0, p.stat().st_size - 3_000_000)); t = h.read().decode("utf8", "replace")
        v = {m for l in t.splitlines() if l.startswith(AUJ) for m in re.findall(r"Fallback activated: (\S+ → \S+)", l) if "modele-inexistant" not in m}
        r += [f"{p.parent.parent.name} : {x}" for x in sorted(v)]
    note("attention" if r else "ok", "Modèles de secours", " ; ".join(r) if r else "aucune bascule")
def sources():
    ds = sorted((L / "dossiers").glob(AUJ + "-*"))
    if not ds: return
    a, h = lire(ds[-1] / "actualites.json"), lire(ds[-1] / "recherche.json")
    if a is None and h is None: return
    vide = [n for n, x in (("flux", a), ("HAL et arXiv", h)) if not x]
    note("attention" if vide else "ok", "Sources", "rien reçu de : " + ", ".join(vide) if vide else f"{len(a)} articles, {len(h)} publications")

def principal():
    for f in (horaires, services, disque, veille, doublons, lettre, bascules, sources): controle(f)
    ordre = ("ok", "attention", "probleme"); niveau = max((p["niveau"] for p in points), key=ordre.index)
    etat = {"quand": MNT.strftime("%Y-%m-%d %H:%M"), "niveau": niveau, "points": sorted(points, key=lambda p: -ordre.index(p["niveau"]))}
    t = L / ".etat.tmp"; t.write_text(json.dumps(etat, ensure_ascii=False, indent=1)); t.rename(L / "etat.json")
    depart = Path("/var/spool/papn-mail")
    if niveau == "probleme" and "--essai" not in sys.argv and depart.is_dir():
        f = depart / f"alerte-{AUJ}.json"
        if not f.exists():
            t = depart / f".alerte-{AUJ}.tmp"; t.write_text(json.dumps({"quand": etat["quand"], "points": [p for p in etat["points"] if p["niveau"] != "ok"]}, ensure_ascii=False)); t.chmod(0o640); t.rename(f)
    for p in etat["points"]: print(f"{p['niveau']:9} {p['nom']} : {p['detail']}")
    print("=>", niveau)
if __name__ == "__main__": principal()
