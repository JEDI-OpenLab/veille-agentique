#!/usr/bin/env python3
"""Envoie les courriers préparés par le PAPN. Aucun modèle de langage ici.
S'exécute sous un compte à part ; destinataires et mot de passe sont hors de portée des agents.
Sans --envoyer : aperçu seulement."""
import configparser, html, json, os, re, smtplib, ssl, sys
from email.message import EmailMessage
from pathlib import Path
C = configparser.ConfigParser(); C.read(os.environ.get("PAPN_MAIL_CONFIG", "/etc/papn-mail/config.ini")); c = C["mail"]
DEPART, ETAT = Path(c["depart"]), Path(c["etat"])
DEST = [x.strip() for x in c["destinataires"].split(",") if x.strip()]
assert 1 <= len(DEST) <= 10 and all(re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+", x) for x in DEST), "destinataires invalides"
NOM = re.compile(r"\d{4}-S\d\d\.json")

def court(x, n):
    assert isinstance(x, str) and 0 < len(x) <= n, "texte absent ou trop long"; return x
def message(d):
    objet = re.sub(r"[\r\n]+", " ", court(d["objet"], 120)); blocs = d["blocs"]; assert 1 <= len(blocs) <= 8
    par = lambda t: "".join(f"<p>{html.escape(x)}</p>" for x in t.split("\n") if x.strip())
    T, H = [court(d["titre"], 200), "", court(d["intro"], 3000)], f"<h1>{html.escape(d['titre'])}</h1>{par(d['intro'])}"
    for b in blocs:
        T += ["", court(b["titre"], 200).upper(), court(b["texte"], 5000)]; H += f"<h2>{html.escape(b['titre'])}</h2>{par(b['texte'])}<ul>"
        for l in b["liens"][:30]:
            u = l.get("url") or ""
            if not re.match(r"https?://[^\s\"<>]+$", u): continue
            T.append(f"- {court(l['titre'], 400)} ({court(l['nature'], 40)}) {u}"); H += f'<li><a href="{html.escape(u, quote=True)}">{html.escape(l["titre"])}</a> <small>({html.escape(l["nature"])})</small></li>'
        H += "</ul>"
    pied = "Préparé par des agents d'IA (PAPN). Les ressources « repérées » ne sont pas vérifiées. Envoi automatique par script."
    m = EmailMessage(); m["Subject"], m["From"], m["To"] = objet, c["expediteur"], ", ".join(DEST)
    m.set_content("\n".join(T + ["", "--", pied])); m.add_alternative(f'<html lang="fr"><body style="font-family:sans-serif;max-width:640px;line-height:1.5">{H}<hr><small>{pied}</small></body></html>', subtype="html"); return m

envoi = "--envoyer" in sys.argv
for f in sorted(DEPART.glob("*.json")):
    if not NOM.fullmatch(f.name) or f.is_symlink() or f.stat().st_size > 200_000: print("ignoré", f.name); continue
    trace = ETAT / (f.stem + ".envoye")
    if trace.exists(): continue
    try: m = message(json.loads(f.read_text()))
    except Exception as e: print("refusé", f.name, e); continue
    if not envoi: print(f"APERÇU {f.name}\nÀ : {m['To']}\nObjet : {m['Subject']}\n\n{m.get_body(('plain',)).get_content()}"); continue
    secret = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / "motdepasse").read_text().strip("\r\n")
    trace.touch(exist_ok=False)  # tracé avant l'envoi : mieux vaut un courrier manqué que deux
    with smtplib.SMTP(c["serveur"], c.getint("port", 587), timeout=40) as s:
        s.starttls(context=ssl.create_default_context()); s.login(c["identifiant"], secret); s.send_message(m)
    print("envoyé", f.name, "à", len(DEST), "destinataire(s)")
