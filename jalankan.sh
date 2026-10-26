#!/usr/bin/env bash
# Jalankan notch di background (Ubuntu). Log error ada di notch.log kalau ada masalah.
cd "$(dirname "$0")"
nohup .venv/bin/python notch.py > notch.log 2>&1 &
