#!/usr/bin/env bash
# Jalankan notch di background (Ubuntu). Log error ada di notch.log kalau ada masalah.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Belum terpasang. Jalankan dulu:  bash install_ubuntu.sh" >&2
    exit 1
fi
# setsid: lepas dari terminal, jadi tetap hidup walau terminalnya ditutup
setsid -f .venv/bin/python notch.py > notch.log 2>&1 < /dev/null
