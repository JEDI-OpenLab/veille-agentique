#!/bin/bash
# Ajoute l'alerte par courriel de la surveillance. A lancer une fois : sudo bash installer-alerte.sh
# Ne touche ni au mot de passe ni aux destinataires de la lettre.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "A lancer avec sudo."; exit 1; }
[ -f /etc/papn-mail/config.ini ] || { echo "L'envoi n'est pas installe."; exit 1; }
ICI="$(cd "$(dirname "$0")" && pwd)"
read -rp "Adresse qui recevra les alertes (une seule) : " A
[[ "$A" =~ ^[^@[:space:],\;\<\>]+@[^@[:space:],\;\<\>]+$ ]] || { echo "Adresse invalide, rien n'a change."; exit 1; }
install -o root -g root -m 755 "$ICI/envoyer.py" /opt/papn-mail/envoyer.py
sed -i '/^destinataire_alerte/d' /etc/papn-mail/config.ini
printf 'destinataire_alerte = %s\n' "${A//%/%%}" >> /etc/papn-mail/config.ini
sed -e 's#^Description=.*#Description=PAPN : alerte de surveillance#' -e 's#envoyer.py --envoyer#envoyer.py --alertes --envoyer#' /etc/systemd/system/papn-mail.service > /etc/systemd/system/papn-alerte.service
cat > /etc/systemd/system/papn-alerte.timer <<'S'
[Unit]
Description=PAPN : alerte de surveillance, jours ouvres a 11 h 10

[Timer]
OnCalendar=Mon..Fri 11:10:00 Europe/Paris
Persistent=true

[Install]
WantedBy=timers.target
S
systemctl daemon-reload
echo "Installe. L'horaire n'est pas actif."
echo "Activer : sudo systemctl enable --now papn-alerte.timer"
