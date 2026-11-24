#!/bin/bash
# Installe l'envoi hebdomadaire sous un compte a part. A lancer une fois : sudo bash installer.sh
# N'active pas l'horaire et n'envoie rien.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "A lancer avec sudo."; exit 1; }
ICI="$(cd "$(dirname "$0")" && pwd)"; AGENTS="${SUDO_USER:?a lancer avec sudo depuis le compte des agents}"
read -rp "Serveur d'envoi : " SERVEUR
read -rp "Identifiant : " IDENT
read -rp "Adresse d'expedition : " EXP
read -rp "Destinataires, separes par des virgules : " DEST
read -rsp "Mot de passe (invisible) : " MDP; echo
id papn-mail >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin papn-mail
install -d -o root -g root -m 755 /opt/papn-mail
install -o root -g root -m 755 "$ICI/envoyer.py" /opt/papn-mail/envoyer.py
install -d -o root -g papn-mail -m 750 /etc/papn-mail
install -d -o papn-mail -g papn-mail -m 700 /var/lib/papn-mail
install -d -o "$AGENTS" -g papn-mail -m 2750 /var/spool/papn-mail
umask 077
printf '%s' "$MDP" > /etc/papn-mail/motdepasse; unset MDP
printf '[mail]\nserveur = %s\nport = 587\nidentifiant = %s\nexpediteur = %s\ndestinataires = %s\ndepart = /var/spool/papn-mail\netat = /var/lib/papn-mail\n' "$SERVEUR" "${IDENT//%/%%}" "$EXP" "$DEST" > /etc/papn-mail/config.ini
chown root:papn-mail /etc/papn-mail/config.ini; chmod 640 /etc/papn-mail/config.ini
umask 022
cat > /etc/systemd/system/papn-mail.service <<'S'
[Unit]
Description=PAPN : envoi du recapitulatif hebdomadaire
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=papn-mail
Group=papn-mail
LoadCredential=motdepasse:/etc/papn-mail/motdepasse
ExecStart=/usr/bin/python3 -I /opt/papn-mail/envoyer.py --envoyer
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/var/lib/papn-mail
S
cat > /etc/systemd/system/papn-mail.timer <<'S'
[Unit]
Description=PAPN : envoi du recapitulatif, le lundi a 9 h 30

[Timer]
OnCalendar=Mon 09:30:00 Europe/Paris
Persistent=false

[Install]
WantedBy=timers.target
S
systemctl daemon-reload
echo "Installe. Rien n'est envoye, l'horaire n'est pas actif."
echo "Apercu  : sudo -u papn-mail python3 -I /opt/papn-mail/envoyer.py"
echo "Envoyer : sudo systemctl start papn-mail"
echo "Activer : sudo systemctl enable --now papn-mail.timer"
