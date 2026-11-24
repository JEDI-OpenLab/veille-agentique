#!/usr/bin/env python3
"""PAPN en direct : vue en lecture seule du circuit. N'écoute que sur 127.0.0.1."""
import json, os, re, subprocess, time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
DOS = Path(os.environ.get("PAPN_DOSSIERS", Path.home() / "laboratoire-veille/dossiers"))
SEM = DOS.parent / "semaines"
PROFILS = Path(os.environ.get("PAPN_PROFILS", Path.home() / ".hermes/profiles"))
PORT = int(os.environ.get("PAPN_PORT", "8770"))
PAGE = (Path(__file__).parent / "direct.html").read_bytes()
AGENTS = ["nestor", "jarvis", "r2d2", "watson", "alfred"]
NOM = re.compile(r"^\d{4}-\d\d-\d\d-\d\dh\d\d$")

def lire(d, f, defaut=None):
    try:
        x = (d / f).read_text()
        return json.loads(x) if f.endswith(".json") else x
    except (OSError, ValueError): return defaut

def prevu(a):
    try: m = re.search(r"(?m)^model:\n(?:  .*\n)*?  default: (.+)$", (PROFILS / a / "config.yaml").read_text())
    except OSError: return None
    return m.group(1).strip("'\" ") if m else None

def modeles(a, debut, fin):
    """Modèles réellement appelés et bascules de secours entre deux dates, d'après le journal de l'agent."""
    c, b = {}, set()
    for f in sorted((PROFILS / a / "logs").glob("agent.log*")):
        try:
            with open(f, "rb") as h:
                h.seek(max(0, f.stat().st_size - 4_000_000)); t = h.read().decode("utf8", "replace")
        except OSError: continue
        for l in t.splitlines():
            if not debut <= l[:19] <= fin: continue
            m = re.search(r"API call #\d+: model=(\S+)", l)
            if m: c[m.group(1)] = c.get(m.group(1), 0) + 1
            m = re.search(r"Fallback activated: (\S+) → (\S+)", l)
            if m: b.add(f"{m.group(1)} → {m.group(2)}")
    return c, sorted(b)

def suivre(noms, lignes, debut, fin, en_marche):
    """État de chaque agent d'après le fil du passage."""
    qui, ag = None, {a: {"prevu": prevu(a), "fait": 0, "tache": None} for a in noms}
    for h, t in lignes:
        p = t.split(" ", 1); a = p[0]
        if a in ag:
            if re.search(r" t_\w+$", t): qui = a; ag[a]["tache"] = re.sub(r" t_\w+$", "", p[1]); ag[a]["depuis"] = h
            elif "terminé" in t: ag[a]["fait"] += 1; qui = None
            elif "refusée" in t: qui = None
    for a in noms:
        ag[a]["reels"], ag[a]["bascules"] = modeles(a, debut, fin)
        ag[a]["etat"] = "travaille" if en_marche and qui == a else "fait" if ag[a]["fait"] else "attend"
    return ag
def fil(d):
    return [(m.group(1), m.group(2)) for m in (re.match(r"(\d\d:\d\d:\d\d) (.*)", l) for l in (lire(d, "journal.txt", "") or "").splitlines()) if m]
def revues(d):
    r = []
    for f in sorted(d.glob("revue-*.json")):
        x = lire(d, f.name, {}) or {}
        r.append({"verdict": x.get("verdict"), "objections": [{k: str(o.get(k, ""))[:600] for k in ("gravite", "phrase", "probleme")} for o in x.get("objections", []) if isinstance(o, dict)]})
    return r

def service(*noms):
    try: r = subprocess.run(["systemctl", "--user", "show", *noms, "-p", "ActiveState", "--value"], capture_output=True, text=True, timeout=5).stdout.split()
    except Exception: return None
    return any(x in ("active", "activating") for x in r)

def prochain(nom, utilisateur=True):
    try:
        x = subprocess.run(["systemctl"] + ["--user"] * utilisateur + ["list-timers", nom, "--no-pager", "--output=json"], capture_output=True, text=True, timeout=5).stdout
        return (json.loads(x) or [{}])[0].get("next")
    except Exception: return None

