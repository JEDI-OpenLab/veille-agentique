#!/usr/bin/env python3
"""Connecteur Ghost du PAPN."""
import hashlib
import hmac
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".hermes/profiles/watson/.env"

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env

def make_jwt(admin_key: str) -> str:
    key_id, secret_hex = admin_key.split(":", 1)
    secret = bytes.fromhex(secret_hex)
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT", "kid": key_id}).encode()).rstrip(b"=")
    now = int(time.time())
    payload = base64.urlsafe_b64encode(json.dumps({"iat": now, "exp": now + 300, "aud": "/admin/"}).encode()).rstrip(b"=")
    signing_input = header + b"." + payload
    sig = base64.urlsafe_b64encode(hmac.new(secret, signing_input, hashlib.sha256).digest()).rstrip(b"=")
    return (signing_input + b"." + sig).decode("ascii")

def create_draft(title: str, html_content: str, excerpt: str = "", tags: list[str] | None = None, status: str = "draft"):
    env = load_env()
    api_url = env.get("GHOST_API_URL", "http://127.0.0.1:2368").rstrip("/")
    admin_key = env.get("GHOST_ADMIN_API_KEY", "")
    if ":" not in admin_key:
        raise RuntimeError("GHOST_ADMIN_API_KEY manquante ou invalide dans ~/.hermes/profiles/watson/.env")

    token = make_jwt(admin_key)
    post_obj = {
        "title": title,
        "html": html_content,
        "status": status,
    }
    if excerpt:
        post_obj["custom_excerpt"] = excerpt[:300]
    if tags:
        post_obj["tags"] = [{"name": t} for t in tags]

    body = json.dumps({"posts": [post_obj]}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/ghost/api/admin/posts/?source=html",
        data=body,
        headers={
            "Authorization": f"Ghost {token}",
            "Content-Type": "application/json",
            "Accept-Version": "v5.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            created = data["posts"][0]
            print(json.dumps({
                "ok": True,
                "id": created["id"],
                "title": created["title"],
                "status": created["status"],
                "url": created.get("url"),
                "editor_url": f"{api_url}/ghost/#/posts/{created['id']}"
            }, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(json.dumps({"ok": False, "code": e.code, "error": e.read().decode("utf-8", errors="replace")}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: ghost_draft.py <titre> <fichier_html> [extrait] [tag1,tag2]", file=sys.stderr)
        sys.exit(1)
    title = sys.argv[1]
    html = Path(sys.argv[2]).read_text(encoding="utf-8")
    excerpt = sys.argv[3] if len(sys.argv) > 3 else ""
    tags = [t.strip() for t in sys.argv[4].split(",") if t.strip()] if len(sys.argv) > 4 else ["Veille pédagogique"]
    status = sys.argv[5] if len(sys.argv) > 5 else "draft"
    create_draft(title, html, excerpt, tags, status)
