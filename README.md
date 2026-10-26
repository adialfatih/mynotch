# mynotch

Notch ala **Dynamic Island** untuk desktop **Windows** dan **Ubuntu (Xorg)**: pil hitam kecil di tengah atas layar dengan sepasang mata robot yang bereaksi terhadap apa yang sedang kamu lakukan.

## Fitur

**Mata yang hidup**
- Di luar terminal, matanya mengikuti kursor mouse. Kalau mouse diam, dia melirik-lirik sendiri.
- Mouse digerakkan cepat di dekat notch: kaget.
- Tidak ada input selama 60 detik: tidur (z z z).
- **Efek mengetik** juga bisa aktif di luar terminal: Word, Excel, Notepad, browser, dan VS Code (di Ubuntu: LibreOffice Writer, LibreOffice Calc, Text Editor, browser, VS Code). Matanya fokus ke bawah dan bar equalizer ikut bergerak. Nyalakan/matikan per aplikasi lewat menu **Efek mengetik**. Shortcut (Ctrl+C, Ctrl+V, dll.) dan tombol navigasi (panah, Page Down) tidak dihitung mengetik.

**Mode terminal** (Windows Terminal, PowerShell, CMD, gnome-terminal, Kitty, Alacritty, WezTerm, Tilix, Konsole, dll.)
- Notch melebar. Warnanya oranye untuk Claude Code, biru untuk Codex, hijau untuk terminal biasa.
- Saat mengetik, matanya fokus ke bawah dan ada bar equalizer yang ikut bergerak.
- **Enter**: riak + "terkirim ✓". **Backspace**: geleng-geleng. **Ctrl+C**: kaget.
- Saat Claude Code atau Codex sedang bekerja: "Claude lagi mikir •••".

**Musik & video** (YouTube di browser, YouTube Music, Spotify, dll.)
- Saat media diputar, muncul indikator kecil dan matanya manggut-manggut.
- Ganti lagu: notifikasi judul dan artis beberapa detik.
- Hover ke notch: panel musik berisi cover, judul, artis, progress bar, dan tombol ⏮ ⏯ ⏭.

