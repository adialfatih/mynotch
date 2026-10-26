"""
Notch — Dynamic Island iseng buat Windows & Ubuntu (Xorg).

Perilaku:
  * Selalu nongol di tengah atas layar (always-on-top, gak muncul di taskbar).
  * Lagi di terminal -> notch melebar, matanya ngeliatin kamu ngetik.
      - Enter     : riak + "terkirim"
      - Backspace : geleng-geleng
      - Ctrl+C    : kaget
      - Judul terminal berubah-ubah cepat (spinner Claude Code / Codex) -> "lagi mikir"
    Privasi: cuma mendeteksi *ada* tombol ditekan; isi ketikan tidak dibaca/disimpan.
  * Di luar terminal -> matanya ngikutin mouse; kalau mouse diem, lirik-lirik sendiri.
  * Gak ada input 60 detik -> tidur.
  * Hover -> jam. Klik -> seneng. Klik 5x cepet -> pusing. Klik kanan -> menu.
  * Klik 2x -> waktu sholat berikutnya (lokasi diatur manual lewat klik kanan,
    data Kemenag dari api.myquran.com, disimpan per bulan di notch_settings.json).
  * Ada musik/video main (YouTube, Spotify, ...) -> indikator kecil + mata manggut-manggut;
    ganti lagu -> notifikasi judul & artis; hover -> panel musik dengan ⏮ ⏯ ⏭.

Bagian yang khusus OS ada di os_windows.py / os_x11.py dan media_windows.py / media_linux.py.

Jalankan:  Windows -> jalankan.bat   |   Ubuntu -> ./install_ubuntu.sh lalu ./jalankan.sh
"""

import json
import math
import os
import random
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import date, datetime, timedelta

if sys.platform == "win32":
    from os_windows import Platform
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")  # X11 API cuma bisa dipakai di jendela X11
    from os_x11 import Platform

try:  # fitur musik opsional: kalau paketnya belum dipasang, notch tetap jalan tanpa musik
    if sys.platform == "win32":
        from media_windows import Media
    else:
        from media_linux import Media
except ImportError as exc:
    print(f"Fitur musik nonaktif: {exc}", file=sys.stderr)
    Media = None

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QKeySequence, QPainter,
                           QPainterPath, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QApplication, QWidget

# ------------------------------------------------------------------ pengaturan
SLEEP_AFTER = 60.0      # detik tanpa input sebelum tidur
TYPING_HOLD = 1.4       # berapa lama dianggap "masih ngetik" setelah tombol terakhir
WIN_W, WIN_H = 560, 250 # kanvas transparan (lebih besar dari pil, buat riak, partikel & menu)
TOP_GAP = 8
MENU_EAR = 9            # lengkung cekung di sudut atas saat menu menempel ke tepi layar
MEDIA_TOAST = 3.5       # detik notifikasi lagu baru tampil

# menu klik kanan: notch memanjang ke bawah jadi panel
MENU_KEYS = ("fullscreen", "autostart", "lokasi", "quit")
MENU_W = 330
MENU_HEAD = 46          # baris atas (mata + judul)
MENU_ROW = 34
MENU_SEP = 9            # jarak garis pemisah sebelum "Keluar"
MENU_H = MENU_HEAD + len(MENU_KEYS) * MENU_ROW + MENU_SEP + 8
MENU_LINGER = 0.8       # detik menu bertahan setelah kursor keluar
LOC_SEARCH_DELAY = 0.45 # detik jeda setelah berhenti ngetik sebelum cari kota
ROW_MAX_H = 58          # tinggi baris atas di mode lain (panel musik)

