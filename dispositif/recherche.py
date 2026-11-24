#!/usr/bin/env python3
"""Publications récentes de HAL et arXiv, par leurs interfaces publiques."""
import html, json, re, sys, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
JOURS, MAX = 30, 12

def lire(url):
    r = urllib.request.Request(url, headers={"User-Agent": "veille-pedagogique/1.0"})
    with urllib.request.urlopen(r, timeout=40) as f: return f.read(5_000_000)
def net(s): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()

def hal():
    q = ('("intelligence artificielle" OR "artificial intelligence" OR "IA générative" OR "generative AI" OR "pédagogie universitaire" OR "numérique éducatif") '
         'AND ("enseignement supérieur" OR "higher education" OR université OR étudiants OR "engineering education" OR pédagogie)')
    depuis = (datetime.now(timezone.utc) - timedelta(days=JOURS)).strftime("%Y-%m-%dT00:00:00Z")
    p = [("q", q), ("fq", "domainAllCode_s:shs.edu"), ("fq", f"submittedDate_tdate:[{depuis} TO *]"), ("rows", MAX), ("sort", "submittedDate_tdate desc"),
         ("fl", "title_s,uri_s,submittedDate_s,producedDate_s,docType_s,abstract_s,fileMain_s"), ("wt", "json")]
    d = json.loads(lire("https://api.archives-ouvertes.fr/search/?" + urllib.parse.urlencode(p)))
    return [{"titre": net((x.get("title_s") or [""])[0]), "url": x["uri_s"], "texte_integral": x.get("fileMain_s"), "source": "HAL", "type": x.get("docType_s"),
             "date": x.get("producedDate_s"), "depot": (x.get("submittedDate_s") or "")[:10], "resume": net((x.get("abstract_s") or [""])[0])[:4000]} for x in d["response"]["docs"]]

def arxiv():
    q = '(cat:cs.CY OR cat:cs.HC OR cat:cs.AI) AND (abs:"higher education" OR abs:"university students" OR abs:"engineering education") AND (abs:"generative AI" OR abs:LLM OR abs:"artificial intelligence" OR abs:ChatGPT)'
    u = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"search_query": q, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": MAX})
    N, lim, r = {"a": "http://www.w3.org/2005/Atom"}, datetime.now(timezone.utc) - timedelta(days=JOURS), []
    for e in ET.fromstring(lire(u)).findall("a:entry", N):
        t = lambda k: net(e.findtext("a:" + k, "", N))
        if not t("published") or datetime.fromisoformat(t("published").replace("Z", "+00:00")) < lim: continue
        i = re.sub(r"v\d+$", "", t("id").rsplit("/abs/", 1)[-1])
        r.append({"titre": t("title"), "url": "https://arxiv.org/abs/" + i, "texte_integral": "https://arxiv.org/pdf/" + i, "source": "arXiv", "type": "prépublication", "date": t("published")[:10], "resume": t("summary")[:4000]})
    return r

def chercher():
    """Rend (publications, erreurs) ; une source en panne n'arrête pas l'autre."""
    res, err = [], []
    for nom, f in (("HAL", hal), ("arXiv", arxiv)):
        try: res += f()
        except Exception as e: err.append(f"{nom} : {type(e).__name__} {str(e)[:120]}")
    return res, err
if __name__ == "__main__":
    r, e = chercher(); print(json.dumps(r, ensure_ascii=False, indent=1)); print(len(r), e, file=sys.stderr)
