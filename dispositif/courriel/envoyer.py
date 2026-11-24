#!/usr/bin/env python3
"""Envoie les courriers préparés par le PAPN. Aucun modèle de langage ici.
S'exécute sous un compte à part ; destinataires et mot de passe sont hors de portée des agents.
Sans --envoyer : aperçu seulement (--html pour le modèle)."""
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
def signature():
    """Signature fixe : elle ne dépend ni des agents ni du courrier. Les liens viennent de la configuration."""
    e, liens = html.escape, [(n, c.get(k, "").strip()) for n, k in (("Lire le blog", "lien_blog"), ("Suivre l'équipe en direct", "lien_direct"), ("Découvrir le projet", "lien_projet"))]
    liens = [(n, u) for n, u in liens if re.match(r"https?://[^\s\"<>]+$", u)]
    T = ["Alfred", "Rédacteur de la lettre de la semaine, agent d'IA", "", "PAPN, Pôle des Agents Pédagogiques Numériques", "Laboratoire pédagogique, Centrale Lille", "",
         "Relecture : Velma. Mise en page : Hedwige. Veille : Nestor."] + [f"{n} : {u}" for n, u in liens]
    L = " &nbsp;|&nbsp; ".join(f'<a href="{e(u, quote=True)}" style="color:#1C5D73;font-weight:bold;text-decoration:none">{e(n)}</a>' for n, u in liens)
    H = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="5" style="background:#1C5D73;font-size:0;line-height:0">&nbsp;</td><td style="padding:2px 0 2px 18px">
<div style="font:bold 22px/1.25 {SERIF};color:#16242A">Alfred</div>
<div style="font:15px/1.5 {SANS};color:#526268">Rédacteur de la lettre de la semaine, agent d'IA</div>
<div style="font:bold 15px/1.5 {SANS};color:#1C5D73;padding-top:12px">PAPN, Pôle des Agents Pédagogiques Numériques</div>
<div style="font:15px/1.5 {SANS};color:#16242A">Laboratoire pédagogique, Centrale Lille</div>
<div style="font:13px/1.5 {SANS};color:#526268;padding-top:12px">Relecture : Velma. Mise en page : Hedwige. Veille : Nestor.</div>
<div style="font:14px/1.9 {SANS};padding-top:6px">{L}</div></td></tr></table>"""
    return T, H

SERIF, SANS = "Georgia,'Times New Roman',serif", "Arial,Helvetica,sans-serif"
def message(d):
    """Modèle du mail : tout texte est échappé, seuls les liens http(s) passent."""
    e, objet, blocs = html.escape, re.sub(r"[\r\n]+", " ", court(d["objet"], 120)), d["blocs"]; assert 1 <= len(blocs) <= 8
    periode = court(d.get("periode") or " ", 80).strip()
    par = lambda t: "".join(f'<p style="margin:0 0 12px;font:16px/1.6 {SANS};color:#16242A">{e(x.strip())}</p>' for x in t.split("\n") if x.strip())
    T, H = ["PAPN, la veille de la semaine", periode, "", court(d["titre"], 200), "", court(d["intro"], 3000)], ""
    for k, b in enumerate(blocs):
        T += ["", "", court(b["titre"], 200).upper(), "", court(b["texte"], 5000)]; liens = ""
        for l in b["liens"][:30]:
            u = l.get("url") or ""
            if not re.match(r"https?://[^\s\"<>]+$", u): continue
            t, n = court(l["titre"], 400), court(l["nature"], 40); teinte = "#97600B" if "non vérifié" in n else "#2F7350"
            T += ["", f"> {t}", f"  {n}", f"  {u}"]
            liens += f'<tr><td style="padding:10px 0 0;font:15px/1.45 {SANS}"><a href="{e(u, quote=True)}" style="color:#1C5D73;font-weight:bold">{e(t)}</a><br><span style="color:{teinte};font-size:13px">{e(n)}</span></td></tr>'
        fond = "background:#DCEBF1;" if not k else "border-top:1px solid #D2DCDB;"
        H += f'<tr><td style="{fond}padding:26px 32px"><h2 style="margin:0 0 12px;font:bold 21px/1.3 {SERIF};color:#16242A">{e(b["titre"])}</h2>{par(b["texte"])}<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{liens}</table></td></tr>'
    pied = ["Vert : billet publié, accepté par Velma, la contradictrice. Ambre : ressource seulement repérée par Nestor, à vérifier avant de s'en servir.",
            "Cette lettre est produite par des agents d'IA, qui peuvent se tromper. Elle est envoyée automatiquement par un script, une fois par semaine."]
    sig_t, sig_h = signature()
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(objet)}</title></head>
<body style="margin:0;padding:0;background:#F2F5F4"><div style="display:none;max-height:0;overflow:hidden">{e(d["intro"][:140])}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F2F5F4"><tr><td align="center" style="padding:20px 10px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;background:#ffffff">
<tr><td style="background:#1C5D73;padding:20px 32px;font:15px/1.5 {SANS};color:#ffffff"><b>PAPN</b>, la veille de la semaine<br><span style="color:#DCEBF1">{e(periode)}</span></td></tr>
<tr><td style="padding:30px 32px 20px"><h1 style="margin:0 0 16px;font:bold 27px/1.25 {SERIF};color:#16242A">{e(d["titre"])}</h1>{par(d["intro"])}</td></tr>
{H}<tr><td style="border-top:1px solid #D2DCDB;padding:30px 32px">{sig_h}</td></tr>
<tr><td style="background:#F2F5F4;padding:20px 32px;font:13px/1.55 {SANS};color:#526268">{"<br><br>".join(e(x) for x in pied)}</td></tr>
</table></td></tr></table></body></html>"""
    m = EmailMessage(); m["Subject"], m["From"], m["To"] = objet, c["expediteur"], ", ".join(DEST)
    m.set_content("\n".join(T + ["", "", "-- "] + sig_t + [""] + pied)); m.add_alternative(page, subtype="html"); return m

envoi = "--envoyer" in sys.argv and "--html" not in sys.argv
for f in sorted(DEPART.glob("*.json")):
    if not NOM.fullmatch(f.name) or f.is_symlink() or f.stat().st_size > 200_000: print("ignoré", f.name); continue
    trace = ETAT / (f.stem + ".envoye")
    if trace.exists(): continue
    try: m = message(json.loads(f.read_text()))
    except Exception as e: print("refusé", f.name, e); continue
    if "--html" in sys.argv: print(m.get_body(("html",)).get_content()); continue
    if not envoi: print(f"APERÇU {f.name}\nÀ : {m['To']}\nObjet : {m['Subject']}\n\n{m.get_body(('plain',)).get_content()}"); continue
    secret = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / "motdepasse").read_text().strip("\r\n")
    trace.touch(exist_ok=False)  # tracé avant l'envoi : mieux vaut un courrier manqué que deux
    with smtplib.SMTP(c["serveur"], c.getint("port", 587), timeout=40) as s:
        s.starttls(context=ssl.create_default_context()); s.login(c["identifiant"], secret); s.send_message(m)
    print("envoyé", f.name, "à", len(DEST), "destinataire(s)")
