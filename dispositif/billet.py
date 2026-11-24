#!/usr/bin/env python3
"""Pages sources, assemblage et contrôle du billet. L'agent écrit du texte et cite des numéros ; le code écrit le HTML, les liens et les titres."""
import html, re, unicodedata, urllib.parse
from html.parser import HTMLParser
def norm(s):
    return re.sub(r"[\W_]+", " ", unicodedata.normalize("NFKC", html.unescape(str(s))).lower()).strip()
VIDES = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

class Lecteur(HTMLParser):
    """Titre de la page, texte découpé par rubrique, et liens."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.h1, self.t, self.rub, self.seg, self.liens = "", "", "", [], []; self.pile = []
    def handle_starttag(self, t, a):
        if t == "a": self.liens.append(dict(a).get("href") or "")
        if t in ("script", "style", "title", "h1", "h2", "h3", "h4", "h5", "summary", "button"): self.pile.append([t, ""])
    def handle_endtag(self, t):
        if self.pile and self.pile[-1][0] == t:
            k, x = self.pile.pop(); x = re.sub(r"\s+", " ", x).strip()
            if k == "title": self.t = self.t or x
            elif k == "h1": self.h1 = self.h1 or x
            elif k not in ("script", "style") and 2 < len(x) < 140 and not re.search(r"menu|fermer|ouvrir|recherche|partager|connexion|^important|vigilance$", x, re.I): self.rub = x
    def handle_data(self, d):
        if self.pile:
            self.pile[-1][1] += d
            if self.pile[-1][0] in ("script", "style", "title"): return
        self.seg.append((self.rub, d))
def analyser(brut):
    p = Lecteur(); p.feed(brut); p.close()
    titre = re.sub(r"^Title:\s*", "", p.h1 or re.split(r"\s+[|–]\s+", p.t)[0]).strip()
    return {"titre": titre[:220], "segments": p.seg, "liens": p.liens, "texte": norm(" ".join(x for _, x in p.seg))}
def rubrique(page, extrait):
    """Rubrique de la page où commence l'extrait, ou ''."""
    pos, cible = 0, page["texte"].find(norm(extrait))
    if cible < 0: return ""
    for r, x in page["segments"]:
        n = norm(x)
        if n: pos += len(n) + 1
        if pos > cible: return r
    return ""
def relie(page, cle_autre, cle): return any(cle_autre and cle(u) == cle_autre for u in page["liens"] if u.startswith("http")) or any(cle_autre.split("/", 3)[-1:] == [u.strip("/")] for u in page["liens"] if u.startswith("/") and len(u) > 8)
def passage(url, extrait):
    """Lien menant au passage cité (les navigateurs récents le surlignent)."""
    m = str(extrait).split(); q = lambda x: urllib.parse.quote(" ".join(x), safe="").replace("-", "%2D")
    return url.split("#")[0] + "#:~:text=" + (q(m[:5]) + "," + q(m[-4:]) if len(m) > 10 else q(m))

NATURES = ("accroche", "faits", "pistes", "limites")
LIEN_SUPPOSE = re.compile(r"\b(associée?s?|complémentaires?|dans la continuité|prolonge\w*|dans le même (?:cadre|projet|programme)|issue? de ce|qui l[’']accompagne)\b", re.I)
def defauts(b, valide):
    """Ce que le code sait refuser dans un brouillon."""
    d, A = [], {a["id"]: a for a in valide["affirmations"]}; mots, sec = 0, b.get("sections")
    for k in ("titre", "extrait"):
        if not str(b.get(k, "")).strip(): d.append(f"{k} absent")
    if not isinstance(sec, list) or not sec: return d + ["sections absentes"]
    reliees = {frozenset(x) for x in valide.get("relations", [])}; n = 0; vu = set()
    for s in sec:
        if s.get("nature") not in NATURES: d.append(f"nature inconnue : {s.get('nature')}"); continue
        vu.add(s["nature"])
        for p in s.get("paragraphes", []):
            n += 1; t = str(p.get("texte", "")); c = p.get("affirmations") or []; mots += len(t.split())
            if re.search(r"https?://|www\.|<\w|\]\(", t): d.append(f"§{n} : ni lien ni HTML, le code s'en charge")
            if re.search(r"\b[AS]\d{1,2}\b", t): d.append(f"§{n} : les numéros vont dans « affirmations », pas dans le texte")
            inc = [x for x in c if x not in A]
            if inc: d.append(f"§{n} : affirmations inconnues {inc}"); continue
            if s["nature"] == "faits" and not c: d.append(f"§{n} : un paragraphe de faits cite au moins une affirmation")
            if s["nature"] in ("accroche", "pistes") and c: d.append(f"§{n} : accroche et pistes ne citent pas d'affirmation, ce ne sont pas des faits")
            src = {A[x]["source"] for x in c}
            if len(src) > 1 and not all(frozenset((x, y)) in reliees for x in src for y in src if x < y): d.append(f"§{n} : réunit {sorted(src)}, que rien ne relie ; un paragraphe par source")
            m = LIEN_SUPPOSE.search(t)
            if m and s["nature"] in ("faits", "limites") and len(valide["sources"]) > 1 and not reliees: d.append(f"§{n} : « {m.group(0)} » suppose un lien entre sources qui n'est pas établi")
    for k in ("accroche", "faits", "limites"):
        if k not in vu: d.append(f"section « {k} » absente")
    if not 480 <= mots <= 750: d.append(f"{mots} mots (500 à 700 attendus)")
    return d
def numeroter(b):
    """Paragraphes numérotés, pour la contradiction."""
    r, n = [], 0
    for s in b["sections"]:
        for p in s.get("paragraphes", []): n += 1; r.append({"n": n, "section": s.get("titre") or s["nature"], "nature": s["nature"], "texte": p["texte"], "affirmations": p.get("affirmations") or []})
    return r
def assembler(b, valide):
    """HTML final : appels de note, vrais titres des pages, rubrique et lien vers chaque passage."""
    e = lambda x: html.escape(str(x), quote=True); gras = lambda x: re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e(x).replace("&#x27;", "’"))
    A, S, ordre, o = {a["id"]: a for a in valide["affirmations"]}, {s["id"]: s for s in valide["sources"]}, [], []
    for s in b["sections"]:
        if s.get("titre") and s["nature"] != "accroche": o.append(f"<h2>{gras(s['titre'])}</h2>")
        ps = []
        for p in s.get("paragraphes", []):
            notes = ""
            for i in p.get("affirmations") or []:
                if i not in ordre: ordre.append(i)
                a = A[i]; notes += f'<sup><a href="{e(a.get("lien") or S[a["source"]]["url"])}">[{ordre.index(i) + 1}]</a></sup>'
            ps.append(gras(p["texte"]) + notes)
        o.append("<ul>" + "".join(f"<li>{x}</li>" for x in ps) + "</ul>" if s["nature"] == "pistes" else "".join(f"<p>{x}</p>" for x in ps))
    o.append("<h2>Sources</h2><ul>")
    for sid in dict.fromkeys(A[i]["source"] for i in ordre):
        s = S[sid]; n = [(ordre.index(i) + 1, A[i].get("rubrique")) for i in ordre if A[i]["source"] == sid]
        ou = "; ".join(f"[{k}]" + (f" rubrique « {e(r)} »" if r else "") for k, r in n)
        o.append(f'<li><a href="{e(s["url"])}">{e(s["titre"])}</a>' + ("" if s.get("titre_verifie") else " (titre non vérifié)") + (f", {e(s['nature'])}" if s.get("nature") else "") + f". {ou}</li>")
    return "\n".join(o) + "</ul>\n"
