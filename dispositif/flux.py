#!/usr/bin/env python3
"""Actualités des sources, par leurs flux. Les dates viennent des flux, pas d'un modèle."""
import html, json, re, sys, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
ICI, PAR_SOURCE = Path(__file__).resolve().parent, 6

def lignes(f):
    return [[x.strip() for x in l.split(" | ")] for l in (ICI / f).read_text().splitlines() if l.strip() and not l.lstrip().startswith("#")]
def jour(s):
    """Date d'un texte (RFC 822, ISO, JJ/MM/AAAA) ou None ; un mois seul compte au 1er."""
    s = str(s or "").strip()
    try: return parsedate_to_datetime(s).date()
    except Exception: pass
    m = re.match(r"(\d{4})-(\d\d)(?:-(\d\d))?", s)
    if m: a = (m.group(1), m.group(2), m.group(3) or 1)
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if not m: return None
        a = (m.group(3), m.group(2), m.group(1))
    try: return date(*map(int, a))
    except ValueError: return None
def net(s, n): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(s or "")))).strip()[:n]

def un(src):
    nom, url, age = src[0], src[1], int(src[2]) if len(src) > 2 else 60
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "veille-pedagogique/1.0"}), timeout=30) as f: b = f.read(6_000_000)
        if b"<!ENTITY" in b: raise ValueError("entités XML refusées")
        r, auj = [], date.today()
        for e in ET.fromstring(b).iter():
            if e.tag.split("}")[-1] not in ("item", "entry"): continue
            c = {}
            for x in e:
                k = x.tag.split("}")[-1]; v = (x.text or "").strip()
                if k == "link" and not v: v = x.get("href", "") if x.get("rel", "alternate") == "alternate" else ""
                if v and k not in c: c[k] = v
            d = jour(c.get("pubDate") or c.get("published") or c.get("date") or c.get("updated")); u = c.get("link", "")
            if d and re.match(r"https?://", u) and auj - timedelta(days=age) <= d <= auj + timedelta(days=1):
                r.append({"titre": net(c.get("title"), 220), "url": u, "source": nom, "date": str(d), "age_max": age, "resume": net(c.get("description") or c.get("summary") or c.get("content"), 220)})
        return sorted(r, key=lambda x: x["date"], reverse=True)[:PAR_SOURCE], None
    except Exception as e: return [], f"{nom} : {type(e).__name__} {str(e)[:80]}"
def collecter():
    """Rend (articles, pannes). Une source en panne n'arrête pas les autres."""
    with ThreadPoolExecutor(8) as p: res = list(p.map(un, lignes("flux.txt")))
    return [a for r, _ in res for a in r], [e for _, e in res if e]
def tournee(n=2):
    l = lignes("tournee.txt"); k = date.today().toordinal() * n
    return [l[(k + i) % len(l)] for i in range(min(n, len(l)))]
if __name__ == "__main__":
    a, e = collecter(); print(json.dumps(a, ensure_ascii=False, indent=1)); print(len(a), "articles ;", *(e or ["aucune panne"]), file=sys.stderr)
