#!/usr/bin/env bash
# Pasang dependensi notch di Ubuntu (sesi Xorg). Cukup dijalankan sekali.
set -e
cd "$(dirname "$0")"

if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    echo "Peringatan: kamu lagi di sesi Wayland. Notch butuh 'Ubuntu on Xorg'."
fi

# libxcb-cursor0 wajib untuk Qt >= 6.5 di X11; sisanya biasanya sudah ada
# Lock-Timeout: tunggu kalau Software Updater lagi jalan, jangan langsung gagal
sudo apt-get -o DPkg::Lock::Timeout=600 install -y python3-venv libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
    libxcb-keysyms1 libxcb-image0 libxcb-render-util0 libxcb-shape0

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
chmod +x jalankan.sh

# Autostart: notch ikut jalan tiap kali login
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/notch.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Notch
Exec=$PWD/jalankan.sh
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
EOF

echo
echo "Beres. Notch otomatis jalan tiap login. Jalankan sekarang dengan:  ./jalankan.sh"
echo "(Matikan autostart: rm ~/.config/autostart/notch.desktop)"
