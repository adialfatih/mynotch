#!/usr/bin/env bash
# Pasang dependensi notch di Ubuntu (sesi Xorg). Cukup dijalankan sekali.
set -e
cd "$(dirname "$0")"

if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo "Peringatan: kamu lagi di sesi Wayland. Notch butuh 'Ubuntu on Xorg'."
fi

# libxcb-cursor0 wajib untuk Qt >= 6.5 di X11; sisanya biasanya sudah ada
sudo apt-get install -y python3-venv libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
    libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-shape0

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
chmod +x jalankan.sh

echo
echo "Beres. Jalankan notch dengan:  ./jalankan.sh"