def recap():
    """Dernier récapitulatif de l'équipe administrative."""
    ds = [d for d in SEM.glob("*") if d.is_dir() and re.fullmatch(r"\d{4}-S\d\d(-essai-\d\dh\d\d|-essai-\d+h\d\d)?", d.name) and (d / "semaine.json").exists()] if SEM.exists() else []
    noms, vide = ["moneypenny", "alfred", "hedwige"], {"id": None}
    if not ds: return {**vide, "agents": {a: {"prevu": prevu(a), "reels": {}, "bascules": [], "fait": 0, "tache": None, "etat": "attend"} for a in noms}}
    d = max(ds, key=lambda x: (x / "semaine.json").stat().st_mtime); l = fil(d); bilan = (lire(d, "bilan.txt") or "").strip()
    jour = datetime.fromtimestamp((d / "semaine.json").stat().st_mtime); pub = lire(d, "publie.json") or {}
    marche = not bilan and bool(service("papn-recap.service", "papn-recap-essai.service"))
    if pub.get("ok"): e = "publie"
    elif bilan.startswith("Échec"): e = "echec"
    elif bilan.startswith("Essai"): e = "essai"
    elif bilan: e = "abandon"
    else: e = "en_cours" if marche else "interrompu"
    fin = datetime.now() if marche else datetime.fromtimestamp(max(f.stat().st_mtime for f in d.glob("*")))
    f = "%Y-%m-%d %H:%M:%S"; sem = lire(d, "semaine.json", {}) or {}
    return {"id": d.name, "jour": jour.strftime("%Y-%m-%d"), "etat": e, "debut": l[0][0] if l else None, "titre": (lire(d, "recap.json", {}) or {}).get("titre"), "bilan": "" if pub else bilan,
            "du": sem.get("du"), "au": sem.get("au"), "billets": len(sem.get("billets", [])), "ressources": len(sem.get("ressources", [])),
            "agents": suivre(noms, l, jour.strftime("%Y-%m-%d ") + (l[0][0] if l else "00:00:00"), fin.strftime(f), marche), "revues": revues(d),
            "journal": [{"h": h, "t": re.sub(r" t_\w+$", "", t)} for h, t in l if not t.startswith("FIN")]}

def dossier(d, detail=False, actif=None):
    lignes, jour = fil(d), d.name[:10]
    bilan = (lire(d, "bilan.txt") or "").strip()
    pub, dec = lire(d, "publie.json"), lire(d, "decision.json", {}) or {}
    if pub and pub.get("ok"): etat = "publie"
    elif bilan.startswith("Échec"): etat = "echec"
    elif bilan: etat = "abandon"
    else: etat = "en_cours" if actif and detail else "interrompu"
    r = {"id": d.name, "etat": etat, "titre": (pub or {}).get("title") or (lire(d, "meta.json", {}) or {}).get("titre"),
         "bilan": "" if pub else bilan, "versions": len(list(d.glob("billet-v*.html"))), "debut": lignes[0][0] if lignes else None, "fin": lignes[-1][0] if lignes else None}
    if not detail: return r
    deb = f"{jour} {lignes[0][0]}" if lignes else jour
    if etat == "en_cours": fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        f = datetime.strptime(f"{jour} {lignes[-1][0]}", "%Y-%m-%d %H:%M:%S") if lignes else datetime.fromisoformat(jour)
        if lignes and lignes[-1][0] < lignes[0][0]: f += timedelta(days=1)
        fin = f.strftime("%Y-%m-%d %H:%M:%S")
    ag = suivre(AGENTS, lignes, deb, fin, etat == "en_cours")
    s, v = lire(d, "selection.json", {}) or {}, lire(d, "valide.json", {}) or {}
    ko = lire(d, "extraits_ecartes.json", []) or []
    r.update(agents=ag, revues=revues(d), journal=[{"h": h, "t": re.sub(r" t_\w+$", "", t)} for h, t in lignes if not t.startswith("FIN")],
             sujet=s.get("angle"), urls=[u for u in s.get("urls", []) if re.match(r"https?://", str(u))], ressources=len(lire(d, "fiches.json", []) or []),
             extraits={"ok": len(v.get("affirmations", [])), "ko": len(ko)} if v else None, accord=dec.get("verdict"))
    return r

cache = {"t": 0, "v": b"{}"}
def etat():
    if time.time() - cache["t"] > 4:
        actif = service("office-veille.service", "office-essai.service"); ds = sorted((d for d in DOS.glob("*") if d.is_dir() and NOM.match(d.name)), reverse=True)[:40] if DOS.exists() else []
        x = {"maintenant": datetime.now().strftime("%H:%M:%S"), "actif": actif, "prochain": prochain("office-veille.timer"), "recap": recap(), "prochain_recap": prochain("papn-recap.timer"), "prochain_mail": prochain("papn-mail.timer", False), "dernier": dossier(ds[0], True, actif) if ds else None, "historique": [dossier(d) for d in ds]}
        if x["dernier"] and x["historique"]: x["historique"][0]["etat"] = x["dernier"]["etat"]
        cache.update(t=time.time(), v=json.dumps(x, ensure_ascii=False).encode())
    return cache["v"]

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        try:
            if p.endswith("/api"): c, t = etat(), "application/json"
            elif p in ("", "/direct"): c, t = PAGE, "text/html"
            else: return self.send_error(404)
        except Exception: return self.send_error(500)
        self.send_response(200)
        for k, v in {"Content-Type": t + "; charset=utf-8", "Content-Length": str(len(c)), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                     "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'"}.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(c)
    def log_message(self, *a): pass

if __name__ == "__main__": ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
