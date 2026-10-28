# mynotch

Notch ala **Dynamic Island** untuk desktop **Windows** dan **Ubuntu (Xorg)**: pil hitam kecil di tengah atas layar dengan sepasang mata robot yang bereaksi terhadap apa yang sedang kamu lakukan.

## Fitur

**Mata yang hidup**
- Di luar terminal, matanya mengikuti kursor mouse. Kalau mouse diam, dia melirik-lirik sendiri.
- Mouse digerakkan cepat di dekat notch: kaget.
- Tidak ada input selama 60 detik: tidur (z z z).

**Efek mengetik**
- Saat mengetik, matanya fokus ke bawah dan bar equalizer ikut bergerak. **Enter**: riak. **Backspace**: geleng-geleng.
- Aktif di terminal, Microsoft Word, Microsoft Excel, Notepad, browser, dan VS Code. Di Ubuntu, Word/Excel/Notepad diganti LibreOffice Writer, LibreOffice Calc, dan Text Editor.
- Bisa dinyalakan/dimatikan per aplikasi lewat menu **Pengaturan → Efek mengetik**. Bawaan Windows: semua nyala. Bawaan Ubuntu: hanya Terminal dan VS Code.
- Di luar terminal, shortcut (Ctrl+C, Ctrl+V, dll.) dan tombol navigasi (panah, Page Down, F1–F12) tidak dihitung mengetik. Aplikasi di luar daftar tidak memicu efek ini.

**Mode terminal** (Windows Terminal, PowerShell, CMD, gnome-terminal, Kitty, Alacritty, WezTerm, Tilix, Konsole, dll.)
- Notch melebar. Warnanya oranye untuk Claude Code, biru untuk Codex, hijau untuk terminal biasa.
- **Enter**: "terkirim ✓". **Ctrl+C**: kaget.
- Saat Claude Code atau Codex sedang bekerja: "Claude lagi mikir •••".

**Musik & video** (YouTube di browser, YouTube Music, Spotify, dll.)
- Saat media diputar, muncul indikator kecil dan matanya manggut-manggut.
- Ganti lagu: notifikasi judul dan artis beberapa detik.
- Hover ke notch: panel musik berisi cover, judul, artis, dan progress bar; tombol ⏮ ⏯ ⏭ menetes keluar dari bawah notch.

**Jadwal sholat**
- Klik 2x notch untuk melihat waktu sholat berikutnya dan berapa lama lagi.
- Pengingat otomatis: mulai 5 menit sebelum waktu sholat, notch bergetar dan muncul "Waktu Dzuhur 5 menit lagi", lalu 4, 3, 2, 1 menit lagi. Saat waktunya tiba: "Waktunya sholat Dzuhur" + konfeti, dan notch berdenyut selama 30 detik. Pengingat tetap muncul walau notch sedang tidur.
- Data resmi Kemenag per kabupaten/kota dari [api.myquran.com](https://api.myquran.com). Lokasi diatur manual (tanpa GPS) dan jadwal disimpan per bulan.

**Lain-lain**
- Tema lewat menu **Pengaturan → Tema**: Hitam (bawaan), Putih, Biru, Kaca gelap, dan Kaca terang (kaca ala Liquid Glass iOS: tengahnya bening, tepinya membiaskan latar seperti kaca tebal dan berkilau, tint-nya menyesuaikan terang-gelap latar). Saat menu menempel ke tepi layar, tema kaca berubah jadi gelap. Di Ubuntu, tema kaca tembus pandang tanpa efek tepi.
- Hover ke notch (saat tidak ada musik): jam dan tanggal.
- Klik: senang + konfeti. Klik 5x cepat: pusing.
- Disembunyikan otomatis saat ada aplikasi fullscreen (game, video). Bisa dimatikan.
- Area di sekitar notch tembus klik, dan notch tidak mengambil fokus dari aplikasi yang sedang aktif.

> **Privasi:** notch hanya mendeteksi *ada* tombol yang ditekan (dan jenisnya: Enter, Backspace, Ctrl+C) saat terminal atau aplikasi yang dinyalakan di menu **Pengaturan → Efek mengetik** aktif. Isi ketikan tidak pernah dibaca atau disimpan.

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

> Kalau di folder kamu belum ada `install.bat` (hasil clone versi lama), jalankan `git pull` sekali dulu, lalu dobel klik `install.bat`.

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
| Klik ⏮ ⏯ ⏭ (di bawah panel musik) | Kontrol media |
| Klik kanan | Menu |

**Menu klik kanan**: notch memanjang ke bawah jadi panel. Di Windows, panelnya naik menempel ke tepi atas layar dengan lengkung kecil di sudut atas, ala notch MacBook. Tutup dengan klik di luar, klik kanan lagi, atau gerakkan kursor menjauh.
- **Sembunyi saat ada app fullscreen**
- **Jalan otomatis saat komputer nyala**: Windows lewat folder Startup, Ubuntu lewat `~/.config/autostart`
- **Pengaturan**: menu bergeser ke kiri ke tiga pengaturan berikut. Tiap pengaturan bergeser ke kiri lagi; **Kembali** / **Batal** bergeser ke kanan satu halaman.
  - **Tema**: Hitam, Putih, Biru, Kaca gelap, atau Kaca terang. Selama halaman ini terbuka, notch lepas dari tepi layar supaya temanya langsung kelihatan.
  - **Efek mengetik**: daftar saklar per aplikasi (lihat [Efek mengetik](#fitur)). Ringkasannya tampil di sebelah kanan: "Semua", "4 aplikasi", atau "Mati".
  - **Lokasi sholat**: ketik nama kota/kabupaten (misalnya `pekalongan`), pilih Kab./Kota yang benar (klik atau ↑ ↓), lalu **Simpan** atau Enter. Esc / **Batal** untuk kembali.
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
- **Pengingat sholat tidak muncul.** Pastikan lokasi sholat sudah diatur. Pengingat juga tidak tampil saat ada aplikasi fullscreen (kalau opsi sembunyi nyala) atau saat menu klik kanan terbuka.
- **Windows: setelah update tampilannya masih versi lama.** Notch lama masih jalan. Dobel klik `jalankan.bat` (atau `install.bat`) supaya notch lama ditutup dan yang baru dijalankan.
- **Efek mengetik tidak muncul di suatu aplikasi.** Cek saklarnya di menu **Pengaturan → Efek mengetik**. Aplikasi yang tidak ada di daftar memang tidak memicu efek ini.

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