**Jadwal sholat**
- Klik 2x notch untuk melihat waktu sholat berikutnya dan berapa lama lagi.
- Pengingat otomatis: mulai 5 menit sebelum waktu sholat, notch bergetar dan muncul "Waktu Dzuhur 5 menit lagi", lalu 4, 3, 2, 1 menit lagi. Saat waktunya tiba: "Waktunya sholat Dzuhur" + konfeti, dan notch berdenyut selama 30 detik.
- Data resmi Kemenag per kabupaten/kota dari [api.myquran.com](https://api.myquran.com). Lokasi diatur manual (tanpa GPS) dan jadwal disimpan per bulan.

**Lain-lain**
- Hover ke notch (saat tidak ada musik): jam dan tanggal.
- Klik: senang + konfeti. Klik 5x cepat: pusing.
- Disembunyikan otomatis saat ada aplikasi fullscreen (game, video). Bisa dimatikan.
- Area di sekitar notch tembus klik, dan notch tidak mengambil fokus dari aplikasi yang sedang aktif.

> **Privasi:** notch hanya mendeteksi *ada* tombol yang ditekan (dan jenisnya: Enter, Backspace, Ctrl+C) saat terminal atau aplikasi yang dinyalakan di menu **Efek mengetik** aktif. Isi ketikan tidak pernah dibaca atau disimpan.

## Instalasi

### Windows

Butuh **Python 3.10+**.

```powershell
git clone https://github.com/adialfatih/mynotch.git
```

Lalu dobel klik **`install.bat`** di folder `mynotch`. Paket Python dipasang dan notch langsung jalan.

Untuk menjalankan atau me-restart notch tanpa update, dobel klik **`jalankan.bat`** (jalan tanpa jendela console). Kalau notch masih jalan, yang lama otomatis ditutup dulu.

### Ubuntu

Butuh sesi **Xorg** (sesi Wayland tidak didukung). Cek dengan:

```bash
echo $XDG_SESSION_TYPE   # harus: x11
```

Kalau hasilnya `wayland`: logout, klik nama user, klik ikon ⚙️ di pojok kanan bawah, pilih **Ubuntu on Xorg**, lalu login.

```bash
git clone https://github.com/adialfatih/mynotch.git
cd mynotch
bash install_ubuntu.sh   # sekali saja: pasang paket sistem + virtualenv
./jalankan.sh
```

Dibuat untuk Ubuntu 22.04 (GNOME 42), tapi seharusnya jalan di desktop Linux mana pun yang memakai sesi Xorg. Di GNOME, notch berada tepat di bawah top bar.

### Update

**Windows:** dobel klik **`install.bat`**. Kode terbaru diambil (`git pull`), paket dipasang, lalu notch di-restart otomatis.

**Ubuntu:**

```bash
git pull
bash install_ubuntu.sh
```

Lalu tutup notch (klik kanan → **Keluar**) dan jalankan lagi.

## Cara pakai

| Aksi | Hasil |
|---|---|
| Hover | Jam, atau panel musik kalau ada media yang diputar |
| Klik | Senang + konfeti |
| Klik 2x | Waktu sholat berikutnya |
| Klik 5x cepat | Pusing |
| Klik ⏮ ⏯ ⏭ (di panel musik) | Kontrol media |
| Klik kanan | Menu |

**Menu klik kanan** (notch memanjang ke bawah jadi panel pengaturan; tutup dengan klik di luar, klik kanan lagi, atau gerakkan kursor menjauh):
- **Sembunyi kalau ada app fullscreen**
- **Jalan otomatis saat komputer nyala**: Windows lewat folder Startup, Ubuntu lewat `~/.config/autostart`
- **Efek mengetik**: menu bergeser ke daftar saklar per aplikasi (Terminal, Microsoft Word, Microsoft Excel, Notepad, Browser, VS Code). Bawaan Windows: semua nyala. Bawaan Ubuntu: hanya Terminal dan VS Code. Aplikasi di luar daftar tidak memicu efek mengetik.
- **Lokasi sholat**: menu bergeser ke halaman lokasi di dalam notch. Ketik nama kota/kabupaten (misalnya `pekalongan`), pilih Kab./Kota yang benar (klik atau ↑ ↓), lalu **Simpan** atau Enter. Esc / **Batal** untuk kembali.
- **Keluar**

Pengaturan disimpan di `notch_settings.json` (tidak ikut di-commit).

## Catatan

- **YouTube biasa:** "artis" yang tampil adalah nama channel. Tombol next/prev mengikuti perilaku YouTube: next butuh playlist atau autoplay, dan prev biasanya kembali ke awal video.
- **"Lagi mikir"** ditebak dari judul jendela terminal yang berubah cepat (spinner). Kalau tool-nya tidak mengubah judul terminal, mode ini tidak muncul.
- **Terminal bawaan VS Code** tidak terdeteksi sebagai terminal (warna, "terkirim ✓", dan "lagi mikir" tidak muncul), tapi efek mengetiknya ikut saklar **VS Code**.
- **Fitur musik opsional.** Kalau paket `winrt-*` (Windows) atau `jeepney` (Ubuntu) belum terpasang, notch tetap jalan tanpa fitur musik.

## Troubleshooting

- **Ubuntu: notch tidak muncul.** Lihat `notch.log` di folder repo. Error `Could not load the Qt platform plugin "xcb"` berarti paket sistem belum lengkap, jalankan ulang `bash install_ubuntu.sh`.
- **Notch tidak bereaksi saat di terminal (Ubuntu).** Pastikan sesinya Xorg, bukan Wayland.
- **Jadwal sholat "Gagal ambil jadwal".** Cek koneksi internet, lalu klik 2x lagi.

## Struktur

```
notch.py           tampilan, animasi, dan logika (semua OS)
os_windows.py      jendela aktif, keyboard, idle, dll. di Windows (Win32 API)
os_x11.py          jendela aktif, keyboard, idle, dll. di Linux (X11 / python-xlib)
media_windows.py   media yang diputar di Windows (Global System Media Transport Controls)
media_linux.py     media yang diputar di Linux (MPRIS lewat D-Bus)
install.bat        instalasi / update Windows (git pull, pasang paket, restart)
jalankan.bat       launcher Windows (sekalian restart kalau sudah jalan)
install_ubuntu.sh  instalasi Ubuntu
jalankan.sh        launcher Ubuntu
```