HIT_REGION = (WIN_W // 2 - 215, 0, 430, TOP_GAP + 70)  # area klik saat hover (X11)
MENU_HIT_REGION = (WIN_W // 2 - MENU_W // 2 - 10, 0, MENU_W + 20, TOP_GAP + MENU_H + 24)

CLAUDE_GLYPHS = "✳✻✽✶✢"

COL_MOUSE = (236, 238, 245)
COL_TERM = (95, 225, 150)
COL_CLAUDE = (217, 119, 87)
COL_CODEX = (110, 190, 255)
COL_SLEEP = (120, 120, 135)
COL_SHOLAT = (110, 215, 190)
COL_MEDIA = (250, 130, 180)
COL_MENU = (140, 165, 255)
COL_DANGER = (255, 120, 110)
CONFETTI = [(255, 120, 160), (255, 210, 90), (120, 220, 255), (160, 255, 150)]

HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

SCRIPT = os.path.abspath(__file__)
SETTINGS_FILE = os.path.join(os.path.dirname(SCRIPT), "notch_settings.json")

SHOLAT_API = "https://api.myquran.com/v3/sholat"
SHOLAT = [("subuh", "Subuh"), ("dzuhur", "Dzuhur"), ("ashar", "Ashar"),
          ("maghrib", "Maghrib"), ("isya", "Isya")]
PRAYER_SHOW = 7.0  # detik panel sholat tampil setelah klik 2x
REMIND_BEFORE = 5  # menit sebelum waktu sholat mulai diingatkan tiap menit
REMIND_SHOW = 8.0  # detik pengingat "x menit lagi" tampil
ADZAN_SHOW = 30.0  # detik tulisan "Waktunya sholat" tampil


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ jadwal sholat
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "notch-iseng"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def cari_kota(keyword):
    """[{'id': ..., 'lokasi': 'KOTA PEKALONGAN'}, ...]"""
    data = http_json(f"{SHOLAT_API}/kabkota/cari/{urllib.parse.quote(keyword)}")
    return (data.get("data") or []) if data.get("status") else []


def jadwal_bulan(kota_id, year, month):
    """{'2026-10-26': {'subuh': '03:59', ...}, ...}"""
    data = http_json(f"{SHOLAT_API}/jadwal/{kota_id}/{year:04d}-{month:02d}")
    return data["data"]["jadwal"]


def next_prayer(jadwal, now):
    """(nama, 'HH:MM', datetime) sholat berikutnya; None kalau jadwalnya belum ada."""
    for offset in (0, 1):
        d = now.date() + timedelta(days=offset)
        hari = jadwal.get(d.isoformat())
        if not hari:
            return None
        for key, nama in SHOLAT:
            h, m = map(int, hari[key].split(":"))
            at = datetime(d.year, d.month, d.day, h, m)
            if at > now:
                return nama, hari[key], at
    return None


def prayer_reminder(jadwal, now):
    """(nama, 'HH:MM', menit) kalau sholat tinggal <= REMIND_BEFORE menit; menit 0 = sudah masuk."""
    hari = jadwal.get(now.date().isoformat())
    if not hari:
        return None
    for key, nama in SHOLAT:
        h, m = map(int, hari[key].split(":"))
        secs = (datetime(now.year, now.month, now.day, h, m) - now).total_seconds()
        if -60 < secs <= REMIND_BEFORE * 60:
            return nama, hari[key], max(0, math.ceil(secs / 60))
    return None


def countdown(delta):
    mins = max(1, math.ceil(delta.total_seconds() / 60))
    if mins < 60:
        return f"{mins} menit lagi"
    return f"{mins // 60} jam {mins % 60} menit lagi" if mins % 60 else f"{mins // 60} jam lagi"


# ------------------------------------------------------------------ animasi
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    return t * t * (3 - 2 * t)


class Spring:
    """Pegas teredam: x mengejar target dengan sedikit mantul ala iOS."""

    def __init__(self, x, stiffness, damping):
        self.x = self.target = float(x)
        self.v = 0.0
        self.k = stiffness
        self.c = 2 * math.sqrt(stiffness) * damping

    def step(self, dt):
        for _ in range(2):
            h = dt / 2
            self.v += (self.k * (self.target - self.x) - self.c * self.v) * h
            self.x += self.v * h


# ------------------------------------------------------------------ notch
class Notch(QWidget):
    def __init__(self, plat):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.plat = plat
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.resize(WIN_W, WIN_H)
        self.place()

        self.pw = Spring(160, 220, 0.62)
        self.ph = Spring(34, 220, 0.62)
        self.py = Spring(0, 260, 0.35)
        self.expand = Spring(0, 160, 0.9)
        self.look_x = Spring(0, 140, 0.75)
        self.look_y = Spring(0.3, 140, 0.75)
        self.open = Spring(1, 260, 0.45)
        self.happy = Spring(0, 200, 0.9)
        self.lid = Spring(0, 200, 0.9)
        self.sleepf = Spring(0, 90, 1.0)
        self.musicf = Spring(0, 160, 0.9)
        self.alpha = Spring(0, 120, 1.0)
        self.menuf = Spring(0, 170, 0.85)
        self.hl_y = Spring(0, 420, 0.8)
        self.hl_a = Spring(0, 300, 1.0)
        self.sw_fs = Spring(0, 320, 0.6)
        self.sw_auto = Spring(0, 320, 0.6)
        self.page = Spring(0, 200, 0.85)  # 0 = daftar menu, 1 = halaman lokasi sholat
        self.springs = [self.pw, self.ph, self.py, self.expand, self.look_x, self.look_y,
                        self.open, self.happy, self.lid, self.sleepf, self.musicf, self.alpha,
                        self.menuf, self.hl_y, self.hl_a, self.sw_fs, self.sw_auto, self.page]
        self.color = list(COL_MOUSE)

        now = time.perf_counter()
        self.t0 = self.last = now
        self.settings = load_settings()
        self.hide_on_fullscreen = self.settings.get("hide_on_fullscreen", True)
        self.jadwal = self.settings.get("jadwal", {})
        self.fetching = False
        self.prayer_until = 0.0
        self.reminder = None       # (baris1, baris2) pengingat sholat yang lagi tampil
        self.reminded = None       # pengingat terakhir, biar tiap menit cuma sekali
        self.adzan_until = 0.0     # selama ini notch berdenyut "Waktunya sholat"
        self.adzan_pulse = 0.0
        self.next_jadwal_check = 0.0
        self.fullscreen = False
        self.next_slow_check = 0.0
        self.mode = "mouse"

        self.fg_win = 0
        self.fg_app = ""
        self.fg_title = ""
        self.fg_rect = None
        self.in_terminal = False
        self.agent_name = None
        self.title_changes = deque()

        self.kb_prev = None
        self.last_key = -99.0
        self.line_len = 0
        self.bars = [0.0] * 6

        self.prev_cursor = QCursor.pos()
        self.last_mouse_move = now
        self.next_saccade = 0.0
        self.saccade = (0.0, 0.3)
        self.sleeping = False

        self.blink = 1.0
        self.blink_start = -99.0
        self.next_blink = now + 2.0
        self.happy_until = 0.0
        self.startle_until = 0.0
        self.startle_cooldown = 0.0
        self.shake_until = 0.0
        self.dizzy_until = 0.0
        self.flash_text = ""
        self.flash_until = 0.0
        self.clicks = []
        self.ripples = []
        self.particles = []

        self.media = None
        if Media:
            try:
                self.media = Media()
            except Exception as exc:
                print(f"Fitur musik nonaktif: {exc}", file=sys.stderr)
        self.track = None
        self.track_key = None
        self.toast_until = 0.0
        self.bobbing = False
        self.art_pixmap = None
        self.art_key = None
        self.btn_pressed = None
        self.btn_pressed_at = -99.0

        self.menu_open = False
        self.menu_left = None
        self.menu_hover = None
        self.hl_key = None
        self.menu_pressed_at = -99.0
        self.autostart_on = False
        self.autostart_lock = threading.Lock()
        self.loc_editing = False
        self.loc_text = ""
        self.loc_results = None
        self.loc_sel = None
        self.loc_status = ""
        self.loc_search_at = 0.0
        self.loc_token = 0
        self.loc_key_at = -99.0

        self.font_label = QFont(plat.FONT, 9, QFont.DemiBold)
        self.font_clock = QFont(plat.FONT, 13, QFont.Bold)
        self.font_small = QFont(plat.FONT, 8)
        self.font_item = QFont(plat.FONT, 9)
        self.font_z = QFont(plat.FONT, 8, QFont.Bold)
        self.ensure_jadwal()

        self.alpha.target = 1.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def place(self):
        scr = QApplication.primaryScreen()
        geo = scr.geometry()
        self.move(geo.x() + (geo.width() - WIN_W) // 2, self.plat.notch_top(scr))

    # -------------------------------------------------------------- input
    def update_foreground(self, now):
        win = self.plat.active_window()
        if win != self.fg_win:
            app = self.plat.window_app(win)
            if app is None:  # menu / notch sendiri: pertahankan konteks sebelumnya
                return
            self.fg_win = win
            self.fg_app = app
            self.fg_title = self.plat.window_title(win) if win else ""
            self.in_terminal = app in self.plat.TERMINALS
            self.title_changes.clear()
            self.kb_prev = None
            self.line_len = 0
        elif self.in_terminal:
            title = self.plat.window_title(win)
            if title != self.fg_title:
                self.fg_title = title
                self.title_changes.append(now)

        self.agent_name = None
        if self.in_terminal:
            low = self.fg_title.lower()
            if "claude" in low or self.fg_title[:1] in CLAUDE_GLYPHS:
                self.agent_name = "Claude Code"
            elif "codex" in low:
                self.agent_name = "Codex"

    def poll_keys(self, now):
        down = self.plat.keys_down()
        if self.kb_prev is None:  # baru masuk terminal: jangan hitung tombol yang lagi ditahan
            self.kb_prev = down
            return
        pressed = down - self.kb_prev
        self.kb_prev = down
        ctrl = bool(down & self.plat.CTRL_KEYS)
        for key in pressed:
            if key not in self.plat.MODIFIER_KEYS:
                self.on_key(key, ctrl, now)

    def on_key(self, key, ctrl, now):
        if not self.in_terminal and (ctrl or key not in self.plat.TEXT_KEYS):
            return  # di luar terminal: shortcut (Ctrl+C = copy) & tombol navigasi bukan ngetik
        self.last_key = now
        self.ph.v += 45
        if ctrl and key == self.plat.KEY_C:
            self.startle(now, 0.6)
            self.shake_until = now + 0.35
            self.flash("eh?! dibatalin", now, 1.2)
            self.line_len = 0
        elif key == self.plat.KEY_ENTER:
            self.line_len = 0
            self.ripples.append(0.0)
            self.happy_until = now + 0.5
            self.flash("terkirim ✓" if self.agent_name else "enter ↵", now, 1.0)
        elif key == self.plat.KEY_BACKSPACE:
            self.line_len = max(0, self.line_len - 1)
            self.shake_until = now + 0.22
            self.bump_bars(0.5)
        else:
            self.line_len += 1
            self.bump_bars(1.0)

    def bump_bars(self, level):
        self.bars = [max(b, random.uniform(0.35, 1.0) * level) for b in self.bars]

    def startle(self, now, dur):
        self.startle_until = now + dur
        self.startle_cooldown = now + 2.0

    def flash(self, text, now, dur):
        self.flash_text = text
        self.flash_until = now + dur

    def register_click(self, now):
        """Catat klik; True kalau barusan jadi pusing (5 klik dalam 2.5 detik)."""
        self.clicks = [c for c in self.clicks if now - c < 2.5] + [now]
        if len(self.clicks) < 5:
            return False
        self.clicks.clear()
        self.prayer_until = 0.0
        self.dizzy_until = now + 2.6
        self.flash("pusing…", now, 2.6)
        return True

    def mousePressEvent(self, e):
        now = time.perf_counter()
        if self.menu_open:
            self.menu_click(e, now)
            return
        if e.button() == Qt.RightButton:
            self.open_menu()
            return
        if e.button() != Qt.LeftButton:
            return
        action = self.media_button_at(e.position())
        if action:
            self.press_media(action, now)
            return
        if not self.register_click(now):
            self.happy_until = now + 1.1
        self.py.v += 160
        self.burst()

    def mouseDoubleClickEvent(self, e):
        now = time.perf_counter()
        if self.menu_open:  # klik cepat beruntun di menu = klik biasa
            self.menu_click(e, now)
            return
        if e.button() != Qt.LeftButton:
            return
        action = self.media_button_at(e.position())
        if action:  # klik cepat beruntun di tombol = tekan tombol lagi
            self.press_media(action, now)
            return
        if self.register_click(now):
            return
        self.py.v += 120
        self.show_prayer(now)

    # -------------------------------------------------------------- musik
    def media_buttons(self, rect):
        """[(aksi, titik tengah)] tombol ⏮ ⏯ ⏭ di sisi kanan panel musik."""
        mid = self.head_mid(rect)
        return [(action, QPointF(rect.right() - 31 - (2 - i) * 30, mid))
                for i, action in enumerate(("prev", "playpause", "next"))]

    def media_button_at(self, pos):
        if self.mode != "media" or not self.track or not self.media:
            return None
        for action, c in self.media_buttons(self.pill_rect()):
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= 15:
                return action
        return None

    def press_media(self, action, now):
        self.media.send(action)
        self.btn_pressed, self.btn_pressed_at = action, now
        if action != "playpause":  # lirik ke arah tombol yang ditekan
            self.look_x.v += 9 if action == "next" else -9

    def update_track(self, now):
        info = self.media.info if self.media else None
        self.track = info
        if not info:
            return
        key = (info["title"], info["artist"])
        if key != self.track_key:
            self.track_key = key
            if info["playing"]:
                self.toast_until = now + MEDIA_TOAST
        if info["art_key"] != self.art_key:
            self.art_key = info["art_key"]
            self.art_pixmap = None
            pix = QPixmap()
            if info["art"] and pix.loadFromData(info["art"]):
                side = min(pix.width(), pix.height())  # potong tengah jadi persegi (thumbnail YouTube 16:9)
                pix = pix.copy((pix.width() - side) // 2, (pix.height() - side) // 2, side, side)
                self.art_pixmap = pix.scaled(96, 96, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def track_progress(self):
        info = self.track
        if not info or info["duration"] <= 0:
            return None
        pos = info["position"]
        elapsed = time.time() - info["stamp"]
        if info["playing"] and 0 <= elapsed < 6 * 3600:
            pos += elapsed
        return clamp(pos / info["duration"])

    def burst(self):
        rect = self.pill_rect()
        for _ in range(16):
            ang = random.uniform(0.15 * math.pi, 0.85 * math.pi)
            speed = random.uniform(80, 220)
            x = rect.center().x() + random.uniform(-rect.width() / 3, rect.width() / 3)
            self.particles.append([x, rect.bottom() - 4, math.cos(ang) * speed,
                                   math.sin(ang) * speed, 1.0, random.choice(CONFETTI)])

    # -------------------------------------------------------------- menu
    def open_menu(self):
        self.menu_open = True
        self.menu_left = None
        self.prayer_until = 0.0
        self.autostart_on = self.plat.autostart_enabled()
        self.sw_fs.x = self.sw_fs.target = float(self.hide_on_fullscreen)
        self.sw_auto.x = self.sw_auto.target = float(self.autostart_on)
        self.hl_a.x = self.hl_a.target = 0.0
        self.page.x = self.page.target = 0.0
        self.py.v += 120

    def close_menu(self):
        self.end_editing()
        self.menu_open = False
        self.menu_hover = None

    def menu_rows(self, rect):
        """[(kunci, kotak baris)] item menu di bawah baris mata."""
        rows = []
        y = rect.top() + MENU_HEAD
        for key in MENU_KEYS:
            if key == "quit":
                y += MENU_SEP
            rows.append((key, QRectF(rect.left() + 8, y, rect.width() - 16, MENU_ROW)))
            y += MENU_ROW
        return rows

    def loc_layout(self, rect):
        """[(kunci, kotak)] halaman lokasi: Batal, kolom ketik, Simpan, lalu baris hasil."""
        top = rect.top() + MENU_HEAD
        field = QRectF(rect.left() + 16, top + 2, rect.width() - 32 - 72, 30)
        items = [("batal", QRectF(rect.right() - 70, rect.top() + 6, 60, MENU_HEAD - 14)),
                 ("field", field),
                 ("simpan", QRectF(field.right() + 8, field.top(), 64, 30))]
        for i in range(len(self.loc_shown())):
            items.append((f"hasil{i}", QRectF(rect.left() + 8, top + 40 + i * MENU_ROW,
                                              rect.width() - 16, MENU_ROW)))
        return items

    def menu_item_at(self, pos):
        if not self.menu_open or self.menuf.x < 0.5 or abs(self.page.x - self.page.target) > 0.5:
            return None  # belum kebuka / lagi geser halaman
        rect = self.pill_rect()
        items = self.loc_layout(rect) if self.page.target else self.menu_rows(rect)
        return next((key for key, r in items if r.contains(pos)), None)

    def menu_click(self, e, now):
        if e.button() == Qt.RightButton:
            self.close_menu()
            return
        if e.button() != Qt.LeftButton:
            return
        key = self.menu_item_at(e.position())
        if key is None:
            if not self.page.target and e.position().y() < self.pill_rect().top() + MENU_HEAD:
                self.close_menu()  # klik baris mata = tutup
            return
        self.menu_pressed_at = now
        if key == "fullscreen":
            self.hide_on_fullscreen = not self.hide_on_fullscreen
            self.sw_fs.target = float(self.hide_on_fullscreen)
            self.settings["hide_on_fullscreen"] = self.hide_on_fullscreen
            save_settings(self.settings)
        elif key == "autostart":
            self.autostart_on = not self.autostart_on
            self.sw_auto.target = float(self.autostart_on)
            # di Windows butuh PowerShell (lambat): jangan bekukan animasi
            threading.Thread(target=self._apply_autostart, daemon=True).start()
        elif key == "lokasi":
            self.open_lokasi(now)
        elif key == "quit":
            self.close_menu()
            QTimer.singleShot(260, QApplication.quit)  # biar animasi menutup kelihatan dulu
        elif key == "batal":
            self.close_lokasi()
        elif key == "simpan":
            self.save_lokasi(now)
        elif key == "field":
            self.plat.take_focus()  # kalau fokusnya sempat pindah
        else:  # hasilN
            self.loc_sel = int(key[5:])

    def _apply_autostart(self):
        with self.autostart_lock:  # yang terakhir dapat kunci memakai pilihan terbaru
            self.plat.set_autostart(self.autostart_on, SCRIPT)

    def update_menu(self, now, hovering, rect):
        """Tutup menu kalau ada klik di luar / kursor lama di luar; sorot baris di bawah kursor."""
        if hovering:
            self.menu_left = None
        elif self.plat.mouse_down():
            self.close_menu()
        elif self.menu_left is None:
            self.menu_left = now
        elif now - self.menu_left > MENU_LINGER and not self.loc_editing:
            self.close_menu()
        if not self.menu_open:
            self.hl_a.target = 0.0
            return

        if self.loc_search_at and now >= self.loc_search_at:
            self.loc_search_at = 0.0
            threading.Thread(target=self._search_kota, daemon=True,
                             args=(self.loc_token, self.loc_text.strip())).start()

        key = self.menu_item_at(QPointF(self.mapFromGlobal(QCursor.pos())))
        row = key if key in MENU_KEYS or (key or "").startswith("hasil") else None
        if row:
            items = self.loc_layout(rect) if self.page.target else self.menu_rows(rect)
            y = dict(items)[row].top() - rect.top()
            if self.hl_a.x < 0.05:  # sorotan baru muncul: langsung di baris itu, jangan meluncur
                self.hl_y.x, self.hl_y.v = y, 0.0
            self.hl_y.target = y
            self.hl_key = row
        self.menu_hover = key
        self.hl_a.target = 1.0 if row else 0.0

    # -------------------------------------------------------------- menu: lokasi sholat
    def open_lokasi(self, now):
        """Geser ke halaman lokasi dan ambil keyboard supaya bisa ngetik di notch."""
        self.page.target = 1.0
        self.hl_a.x = self.hl_a.target = 0.0
        self.loc_text = None  # paksa set_loc_text mengisi ulang semuanya
        self.set_loc_text("")
        self.loc_key_at = now
        self.loc_editing = True
        self.plat.take_focus()
        self.grabKeyboard()

    def close_lokasi(self):
        self.end_editing()
        self.page.target = 0.0
        self.hl_a.x = self.hl_a.target = 0.0

    def end_editing(self):
        if not self.loc_editing:
            return
        self.loc_editing = False
        self.loc_token += 1  # hasil pencarian yang masih jalan diabaikan
        self.loc_search_at = 0.0
        self.releaseKeyboard()
        self.plat.release_focus()

    def set_loc_text(self, text):
        text = text[:40]
        if text == self.loc_text:
            return
        self.loc_text = text
        self.loc_token += 1
        self.loc_results = None
        self.loc_sel = None
        if len(text.strip()) >= 3:
            self.loc_search_at = time.perf_counter() + LOC_SEARCH_DELAY
            self.loc_status = "Mencari"
        else:
            self.loc_search_at = 0.0
            lokasi = self.settings.get("sholat")
            self.loc_status = ("Ketik minimal 3 huruf" if text.strip() else
                               f"Sekarang: {lokasi['lokasi']}" if lokasi else
                               "Ketik nama kota atau kabupaten")

    def _search_kota(self, token, keyword):
        try:
            hasil = [{"id": h["id"], "lokasi": h["lokasi"].title()} for h in cari_kota(keyword)]
        except Exception:
            hasil = None
        if token != self.loc_token:
            return  # teksnya keburu diubah
        if hasil is None:
            self.loc_status = "Gagal menghubungi server, cek internet"
        elif not hasil:
            self.loc_status = f"\"{keyword}\" tidak ketemu, coba nama lain"
        self.loc_sel = 0 if hasil else None
        self.loc_results = hasil or None

    def loc_shown(self):
        """Hasil yang muat ditampilkan; kalau lebih dari 3, baris ke-3 jadi keterangan."""
        res = self.loc_results or []
        return res[:2] if len(res) > 3 else res

    def loc_choice(self):
        shown = self.loc_shown()
        return shown[self.loc_sel] if self.loc_sel is not None and self.loc_sel < len(shown) else None

    def save_lokasi(self, now):
        pick = self.loc_choice()
        if not pick:
            return
        self.settings["sholat"] = dict(pick)
        self.jadwal = {}
        self.settings["jadwal"] = {}
        save_settings(self.settings)
        self.ensure_jadwal()
        self.happy_until = now + 1.0
        self.close_lokasi()

    def keyPressEvent(self, e):
        if not self.loc_editing:
            return
        self.loc_key_at = time.perf_counter()
        key = e.key()
        if key == Qt.Key_Escape:
            self.close_lokasi()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if self.loc_choice():
                self.save_lokasi(self.loc_key_at)
            elif self.loc_search_at:
                self.loc_search_at = self.loc_key_at  # langsung cari, gak usah nunggu jeda
        elif key in (Qt.Key_Up, Qt.Key_Down):
            n = len(self.loc_shown())
            if n:
                step = 1 if key == Qt.Key_Down else -1
                self.loc_sel = 0 if self.loc_sel is None else (self.loc_sel + step) % n
        elif key == Qt.Key_Backspace:
            ctrl = e.modifiers() & Qt.ControlModifier
            self.set_loc_text("" if ctrl else self.loc_text[:-1])
        elif e.matches(QKeySequence.Paste):
            self.set_loc_text(self.loc_text + " ".join(QApplication.clipboard().text().split()))
        elif e.text() and e.text().isprintable():
            self.set_loc_text(self.loc_text + e.text())

    # -------------------------------------------------------------- sholat
    def show_prayer(self, now):
        self.reminder = None
        self.adzan_until = 0.0
        self.prayer_until = now + PRAYER_SHOW
        self.ensure_jadwal()

    def check_reminder(self, now):
        """Ingatkan tiap menit mulai 5 menit sebelum waktu sholat, lalu saat waktunya tiba."""
        if now >= self.next_jadwal_check:  # notch bisa jalan berhari-hari: jadwal bulan depan
            self.next_jadwal_check = now + 600
            self.ensure_jadwal()
        if self.mode == "prayer" and now < self.adzan_until and now >= self.adzan_pulse:
            self.adzan_pulse = now + 2.5  # riak berulang selama "Waktunya sholat" tampil
            self.ripples.append(0.0)

        rem = prayer_reminder(self.jadwal, datetime.now())
        if not rem:
            return
        nama, jam, menit = rem
        key = (date.today(), nama, menit)
        if key == self.reminded:
            return
        self.reminded = key
        lokasi = self.settings.get("sholat", {}).get("lokasi", "")
        if menit:
            self.reminder = (f"Waktu {nama} {menit} menit lagi", f"pukul {jam} · {lokasi}")
            self.prayer_until = now + REMIND_SHOW
            self.shake_until = now + 0.45  # getar
        else:
            self.reminder = (f"Waktunya sholat {nama}", f"{jam} · {lokasi}")
            self.prayer_until = self.adzan_until = now + ADZAN_SHOW
            self.adzan_pulse = now + 2.5
            self.happy_until = now + 1.5
            self.burst()
        self.startle(now, 0.4)
        self.ripples.append(0.0)
        self.py.v += 160

    def ensure_jadwal(self):
        """Ambil jadwal bulan ini (dan bulan depan kalau besok ganti bulan) di background."""
        lokasi = self.settings.get("sholat")
        if not lokasi or self.fetching:
            return
        today = date.today()
        days = [today, today + timedelta(days=1)]
        months = sorted({(d.year, d.month) for d in days if d.isoformat() not in self.jadwal})
        if not months:
            return
        self.fetching = True
        threading.Thread(target=self._fetch_jadwal, args=(lokasi["id"], months), daemon=True).start()

    def _fetch_jadwal(self, kota_id, months):
        try:
            got = {}
            for y, m in months:
                got.update(jadwal_bulan(kota_id, y, m))
            if self.settings.get("sholat", {}).get("id") != kota_id:
                return  # lokasi keburu diganti
            kemarin = (date.today() - timedelta(days=1)).isoformat()
            self.jadwal = {k: v for k, v in {**self.jadwal, **got}.items() if k >= kemarin}
            self.settings["jadwal"] = self.jadwal
            save_settings(self.settings)
        except Exception:
            pass  # panel akan bilang gagal; klik 2x lagi untuk coba ulang
        finally:
            self.fetching = False

    def prayer_lines(self):
        if self.reminder:
            return self.reminder
        lokasi = self.settings.get("sholat")
        if not lokasi:
            return "Lokasi belum diatur", "klik kanan → Atur lokasi sholat"
        nxt = next_prayer(self.jadwal, datetime.now())
        if nxt:
            nama, jam, at = nxt
            return f"{nama}  {jam}", f"{countdown(at - datetime.now())} · {lokasi['lokasi']}"
        if self.fetching:
            return "Ambil jadwal…", lokasi["lokasi"]
        return "Gagal ambil jadwal", "cek internet, lalu klik 2x lagi"

    # -------------------------------------------------------------- logika
    def pill_rect(self):
        pw, ph = self.pw.x, self.ph.x
        top = (TOP_GAP + self.py.x) * (1 - self.attach())
        return QRectF(WIN_W / 2 - pw / 2, top, pw, ph)

    def attach(self):
        """0..1: seberapa menempel notch ke tepi atas layar (cuma saat menu terbuka)."""
        return clamp(self.menuf.x) if self.plat.MENU_FLUSH else 0.0

    def notch_shape(self, rect, radius):
        """Pil membulat; saat menempel, sudut atas berganti jadi lengkung cekung ke tepi layar."""
        att = self.attach()
        path = QPainterPath()
        if att <= 0:
            path.addRoundedRect(rect, radius, radius)
            return path
        # paruh pertama sudut atas cembung mengecil, paruh kedua lengkung cekung tumbuh
        rt = radius * max(0.0, 1 - 2 * att)
        ear = MENU_EAR * max(0.0, 2 * att - 1)
        sx, d = ear - rt, ear + rt  # salah satunya selalu nol
        q = 1 - 0.5523  # titik kendali Bézier untuk seperempat lingkaran
        l, r, t, b = rect.left(), rect.right(), rect.top(), rect.bottom()
        rb = radius
        path.moveTo(l - sx, t)
        path.lineTo(r + sx, t)
        path.cubicTo(r + sx * q, t, r, t + d * q, r, t + d)
        path.lineTo(r, b - rb)
        path.cubicTo(r, b - rb * q, r - rb * q, b, r - rb, b)
        path.lineTo(l + rb, b)
        path.cubicTo(l + rb * q, b, l, b - rb * q, l, b - rb)
        path.lineTo(l, t + d)
        path.cubicTo(l, t + d * q, l - sx * q, t, l - sx, t)
        path.closeSubpath()
        return path

    def head_mid(self, rect):
        """Tengah vertikal baris atas (mata & teks); panel menu lebih tinggi dari baris ini."""
        return rect.top() + lerp(min(rect.height(), ROW_MAX_H), MENU_HEAD, clamp(self.menuf.x)) / 2

    def eye_anchor(self, rect):
        cx = lerp(rect.center().x(), rect.left() + 46, clamp(self.expand.x))
        return cx - self.sleepf.x * 14 - self.musicf.x * 16, self.head_mid(rect)

    def look_at(self, gx, gy, rect):
        ex, ey = self.eye_anchor(rect)
        dx, dy = gx - (self.x() + ex), gy - (self.y() + ey)
        return dx / (abs(dx) + 220), clamp(dy / (abs(dy) + 140), -0.8, 1.0)

    def context_color(self):
        if not self.in_terminal:
            return COL_MOUSE
        return {"Claude Code": COL_CLAUDE, "Codex": COL_CODEX}.get(self.agent_name, COL_TERM)

    def tick(self):
        now = time.perf_counter()
        dt = min(now - self.last, 1 / 30)
        self.last = now
        t = now - self.t0

        cur = QCursor.pos()
        mdist = math.hypot(cur.x() - self.prev_cursor.x(), cur.y() - self.prev_cursor.y())
        self.prev_cursor = cur
        if mdist > 0:
            self.last_mouse_move = now

        self.update_foreground(now)
        watch_keys = self.in_terminal or self.plat.TYPE_ANYWHERE
        if watch_keys and not self.menu_open:
            self.poll_keys(now)
        else:
            self.kb_prev = None
        self.update_track(now)
        playing = bool(self.track and self.track["playing"])

        was_sleeping = self.sleeping
        self.sleeping = self.plat.idle_seconds() > SLEEP_AFTER
        if was_sleeping and not self.sleeping:
            self.startle(now, 0.45)

        if now >= self.next_slow_check:
            self.next_slow_check = now + 0.5
            self.fullscreen = self.hide_on_fullscreen and self.plat.is_fullscreen(self.fg_win)
            self.fg_rect = self.plat.window_rect(self.fg_win) if self.fg_win else None
            self.place()
            self.plat.keep_on_top()
            self.check_reminder(now)

        rect = self.pill_rect()
        grect = rect.translated(self.x(), self.y())
        hovering = self.alpha.x > 0.5 and grect.adjusted(-6, -6, 6, 6).contains(QPointF(cur))
        if self.menu_open and self.fullscreen:
            self.close_menu()
        if self.menu_open:
            self.update_menu(now, hovering, rect)
        self.plat.set_click_through(not hovering,
                                    MENU_HIT_REGION if self.menu_open else HIT_REGION)

        # mouse ngebut lewat dekat notch -> kaget
        if not self.in_terminal and mdist / max(dt, 1e-3) > 4000 and now > self.startle_cooldown:
            ex, ey = self.eye_anchor(rect)
            if math.hypot(cur.x() - self.x() - ex, cur.y() - self.y() - ey) < 260:
                self.startle(now, 0.5)

        typing = watch_keys and now - self.last_key < TYPING_HOLD
        while self.title_changes and now - self.title_changes[0] > 2.5:
            self.title_changes.popleft()
        thinking = self.in_terminal and not typing and len(self.title_changes) >= 3

        if self.fullscreen:
            mode = "hidden"
        elif self.menu_open:
            mode = "menu"
        elif now < self.prayer_until:  # pengingat sholat tetap muncul walau notch lagi tidur
            mode = "prayer"
        elif self.sleeping:
            mode = "sleep"
        elif hovering:
            mode = "media" if self.track else "hover"
        elif typing or thinking:
            mode = "thinking" if thinking else "typing"
        elif now < self.toast_until and self.track:
            mode = "media"
        elif self.in_terminal:
            mode = "terminal"
        else:
            mode = "mouse"
        self.mode = mode
        self.bobbing = playing and mode not in ("sleep", "typing", "hidden")

        # ---- target bentuk & ekspresi
        sizes = {"mouse": (190 if playing else 160, 34), "hidden": (160, 34), "sleep": (150, 32),
                 "hover": (270, 44), "typing": (310, 40), "terminal": (310, 40),
                 "thinking": (310, 40), "prayer": (320, 52), "media": (400, 58),
                 "menu": (MENU_W, MENU_H)}
        self.pw.target, self.ph.target = sizes[mode]
        if mode == "prayer":  # pengingat lebih panjang dari "Dzuhur  11:52", lebarkan secukupnya
            text_w = QFontMetrics(self.font_clock).horizontalAdvance(self.prayer_lines()[0])
            self.pw.target = min(WIN_W - 40, max(self.pw.target, text_w + 116))
        self.alpha.target = 0.0 if mode == "hidden" else 1.0
        self.expand.target = 1.0 if mode in ("hover", "typing", "terminal", "thinking",
                                             "prayer", "media", "menu") else 0.0
        self.menuf.target = 1.0 if mode == "menu" else 0.0
        self.sleepf.target = 1.0 if mode == "sleep" else 0.0
        self.musicf.target = 1.0 if playing and mode == "mouse" else 0.0
        loc_typing = self.loc_editing and bool(self.loc_text) and now - self.loc_key_at < TYPING_HOLD
        self.lid.target = 0.25 if mode == "typing" or loc_typing else 0.0
        self.happy.target = 1.0 if now < self.happy_until or mode in ("hover", "prayer",
                                                                      "media") else 0.0
        if mode == "sleep":
            self.open.target = 0.1
        else:
            self.open.target = 1.35 if now < self.startle_until else 1.0

        # ---- arah pandang
        if mode == "sleep":
            lx, ly = 0.0, 0.35
        elif mode == "typing":
            lx, ly = -0.55 + min(self.line_len, 48) / 48 * 1.1, 0.55
        elif mode == "thinking":
            lx, ly = 0.45 + 0.3 * math.sin(t * 0.9), -0.75
        elif mode == "menu" and loc_typing:  # ngikutin kursor ketik
            lx, ly = -0.2 + min(len(self.loc_text), 24) / 24 * 0.9, 0.6
        elif mode == "terminal" and now - self.last_mouse_move > 1.5 and self.fg_rect:
            left, top, right, bottom = self.fg_rect
            dpr = self.devicePixelRatioF()
            lx, ly = self.look_at((left + (right - left) * 0.3) / dpr,
                                  (bottom - (bottom - top) * 0.12) / dpr, rect)
        elif mode == "mouse" and now - self.last_mouse_move > 3.5:
            if now >= self.next_saccade:
                self.next_saccade = now + random.uniform(1.0, 3.0)
                self.saccade = (random.uniform(-0.85, 0.85), random.uniform(-0.4, 0.8))
            lx, ly = self.saccade
        else:
            lx, ly = self.look_at(cur.x(), cur.y(), rect)
        self.look_x.target, self.look_y.target = lx, ly

        # ---- kedip
        if now >= self.next_blink and mode != "sleep" and now > self.dizzy_until:
            self.blink_start = now
            self.next_blink = now + (0.28 if random.random() < 0.18 else random.uniform(2.2, 6.0))
        bt = (now - self.blink_start) / 0.16
        self.blink = 1 - 0.95 * math.sin(math.pi * bt) if 0 <= bt < 1 else 1.0

        # ---- integrasi
        for s in self.springs:
            s.step(dt)
        target_col = ({"sleep": COL_SLEEP, "prayer": COL_SHOLAT, "media": COL_MEDIA,
                       "menu": COL_MENU}.get(mode)
                      or self.context_color())
        k = 1 - math.exp(-dt * 6)
        self.color = [lerp(c, tc, k) for c, tc in zip(self.color, target_col)]
        decay = math.exp(-dt * 5)
        self.bars = [b * decay for b in self.bars]
        self.ripples = [r + dt / 0.7 for r in self.ripples if r + dt / 0.7 < 1]
        for pt in self.particles:
            pt[3] += 380 * dt
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[4] -= dt / 1.1
        self.particles = [pt for pt in self.particles if pt[4] > 0]

        self.update()

    # -------------------------------------------------------------- gambar
    def paintEvent(self, _):
        a = clamp(self.alpha.x)
        if a < 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(a)
        rect = self.pill_rect()
        radius = min(rect.height() / 2, 22)
        col = QColor(*[int(c) for c in self.color])

        p.setBrush(Qt.NoBrush)
        for rt in self.ripples:
            g = rt * 28
            c = QColor(col)
            c.setAlphaF(clamp((1 - rt) * 0.6))
            p.setPen(QPen(c, 2.0 * (1 - rt) + 0.6))
            p.drawRoundedRect(rect.adjusted(-g, -g, g, g), radius + g, radius + g)

        path = self.notch_shape(rect, radius)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawPath(path)
        p.save()
        if self.attach() > 0:  # tepi atas menyatu dengan layar, gak perlu garis
            p.setClipRect(QRectF(0, rect.top() + 1.5, WIN_W, WIN_H))
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.restore()

        p.save()
        p.setClipPath(path)
        self.paint_eyes(p, rect, col)
        self.paint_content(p, rect, col, a)
        self.paint_menu(p, rect, col, a)
        p.restore()

        p.setPen(Qt.NoPen)
        for x, y, _, _, life, pc in self.particles:
            c = QColor(*pc)
            c.setAlphaF(clamp(life))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), 2.4, 2.4)
        p.end()

    def paint_eyes(self, p, rect, col):
        now = time.perf_counter()
        t = now - self.t0
        s = min(rect.height(), 44) / 36  # di panel tinggi (sholat/musik) mata gak ikut membesar
        cx, cy = self.eye_anchor(rect)
        lx, ly = self.look_x.x, self.look_y.x
        shake = math.sin(t * 60) * 2.4 * s if now < self.shake_until else 0.0
        openness = max(0.07, self.open.x * self.blink)
        bg = QColor(0, 0, 0)

        for side in (-1, 1):
            persp = 1 + 0.13 * lx * side  # mata di arah lirikan sedikit lebih besar
            ew = 13 * s * persp
            eh = 17 * s * persp * openness
            ex = cx + side * 14 * s + lx * 7 * s + shake
            ey = cy + ly * 5 * s
            if self.bobbing:  # manggut-manggut ikut musik
                ey += math.sin(t * 11) * 1.4 * s

            if now < self.dizzy_until:
                p.save()
                p.translate(ex, ey)
                p.rotate(t * 400 * side)
                pen = QPen(col, 2.4 * s)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                d = 5 * s
                p.drawLine(QPointF(-d, -d), QPointF(d, d))
                p.drawLine(QPointF(-d, d), QPointF(d, -d))
                p.restore()
                continue

            r = min(ew, eh) / 2
            p.setPen(Qt.NoPen)
            for grow, al in ((5 * s, 0.10), (2.5 * s, 0.18)):
                g = QColor(col)
                g.setAlphaF(al)
                p.setBrush(g)
                p.drawRoundedRect(QRectF(ex - ew / 2 - grow, ey - eh / 2 - grow,
                                         ew + 2 * grow, eh + 2 * grow), r + grow, r + grow)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(ex - ew / 2, ey - eh / 2, ew, eh), r, r)

            top = ey - eh / 2
            lid = self.lid.x
            if lid > 0.01:  # kelopak miring = muka fokus
                x0, x1 = ex - ew / 2 - 7 * s, ex + ew / 2 + 7 * s
                outer, inner = top + eh * lid * 0.45, top + eh * lid
                yl, yr = (outer, inner) if side < 0 else (inner, outer)
                p.setBrush(bg)
                p.drawPolygon(QPolygonF([QPointF(x0, top - 8 * s), QPointF(x1, top - 8 * s),
                                         QPointF(x1, yr), QPointF(x0, yl)]))
            hp = self.happy.x
            if hp > 0.01:  # potong bagian bawah -> mata senyum ∩
                p.setBrush(bg)
                p.drawEllipse(QPointF(ex, ey + eh * 0.5 + eh * (1 - hp) * 1.3 + 1), ew, eh * 0.62)

    def paint_content(self, p, rect, col, a):
        now = time.perf_counter()
        t = now - self.t0
        mid = self.head_mid(rect)
        hh = (mid - rect.top()) * 2  # tinggi baris atas

        c = smoothstep(clamp((self.expand.x - 0.35) / 0.65))
        if c > 0.01:
            p.setOpacity(a * c)
            x0, x1 = rect.left() + 92, rect.right() - 16
            area = QRectF(x0, rect.top(), max(0.0, x1 - x0), hh)

            if self.mode == "media" and self.track:
                self.paint_media(p, rect)
            elif self.mode == "prayer":
                line1, line2 = self.prayer_lines()
                p.setFont(self.font_clock)
                p.setPen(QColor(245, 245, 250))
                p.drawText(QRectF(x0, rect.top() + 7, area.width(), 22),
                           Qt.AlignVCenter | Qt.AlignLeft, line1)
                p.setFont(self.font_small)
                p.setPen(QColor(150, 150, 160))
                p.drawText(QRectF(x0, rect.top() + 29, area.width(), 16),
                           Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetrics(self.font_small).elidedText(line2, Qt.ElideRight,
                                                                   int(area.width())))
            elif self.mode == "menu":  # judul halaman berganti pelan saat geser
                pg = clamp(self.page.x)
                batal = QColor(245, 245, 250) if self.menu_hover == "batal" else QColor(150, 150, 160)
                for title, right, rc, al in (("Pengaturan", time.strftime("%H:%M"),
                                              QColor(150, 150, 160), 1 - pg),
                                             ("Lokasi sholat", "Batal", batal, pg)):
                    if al < 0.01:
                        continue
                    p.setOpacity(a * c * al)
                    p.setFont(self.font_label)
                    p.setPen(QColor(245, 245, 250))
                    p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, title)
                    p.setFont(self.font_small)
                    p.setPen(rc)
                    p.drawText(area, Qt.AlignVCenter | Qt.AlignRight, right)
            elif self.mode == "hover":
                lt = time.localtime()
                p.setFont(self.font_clock)
                p.setPen(QColor(245, 245, 250))
                p.drawText(area, Qt.AlignVCenter | Qt.AlignLeft, time.strftime("%H:%M", lt))
                p.setFont(self.font_label)
                p.setPen(QColor(150, 150, 160))
                p.drawText(area, Qt.AlignVCenter | Qt.AlignRight,
                           f"{HARI[lt.tm_wday]}, {lt.tm_mday} {BULAN[lt.tm_mon - 1]}")
            else:
                flash = now < self.flash_until
                name = self.agent_name or self.plat.TERMINALS.get(self.fg_app, "Terminal")
                if flash:
                    label = self.flash_text
                elif self.mode == "thinking":
                    label = f"{self.agent_name.split()[0]} lagi mikir" if self.agent_name \
                        else "lagi mikir"
                elif self.mode == "typing":
                    label = ""
                else:
                    label = f"{name}  ♪" if self.track and self.track["playing"] else name

                right_w = 0
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                if self.mode == "thinking" and not flash:
                    right_w = 30
                    for i in range(3):
                        bounce = max(0.0, math.sin(t * 5 - i * 0.7))
                        p.drawEllipse(QPointF(x1 - 24 + i * 9 + 3, mid - bounce * 4), 2.6, 2.6)
                elif not flash:
                    bw, gap = 3, 3
                    right_w = len(self.bars) * (bw + gap) - gap
                    maxh = hh - 16
                    for i, b in enumerate(self.bars):
                        h = 3 + b * maxh
                        p.drawRoundedRect(QRectF(x1 - right_w + i * (bw + gap), mid - h / 2, bw, h),
                                          1.5, 1.5)

                text_w = max(0.0, area.width() - right_w - 8)
                p.setFont(self.font_label)
                p.setPen(col if flash else QColor(215, 215, 222))
                text = QFontMetrics(self.font_label).elidedText(label, Qt.ElideRight, int(text_w))
                p.drawText(QRectF(x0, rect.top(), text_w, hh),
                           Qt.AlignVCenter | Qt.AlignLeft, text)
            p.setOpacity(a)

        mf = self.musicf.x
        if mf > 0.02:  # indikator kecil "lagi ada musik" di notch mode ringkas
            mc = QColor(*COL_MEDIA)
            mc.setAlphaF(clamp(mf))
            p.setPen(Qt.NoPen)
            p.setBrush(mc)
            for i in range(4):
                h = 3 + (0.5 + 0.5 * math.sin(t * (7 + i * 1.7) + i * 1.3)) * 9
                p.drawRoundedRect(QRectF(rect.right() - 36 + i * 5, mid - h / 2, 2.6, h), 1.3, 1.3)

        sf = self.sleepf.x
        if sf > 0.02:
            for k in range(3):
                ph = (t * 0.45 + k / 3) % 1
                zc = QColor(col)
                zc.setAlphaF(clamp(sf * math.sin(math.pi * ph) * 0.9))
                f = QFont(self.font_z)
                f.setPointSizeF(6 + ph * 4)
                p.setFont(f)
                p.setPen(zc)
                p.drawText(QPointF(rect.right() - 40 + ph * 16,
                                   rect.bottom() - 6 - ph * (rect.height() - 12)), "z")


    def paint_menu(self, p, rect, col, a):
        m = clamp(self.menuf.x)
        if m < 0.01:
            return
        line = QColor(255, 255, 255)
        line.setAlphaF(0.08 * m)
        p.setPen(QPen(line, 1))
        y = rect.top() + MENU_HEAD - 4
        p.drawLine(QPointF(rect.left() + 18, y), QPointF(rect.right() - 18, y))

        # dua halaman berdampingan: daftar menu di kiri, lokasi di kanan
        pg = self.page.x
        for page, shift in ((0, -pg), (1, 1 - pg)):
            if abs(shift) > 0.999:  # halaman di luar notch
                continue
            fade = 1 - 0.6 * abs(shift)
            p.save()
            p.translate(shift * rect.width(), 0)
            if page == 0:
                self.paint_menu_main(p, rect, col, a * fade, m)
            else:
                self.paint_menu_lokasi(p, rect, col, a * fade, m)
            p.restore()
        p.setOpacity(a)

    def paint_highlight(self, p, rect, m, page_keys):
        hl = clamp(self.hl_a.x) * m
        if hl < 0.01 or self.hl_key is None or not page_keys(self.hl_key):
            return
        danger = self.hl_key == "quit"
        pressed = time.perf_counter() - self.menu_pressed_at < 0.15
        c = QColor(*COL_DANGER) if danger else QColor(255, 255, 255)
        c.setAlphaF(clamp(hl * (0.16 if danger else 0.08) * (1.8 if pressed else 1.0)))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(rect.left() + 8, rect.top() + self.hl_y.x,
                                 rect.width() - 16, MENU_ROW), 11, 11)

    def paint_menu_main(self, p, rect, col, a, m):
        rows = self.menu_rows(rect)
        p.setOpacity(a)
        line = QColor(255, 255, 255)
        line.setAlphaF(0.08 * m)
        p.setPen(QPen(line, 1))
        y = rows[-1][1].top() - MENU_SEP / 2
        p.drawLine(QPointF(rect.left() + 18, y), QPointF(rect.right() - 18, y))
        self.paint_highlight(p, rect, m, lambda k: k in MENU_KEYS)  # meluncur ke baris di-hover

        lokasi = self.settings.get("sholat")
        labels = {"fullscreen": "Sembunyi saat ada app fullscreen",
                  "autostart": "Jalan otomatis saat komputer nyala",
                  "lokasi": "Lokasi sholat", "quit": "Keluar"}
        fm = QFontMetrics(self.font_item)
        fm_small = QFontMetrics(self.font_small)
        for i, (key, r) in enumerate(rows):
            appear = smoothstep(clamp((m - 0.2 - i * 0.1) / 0.45))  # muncul satu per satu
            if appear < 0.01:
                continue
            p.setOpacity(a * appear)
            r = r.translated(0, (appear - 1) * 8)
            cy = r.center().y()
            fg = (QColor(*COL_DANGER) if key == "quit" else
                  QColor(245, 245, 250) if key == self.menu_hover else QColor(205, 205, 214))
            self.paint_menu_icon(p, key, QPointF(r.left() + 17, cy), fg)
            text_x, right = r.left() + 36, r.right() - 12

            if key in ("fullscreen", "autostart"):  # saklar ala iOS, kenopnya pakai pegas
                v = (self.sw_fs if key == "fullscreen" else self.sw_auto).x
                k = clamp(v)
                track = QRectF(right - 30, cy - 9, 30, 18)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(int(lerp(255, col.red(), k)), int(lerp(255, col.green(), k)),
                                  int(lerp(255, col.blue(), k)), int(lerp(40, 255, k))))
                p.drawRoundedRect(track, 9, 9)
                p.setBrush(QColor(250, 250, 252))
                p.drawEllipse(QPointF(track.left() + 9 + v * 12, cy), 7, 7)
                right = track.left() - 10
            elif key == "lokasi":  # nama kota + ›
                self.paint_chevron(p, QPointF(right, cy))
                value = lokasi["lokasi"] if lokasi else "Atur"
                vw = min(fm_small.horizontalAdvance(value), 130)
                p.setFont(self.font_small)
                p.drawText(QRectF(right - 12 - vw, r.top(), vw, r.height()),
                           Qt.AlignVCenter | Qt.AlignRight,
                           fm_small.elidedText(value, Qt.ElideRight, vw))
                right -= 20 + vw

            text_w = max(0, int(right - text_x))
            p.setFont(self.font_item)
            p.setPen(fg)
            p.drawText(QRectF(text_x, r.top(), text_w, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(labels[key], Qt.ElideRight, text_w))

    def paint_menu_lokasi(self, p, rect, col, a, m):
        now = time.perf_counter()
        p.setOpacity(a * m)
        lay = dict(self.loc_layout(rect))
        field, simpan = lay["field"], lay["simpan"]
        fm = QFontMetrics(self.font_item)

        # kolom ketik
        border = QColor(col)
        border.setAlphaF(0.55 if self.loc_editing else 0.0)
        p.setPen(QPen(border, 1.2))
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(field, 10, 10)
        text_rect = field.adjusted(12, 0, -10, 0)
        p.setFont(self.font_item)
        if self.loc_text:
            shown = fm.elidedText(self.loc_text, Qt.ElideLeft, int(text_rect.width() - 4))
            p.setPen(QColor(245, 245, 250))
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, shown)
            caret_x = text_rect.left() + fm.horizontalAdvance(shown) + 1
        else:
            p.setPen(QColor(115, 115, 125))
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, "Nama kota, mis. pekalongan")
            caret_x = text_rect.left()
        if self.loc_editing and (now - self.loc_key_at) % 1.0 < 0.55:  # kedip, diam saat ngetik
            caret = QPen(col, 1.6)
            caret.setCapStyle(Qt.RoundCap)
            p.setPen(caret)
            p.drawLine(QPointF(caret_x, field.center().y() - 7), QPointF(caret_x, field.center().y() + 7))

        # tombol Simpan: menyala kalau sudah ada kota terpilih
        ok = self.loc_choice() is not None
        pressed = self.menu_hover == "simpan" and now - self.menu_pressed_at < 0.15
        p.setPen(Qt.NoPen)
        if ok:
            p.setBrush(QColor(col).lighter(118) if self.menu_hover == "simpan" else col)
        else:
            p.setBrush(QColor(255, 255, 255, 22))
        d = 1.5 if pressed else 0.0  # mengecil sedikit saat ditekan
        p.drawRoundedRect(simpan.adjusted(d, d, -d, -d), 10, 10)
        p.setFont(self.font_label)
        p.setPen(QColor(15, 15, 25) if ok else QColor(110, 110, 120))
        p.drawText(simpan, Qt.AlignCenter, "Simpan")

        # hasil pencarian / keterangan
        self.paint_highlight(p, rect, m, lambda k: k.startswith("hasil"))
        shown = self.loc_shown()
        top = rect.top() + MENU_HEAD + 40
        for i, h in enumerate(shown):
            r = lay[f"hasil{i}"]
            cy = r.center().y()
            sel = i == self.loc_sel
            fg = QColor(245, 245, 250) if sel or self.menu_hover == f"hasil{i}" else QColor(190, 190, 200)
            self.paint_menu_icon(p, "lokasi", QPointF(r.left() + 17, cy), col if sel else fg)
            p.setFont(self.font_item)
            p.setPen(fg)
            p.drawText(QRectF(r.left() + 36, r.top(), r.width() - 70, r.height()),
                       Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(h["lokasi"], Qt.ElideRight, int(r.width() - 70)))
            if sel:  # centang
                pen = QPen(col, 2.0)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                x = r.right() - 16
                p.drawPolyline(QPolygonF([QPointF(x - 9, cy), QPointF(x - 5, cy + 4),
                                          QPointF(x + 2, cy - 4)]))
        extra = len(self.loc_results or []) - len(shown)
        note = f"+{extra} lainnya, ketik lebih lengkap" if extra else None if shown else self.loc_status
        if note:
            if note == "Mencari":
                note += "." * (1 + int(now * 3) % 3)
            p.setFont(self.font_small)
            p.setPen(QColor(140, 140, 150))
            p.drawText(QRectF(rect.left() + 24, top + len(shown) * MENU_ROW, rect.width() - 48, MENU_ROW),
                       Qt.AlignVCenter | Qt.AlignLeft, note)

    def paint_chevron(self, p, c):
        pen = QPen(QColor(150, 150, 160), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPolygonF([QPointF(c.x() - 4, c.y() - 4), c, QPointF(c.x() - 4, c.y() + 4)]))

    def paint_menu_icon(self, p, key, c, color):
        p.save()
        p.translate(c)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if key == "fullscreen":  # empat sudut layar
            for sx in (-1, 1):
                for sy in (-1, 1):
                    p.drawPolyline(QPolygonF([QPointF(sx * 6, sy * 2.5), QPointF(sx * 6, sy * 6),
                                              QPointF(sx * 2.5, sy * 6)]))
        elif key == "autostart":  # petir
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawPolygon(QPolygonF([QPointF(1.5, -7), QPointF(-4.5, 1), QPointF(-0.5, 1),
                                     QPointF(-1.5, 7), QPointF(4.5, -1), QPointF(0.5, -1)]))
        elif key == "lokasi":  # pin peta
            pin = QPainterPath()
            pin.moveTo(0, 7)
            pin.cubicTo(-2, 4, -5.5, 1, -5.5, -2)
            pin.arcTo(QRectF(-5.5, -7.5, 11, 11), 180, -180)
            pin.cubicTo(5.5, 1, 2, 4, 0, 7)
            p.drawPath(pin)
            p.drawEllipse(QPointF(0, -2), 1.6, 1.6)
        else:  # tombol power
            p.drawArc(QRectF(-6, -5, 12, 12), 125 * 16, 290 * 16)
            p.drawLine(QPointF(0, -6.5), QPointF(0, 0))
        p.restore()

    def paint_media(self, p, rect):
        info = self.track
        now = time.perf_counter()
        mid = self.head_mid(rect)

        cover = QRectF(rect.left() + 86, mid - 20, 40, 40)
        clip = QPainterPath()
        clip.addRoundedRect(cover, 8, 8)
        if self.art_pixmap:
            p.save()
            p.setClipPath(clip, Qt.IntersectClip)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(cover, self.art_pixmap, QRectF(self.art_pixmap.rect()))
            p.restore()
        else:
            p.fillPath(clip, QColor(40, 40, 46))
            p.setPen(QColor(*COL_MEDIA))
            p.setFont(self.font_clock)
            p.drawText(cover, Qt.AlignCenter, "♪")

        buttons = self.media_buttons(rect)
        x0 = cover.right() + 10
        text_w = max(0.0, buttons[0][1].x() - 20 - x0)
        p.setFont(self.font_label)
        p.setPen(QColor(245, 245, 250))
        p.drawText(QRectF(x0, rect.top() + 10, text_w, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(self.font_label).elidedText(info["title"], Qt.ElideRight, int(text_w)))
        p.setFont(self.font_small)
        p.setPen(QColor(150, 150, 160))
        p.drawText(QRectF(x0, rect.top() + 27, text_w, 16), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(self.font_small).elidedText(info["artist"], Qt.ElideRight, int(text_w)))

        progress = self.track_progress()
        if progress is not None:
            bar = QRectF(x0, rect.top() + 46, text_w, 2.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 40))
            p.drawRoundedRect(bar, 1.2, 1.2)
            p.setBrush(QColor(*COL_MEDIA))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * progress, bar.height()),
                              1.2, 1.2)

        cur = self.mapFromGlobal(QCursor.pos())
        for action, c in buttons:
            pressed = action == self.btn_pressed and now - self.btn_pressed_at < 0.18
            if math.hypot(cur.x() - c.x(), cur.y() - c.y()) <= 15:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 45 if pressed else 28))
                p.drawEllipse(c, 14, 14)
            icon = "pause" if action == "playpause" and info["playing"] else \
                "play" if action == "playpause" else action
            self.paint_icon(p, icon, c, 0.8 if pressed else 1.0)

    def paint_icon(self, p, icon, c, scale):
        p.save()
        p.translate(c)
        p.scale(scale, scale)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(245, 245, 250))
        if icon == "play":
            p.drawPolygon(QPolygonF([QPointF(-4, -6.5), QPointF(-4, 6.5), QPointF(7, 0)]))
        elif icon == "pause":
            p.drawRoundedRect(QRectF(-5.5, -6.5, 4, 13), 1.2, 1.2)
            p.drawRoundedRect(QRectF(1.5, -6.5, 4, 13), 1.2, 1.2)
        else:  # next; prev = next dicerminkan
            if icon == "prev":
                p.scale(-1, 1)
            p.drawPolygon(QPolygonF([QPointF(-6, -5.5), QPointF(-6, 5.5), QPointF(2.5, 0)]))
            p.drawRoundedRect(QRectF(3.5, -5.5, 2.4, 11), 1, 1)
        p.restore()


def main():
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("Peringatan: sesi Wayland terdeteksi. Notch butuh sesi Xorg "
              "(layar login -> ikon gerigi -> 'Ubuntu on Xorg').", file=sys.stderr)
    plat = Platform()
    lock = plat.single_instance()  # disimpan supaya tetap terkunci selama app jalan
    if lock is None:
        return
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = Notch(plat)
    w.show()
    plat.setup_window(w)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
