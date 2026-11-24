#!/usr/bin/env python3
"""Publie une seule fois le billet accepté d'un dossier du PAPN."""
import json, subprocess, sys
from pathlib import Path
d = Path(sys.argv[1]).resolve()
recu = d / "publie.json"
if recu.exists():
    print("Déjà publié :", recu.read_text()); sys.exit(0)
dec = json.loads((d / "decision.json").read_text())
if dec.get("verdict") != "accepte":
    sys.exit("Publication refusée : pas d'acceptation d'Alfred.")
m = json.loads((d / "meta.json").read_text())
r = subprocess.run([sys.executable, str(Path(__file__).parent / "ghost_draft.py"), m["titre"], str(d / "billet.html"),
                    m.get("extrait", "")[:250], ",".join(m.get("tags") or ["Veille pédagogique"]), "published"], capture_output=True, text=True)
if r.returncode:
    sys.exit("Échec Ghost : " + r.stderr[:500])
recu.write_text(r.stdout); print(r.stdout)
